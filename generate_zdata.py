#!/usr/bin/env python3
"""Generate Inform 6 byte arrays from the verified C game-data snapshot."""

import argparse
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = ROOT / "gamedata.c"
OUTPUT = ROOT / "zmachine" / "gamedata.inf"

ARRAY_RE = re.compile(
    r"unsigned char\s+(\w+)\[\]\s*=\s*\{(.*?)\};\s*"
    r"int\s+\1_len\s*=\s*(\d+)\s*;",
    re.DOTALL,
)
BYTE_RE = re.compile(r"0x([0-9A-Fa-f]{2})")


def parse_c_arrays(text):
    arrays = []
    for match in ARRAY_RE.finditer(text):
        name, body, declared_len = match.groups()
        values = [int(value, 16) for value in BYTE_RE.findall(body)]
        if len(values) != int(declared_len):
            raise ValueError(
                f"{name}: declared length {declared_len}, found {len(values)} bytes"
            )
        arrays.append((name, values))
    if not arrays:
        raise ValueError("no game-data arrays found")
    return arrays


def render(arrays):
    lines = [
        "! Auto-generated from gamedata.c by generate_zdata.py -- do not edit.",
        "! These must remain writable so Version 3 SAVE captures game state.",
        "",
    ]
    for name, values in arrays:
        lines.append(f"Array {name} ->")
        for offset in range(0, len(values), 16):
            chunk = values[offset : offset + 16]
            lines.append("    " + " ".join(f"${value:02X}" for value in chunk))
        lines[-1] += ";"
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="fail if the checked-in output is stale"
    )
    args = parser.parse_args()

    try:
        generated = render(parse_c_arrays(SOURCE.read_text()))
    except (OSError, ValueError) as exc:
        print(f"generate_zdata.py: {exc}", file=sys.stderr)
        return 1

    if args.check:
        try:
            current = OUTPUT.read_text()
        except OSError as exc:
            print(f"generate_zdata.py: {exc}", file=sys.stderr)
            return 1
        if current != generated:
            print(f"{OUTPUT} is stale; run generate_zdata.py", file=sys.stderr)
            return 1
        print(f"{OUTPUT} is current")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(generated)
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
