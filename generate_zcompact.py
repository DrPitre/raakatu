#!/usr/bin/env python3
"""Generate compact runtime data with legacy packed text payloads removed."""

import argparse
import pathlib
import sys

from generate_zdata import parse_c_arrays
from generate_zscripts import Compiler, Node


ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = ROOT / "gamedata.c"
OUTPUT = ROOT / "zmachine" / "compactdata.inf"


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


def length_prefix(length):
    if length < 0x80:
        return [length]
    if length > 0x7FFF:
        raise ValueError(f"list is too long: {length}")
    return [0x80 | (length >> 8), length & 0xFF]


def tagged(tag, payload):
    return [tag, *length_prefix(len(payload)), *payload]


class CompactBuilder:
    def __init__(self, arrays):
        self.arrays = arrays
        self.compiler = Compiler(arrays)
        self.main, self.common, self.rooms, self.objects = (
            self.compiler.parse_entries()
        )
        self.text_ids = {}
        self.text_sources = []

    def text_payload(self, source):
        text_id = self.text_ids.get(source)
        if text_id is None:
            text_id = len(self.text_sources) + 1
            self.text_ids[source] = text_id
            self.text_sources.append(source)
        return [text_id >> 8, text_id & 0xFF]

    def script(self, node):
        def emit(current):
            if current.kind == "script":
                return sum((emit(child) for child in current.args), [])
            if current.kind == "common":
                return [current.args[0]]
            if current.kind == "op":
                op, *args = current.args
                if op in (4, 31):
                    payload = self.text_payload(args[0])
                    return [op, *length_prefix(len(payload)), *payload]
                return [op, *args]
            if current.kind == "phrase":
                phrase, body = current.args
                nested = emit(body)
                if len(nested) > 255:
                    raise ValueError("phrase-form block exceeds 255 bytes")
                return [phrase, len(nested), *nested]
            if current.kind == "not":
                return [20, *emit(current.args[0])]
            if current.kind == "list":
                stop_on, children = current.args
                opcode = 13 if stop_on == 0 else 14
                payload = sum((emit(child) for child in children), [])
                return [opcode, *length_prefix(len(payload)), *payload]
            if current.kind == "dispatch":
                cases = current.args
                payload = []
                if cases:
                    test_op = cases[0][0].args[0]
                    payload.append(test_op)
                    for test, action in cases:
                        if test.args[0] != test_op:
                            raise ValueError("mixed tests in dispatch block")
                        payload.extend(test.args[1:])
                        action_bytes = emit(action)
                        payload.extend(length_prefix(len(action_bytes)))
                        payload.extend(action_bytes)
                return [11, *length_prefix(len(payload)), *payload]
            raise ValueError(f"cannot serialize node kind {current.kind}")

        return emit(node)

    def build_rooms(self):
        source = self.arrays["room_data"]
        pos, end = list_open(source, 0)
        payload = []
        while pos < end:
            room = source[pos]
            content, item_end = list_open(source, pos)
            room_payload = [room]
            sub = content + 1
            while sub < item_end:
                tag = source[sub]
                sub_content, sub_end = list_open(source, sub)
                if tag in (2, 3):
                    item = tagged(
                        tag, self.text_payload(("room_data", sub + 1))
                    )
                elif tag == 4:
                    body = self.script(self.rooms[room])
                    item = tagged(tag, body)
                else:
                    item = tagged(tag, source[sub_content:sub_end])
                room_payload.extend(item)
                sub = sub_end
            payload.extend(tagged(room, room_payload))
            pos = item_end
        return tagged(source[0], payload)

    def build_objects(self):
        source = self.arrays["obj_data"]
        pos, end = list_open(source, 0)
        payload = []
        obj_num = 0
        while pos < end:
            obj_num += 1
            obj_tag = source[pos]
            content, item_end = list_open(source, pos)
            obj_payload = list(source[content:content + 3])
            sub = content + 3
            while sub < item_end:
                tag = source[sub]
                sub_content, sub_end = list_open(source, sub)
                if tag in (2, 3):
                    item = tagged(
                        tag, self.text_payload(("obj_data", sub + 1))
                    )
                elif tag in self.objects and obj_num in self.objects[tag]:
                    body = self.script(self.objects[tag][obj_num])
                    # Tag 8 scripts are translated to native Z-code by
                    # generate_zturns.py. Walking them above preserves their
                    # text-ID allocation, but retaining a compact copy would
                    # leave 377 bytes of unreachable story data.
                    if tag == 8:
                        sub = sub_end
                        continue
                    item = tagged(tag, body)
                else:
                    item = tagged(tag, source[sub_content:sub_end])
                obj_payload.extend(item)
                sub = sub_end
            payload.extend(tagged(obj_tag, obj_payload))
            pos = item_end
        return tagged(source[0], payload)

    def build_common(self):
        source = self.arrays["ccmd_data"]
        payload = []
        for key, node in sorted(self.common.items()):
            body = self.script(node)
            payload.extend(tagged(key, body))
        return tagged(source[0], payload)

    def build_main(self):
        source = self.arrays["cmd_data"]
        body = self.script(self.main)
        return tagged(source[0], body)

    def build(self):
        compact = {
            "phrase_list": self.arrays["phrase_list"],
            "room_data": self.build_rooms(),
            "obj_data": self.build_objects(),
            "cmd_data": self.build_main(),
            "ccmd_data": self.build_common(),
        }
        return compact, self.text_sources


def render(arrays):
    order = (
        "phrase_list", "room_data", "obj_data", "cmd_data", "ccmd_data",
    )
    lines = [
        "! Auto-generated by generate_zcompact.py -- do not edit.",
        "! Packed text and unused source tables are omitted.",
        "",
    ]
    for name in order:
        data = arrays[name]
        lines.append(f"Array {name} ->")
        for index in range(0, len(data), 16):
            chunk = " ".join(f"${value:02X}" for value in data[index:index + 16])
            suffix = ";" if index + 16 >= len(data) else ""
            lines.append(f"    {chunk}{suffix}")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        original = dict(parse_c_arrays(SOURCE.read_text()))
        compact, _ = CompactBuilder(original).build()
        generated = render(compact)
    except (OSError, ValueError, IndexError) as exc:
        print(f"generate_zcompact.py: {exc}", file=sys.stderr)
        return 1
    if args.check:
        try:
            current = OUTPUT.read_text()
        except OSError as exc:
            print(f"generate_zcompact.py: {exc}", file=sys.stderr)
            return 1
        if current != generated:
            print(f"{OUTPUT} is stale; run generate_zcompact.py", file=sys.stderr)
            return 1
        print(f"{OUTPUT} is current")
        return 0
    OUTPUT.write_text(generated)
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
