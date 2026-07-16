#!/usr/bin/env python3
"""Generate native Z-string and direct vocabulary dispatch for Raaka-Tu."""

import argparse
import pathlib
import sys

from generate_zdata import parse_c_arrays
from generate_zcompact import CompactBuilder
from generate_zscripts import Compiler


ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = ROOT / "gamedata.c"
OUTPUT = ROOT / "zmachine" / "fastdata.inf"


def list_from_len(data, pos):
    first = data[pos]
    if first & 0x80:
        length = ((first & 0x7F) << 8) | data[pos + 1]
        content = pos + 2
    else:
        length = first
        content = pos + 1
    return content, content + length


def list_open(data, pos):
    return list_from_len(data, pos + 1)


def packed_text(data, pos, chartab):
    content, end = list_from_len(data, pos)
    result = []
    while content + 1 < end:
        value = data[content] | (data[content + 1] << 8)
        result.extend((
            chartab[value // 1600],
            chartab[(value // 40) % 40],
            chartab[value % 40],
        ))
        content += 2
    if content < end:
        result.append(data[content])
    return result


def rendered_text(values, initial_cap):
    cap = initial_cap
    chars = []
    for value in values:
        if value == 0xCF:
            continue
        char = chr(value)
        if "A" <= char <= "Z":
            if not cap:
                char = char.lower()
            cap = False
        elif char in ".!?":
            cap = True
        elif value in (10, 13):
            cap = True
        chars.append(char)
    # Script messages are concatenated at runtime. Some source fragments
    # already carry their separator; add one only when it is absent.
    if not chars or not chars[-1].isspace():
        chars.append(" ")
    return "".join(chars), int(cap)


def inform_string(text):
    escaped = []
    for char in text:
        code = ord(char)
        if char == '"':
            escaped.append("~")
        elif char in ("@", "^", "~", "\\"):
            escaped.append(f"@@{code}")
        elif code == 10 or code == 13:
            escaped.append("^")
        elif 32 <= code <= 126:
            escaped.append(char)
        else:
            escaped.append(f"@@{code}")
    return "".join(escaped)


def collect_texts(arrays):
    locations = []
    for array_name, skip in (("room_data", 1), ("obj_data", 3)):
        data = arrays[array_name]
        pos, outer_end = list_open(data, 0)
        while pos < outer_end:
            content, item_end = list_open(data, pos)
            sub = content + skip
            while sub < item_end:
                tag = data[sub]
                _, sub_end = list_open(data, sub)
                if tag in (2, 3):
                    locations.append((array_name, sub + 1))
                sub = sub_end
            pos = item_end

    compiler = Compiler(arrays)
    compiler.parse_entries()
    locations.extend(compiler.message_locations.values())
    return sorted(set(locations))


def collect_vocabulary(arrays):
    vocabulary = []
    data = arrays["vocab_data"]
    pos = 0
    for word_type in range(4):
        while data[pos] != 0:
            length = data[pos]
            word = bytes(data[pos + 1 : pos + 1 + length]).decode("ascii")
            number = data[pos + 1 + length]
            vocabulary.append((word, word_type, number))
            pos += length + 2
        pos += 1

    data = arrays["prep_data"]
    pos = 0
    while data[pos] != 0:
        length = data[pos]
        word = bytes(data[pos + 1 : pos + 1 + length]).decode("ascii")
        number = data[pos + 1 + length]
        vocabulary.append((word, 4, number))
        pos += length + 2
    return vocabulary


def word_condition(word, start=0):
    tests = [f"input_buffer->(pos + {index}) == '{char}'"
             for index, char in enumerate(word) if index >= start]
    if len(word) < 6:
        end = len(word)
        tests.append(
            f"(input_buffer->(pos + {end}) < 'A' || "
            f"input_buffer->(pos + {end}) > 'Z')"
        )
    return " && ".join(tests)


def phrase_index(arrays, verb_count=64):
    data = arrays["phrase_list"]
    groups = [dict() for _ in range(verb_count)]
    defaults = [255] * verb_count
    for pos in range(0, len(data) - 4, 5):
        verb = data[pos]
        if verb == 0:
            break
        if verb >= verb_count:
            raise ValueError(f"phrase verb {verb} exceeds generated index")
        row = pos // 5
        prep = data[pos + 1]
        if defaults[verb] == 255:
            defaults[verb] = row
        if prep not in groups[verb]:
            groups[verb][prep] = row
    starts = []
    pairs = []
    for group in groups:
        starts.append(len(pairs) // 2)
        for prep, row in group.items():
            pairs.extend((prep, row))
    starts.append(len(pairs) // 2)
    return defaults, starts, pairs


def render(arrays):
    chartab = arrays["chartab"]
    _, text_sources = CompactBuilder(arrays).build()
    lines = [
        "! Auto-generated by generate_zfast.py.",
        "! Indexed native Z-strings replace base-40 decoding; direct tests",
        "! replace linear vocabulary-table scans.",
        "",
    ]
    lower_initials = []
    upper_initials = []
    suffixes = []
    for text_id, (array_name, pos) in enumerate(text_sources, 1):
        values = packed_text(arrays[array_name], pos, chartab)
        lower, lower_cap = rendered_text(values, False)
        upper, upper_cap = rendered_text(values, True)
        differences = [
            index for index, pair in enumerate(zip(lower, upper))
            if pair[0] != pair[1]
        ]
        if not differences:
            prefix = 0
            lower_initial = 0
            upper_initial = 0
            suffixes.append(lower)
        elif len(differences) == 1 and differences[0] <= 1:
            index = differences[0]
            prefix = ord(lower[0]) if index == 1 else 0
            lower_initial = ord(lower[index])
            upper_initial = ord(upper[index])
            suffixes.append(lower[index + 1:])
        else:
            raise ValueError(
                f"{array_name}+0x{pos:x}: unsupported capitalization layout"
            )
        if lower_cap != upper_cap:
            raise ValueError(
                f"{array_name}+0x{pos:x}: capitalization changes final state"
            )
        # Lowercase initials use bit 7 to mark a preceding character.
        # Uppercase initials use bit 7 for final capitalization state and
        # bit 5 to distinguish the sole '<' prefix from quote prefixes.
        if prefix:
            lower_initial |= 0x80
            if prefix == ord("<"):
                upper_initial |= 0x20
            elif prefix != ord('"'):
                raise ValueError(f"unsupported text prefix {prefix!r}")
        upper_initial |= lower_cap << 7
        lower_initials.append(lower_initial)
        upper_initials.append(upper_initial)

    def byte_array(name, values):
        result = [f"Array {name} ->"]
        for index in range(0, len(values), 16):
            chunk = " ".join(f"${value:02X}" for value in values[index:index + 16])
            suffix = ";" if index + 16 >= len(values) else ""
            result.append(f"    {chunk}{suffix}")
        result.append("")
        return result

    lines.extend(byte_array("text_lower_initials", lower_initials))
    lines.extend(byte_array("text_upper_initials", upper_initials))
    lines.append("Array text_strings -->")
    for index, suffix in enumerate(suffixes):
        terminator = ";" if index + 1 == len(suffixes) else ""
        lines.append(f'    "{inform_string(suffix)}"{terminator}')
    lines.extend((
        "",
        "[ FastPrintPacked text_id index lower upper c packed;",
        "    index = text_id - 1;",
        "    lower = text_lower_initials->index;",
        "    upper = text_upper_initials->index;",
        "    if ((lower & $80) ~= 0) {",
        "        if ((upper & $20) ~= 0) c = '<'; else c = 34;",
        "        @print_char c;",
        "    }",
        "    if (cap_next) c = upper & $5F; else c = lower & $7F;",
        "    if (c ~= 0) @print_char c;",
        "    packed = text_strings-->index;",
        "    @print_paddr packed;",
        "    if ((upper & $80) ~= 0) cap_next = 1; else cap_next = 0;",
        "];",
        "",
    ))

    vocabulary = collect_vocabulary(arrays)
    sentinel = "AAAAAA"
    if any(word == sentinel for word, _, _ in vocabulary):
        raise ValueError("dictionary sentinel collides with game vocabulary")
    vocabulary.append((sentinel, 0, 0))
    vocabulary.sort(key=lambda entry: entry[0])
    sentinel_index = next(
        index for index, entry in enumerate(vocabulary)
        if entry[0] == sentinel
    )
    lines.append("! Populate the V3 dictionary consumed natively by @sread.")
    for word, _, _ in vocabulary:
        lines.append(f"Dictionary '{word.lower()}';")
    lines.extend((
        f"Constant FAST_DICT_COUNT {len(vocabulary)};",
        "Constant FAST_DICT_ENTRY_SIZE 7;",
        f"Constant FAST_DICT_SENTINEL_INDEX {sentinel_index};",
        "Constant FastDictSentinel 'aaaaaa';",
        "",
    ))
    lines.extend(byte_array(
        "fast_dict_types", [word_type for _, word_type, _ in vocabulary]
    ))
    lines.extend(byte_array(
        "fast_dict_nums", [number for _, _, number in vocabulary]
    ))
    defaults, starts, pairs = phrase_index(arrays)
    lines.append("! Direct per-verb index into the original phrase rows.")
    lines.extend(byte_array("phrase_defaults", defaults))
    lines.extend(byte_array("phrase_group_starts", starts))
    lines.extend(byte_array("phrase_prep_rows", pairs))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="fail if generated output is stale"
    )
    args = parser.parse_args()
    try:
        arrays = dict(parse_c_arrays(SOURCE.read_text()))
        generated = render(arrays)
    except (OSError, ValueError, IndexError) as exc:
        print(f"generate_zfast.py: {exc}", file=sys.stderr)
        return 1

    if args.check:
        try:
            current = OUTPUT.read_text()
        except OSError as exc:
            print(f"generate_zfast.py: {exc}", file=sys.stderr)
            return 1
        if current != generated:
            print(f"{OUTPUT} is stale; run generate_zfast.py", file=sys.stderr)
            return 1
        print(f"{OUTPUT} is current")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(generated)
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
