#!/usr/bin/env python3
"""Compile Raaka-Tu's data-driven scripts into direct Inform 6 routines."""

import argparse
from dataclasses import dataclass
import pathlib
import sys

from generate_zdata import parse_c_arrays


ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = ROOT / "gamedata.c"
OUTPUT = ROOT / "zmachine" / "scripts.inf"

NUM_OPS = 0x27
OPERAND_BYTES = (
    1, 1, 1, 2, 0, 1, 0, 0, 1, 1, 1, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 2, 0, 1,
    0, 0, 1, 1, 2, 0, 1, 3, 1, 1, 0, 0, 0,
)
MESSAGE_OPS = {4, 31}
DISPATCH_OP = 11
LIST_OPS = {13: 0, 14: 1}
NOT_OP = 20
TEST_OPERAND_BYTES = {
    1: 1, 2: 1, 3: 2, 5: 1, 8: 1, 9: 1, 10: 1,
    15: 0, 18: 0, 20: 1, 21: 1, 22: 1,
}


@dataclass(frozen=True)
class Node:
    kind: str
    args: tuple = ()


class Compiler:
    def __init__(self, arrays):
        self.arrays = arrays
        self.message_locations = {}
        self.function_names = {}
        self.functions = []

    @staticmethod
    def list_from_len(data, pos):
        first = data[pos]
        if first & 0x80:
            length = ((first & 0x7F) << 8) | data[pos + 1]
            content = pos + 2
        else:
            length = first
            content = pos + 1
        return content, content + length

    def list_open(self, data, pos):
        return self.list_from_len(data, pos + 1)

    def list_begin(self, data):
        return self.list_open(data, 0)

    def message_node(self, array_name, data, pos):
        content, end = self.list_from_len(data, pos)
        encoded = bytes(data[content:end])
        location = self.message_locations.setdefault(encoded, (array_name, pos))
        return Node("op", (4, location)), end

    def parse_body(self, array_name, data, op, pos, end):
        if op & 0x80:
            return Node("common", (op,)), pos

        if op >= NUM_OPS:
            size = data[pos]
            block_start = pos + 1
            block_end = block_start + size
            if block_end > len(data):
                raise ValueError(
                    f"{array_name}+0x{pos:x}: phrase block extends past data"
                )
            block = self.parse_script(array_name, data, block_start, block_end)
            return Node("phrase", (op, block)), block_end

        if op in MESSAGE_OPS:
            node, new_pos = self.message_node(array_name, data, pos)
            if op == 31:
                node = Node("op", (31, node.args[1]))
            return node, new_pos

        if op == DISPATCH_OP:
            content, sub_end = self.list_from_len(data, pos)
            if content >= sub_end:
                return Node("dispatch", ()), sub_end
            test_op = data[content]
            item = content + 1
            cases = []
            while item < sub_end:
                operand_count = TEST_OPERAND_BYTES.get(test_op, 0)
                operands = tuple(data[item : item + operand_count])
                if len(operands) != operand_count:
                    raise ValueError(
                        f"{array_name}+0x{item:x}: truncated dispatch test"
                    )
                test = Node("test", (test_op, *operands))
                item += operand_count
                action_content, action_end = self.list_from_len(data, item)
                action, consumed = self.parse_one(
                    # Some dispatch actions deliberately contain only the
                    # opcode byte in their sublist.  The opcode's operands
                    # overlap the following dispatch cases; the original
                    # interpreter likewise lets ExecOne read beyond the
                    # action sublist while the dispatch iterator still skips
                    # only to action_end.
                    array_name, data, action_content, len(data)
                )
                cases.append((test, action))
                item = action_end
            return Node("dispatch", tuple(cases)), sub_end

        if op in LIST_OPS:
            content, sub_end = self.list_from_len(data, pos)
            items = []
            while content < sub_end:
                item, content = self.parse_one(
                    array_name, data, content, sub_end
                )
                items.append(item)
            return Node("list", (LIST_OPS[op], tuple(items))), sub_end

        if op == NOT_OP:
            item, new_pos = self.parse_one(array_name, data, pos, end)
            return Node("not", (item,)), new_pos

        operand_count = OPERAND_BYTES[op]
        operands = tuple(data[pos : pos + operand_count])
        if len(operands) != operand_count:
            raise ValueError(f"{array_name}+0x{pos:x}: truncated opcode {op}")
        return Node("op", (op, *operands)), pos + operand_count

    def parse_one(self, array_name, data, pos, end):
        if pos >= end:
            raise ValueError(f"{array_name}+0x{pos:x}: missing opcode")
        op = data[pos]
        return self.parse_body(array_name, data, op, pos + 1, end)

    def parse_script(self, array_name, data, pos, end):
        items = []
        while pos < end:
            item, pos = self.parse_one(array_name, data, pos, end)
            items.append(item)
        # The original engine permits a compound opcode at the end of a
        # bounded script to consume bytes beyond that bound, then stops.
        # Several cmd_data branches intentionally rely on that overlap.
        return Node("script", tuple(items))

    def parse_sublists(self, array_name, data, pos, end, wanted_tags):
        scripts = {}
        while pos < end:
            tag = data[pos]
            content, item_end = self.list_open(data, pos)
            if tag in wanted_tags:
                scripts[tag] = self.parse_script(
                    array_name, data, content, item_end
                )
            pos = item_end
        return scripts

    def parse_entries(self):
        room_scripts = {}
        data = self.arrays["room_data"]
        pos, end = self.list_begin(data)
        while pos < end:
            room = data[pos]
            content, item_end = self.list_open(data, pos)
            scripts = self.parse_sublists(
                "room_data", data, content + 1, item_end, {4}
            )
            if 4 in scripts:
                room_scripts[room] = scripts[4]
            pos = item_end

        object_scripts = {6: {}, 7: {}, 8: {}, 10: {}}
        data = self.arrays["obj_data"]
        pos, end = self.list_begin(data)
        obj_num = 0
        while pos < end:
            obj_num += 1
            content, item_end = self.list_open(data, pos)
            scripts = self.parse_sublists(
                "obj_data", data, content + 3, item_end, set(object_scripts)
            )
            for tag, script in scripts.items():
                object_scripts[tag][obj_num] = script
            pos = item_end

        common_scripts = {}
        data = self.arrays["ccmd_data"]
        pos, end = self.list_begin(data)
        while pos < end:
            tag = data[pos]
            content, item_end = self.list_open(data, pos)
            common_scripts[tag] = self.parse_script(
                "ccmd_data", data, content, item_end
            )
            pos = item_end

        data = self.arrays["cmd_data"]
        content, end = self.list_open(data, 0)
        main_script = self.parse_script("cmd_data", data, content, end)
        return main_script, common_scripts, room_scripts, object_scripts

    def ensure_function(self, node):
        if node.kind in {"op", "common", "test"}:
            raise ValueError("simple nodes do not need generated routines")
        if node in self.function_names:
            return self.function_names[node]

        for child in self.children(node):
            if child.kind not in {"op", "common", "test"}:
                self.ensure_function(child)

        name = f"AotScript{len(self.functions) + 1:03d}"
        self.function_names[node] = name
        self.functions.append((name, node))
        return name

    @staticmethod
    def children(node):
        if node.kind == "script":
            return node.args
        if node.kind == "list":
            return node.args[1]
        if node.kind == "not":
            return node.args
        if node.kind == "phrase":
            return (node.args[1],)
        if node.kind == "dispatch":
            return tuple(child for case in node.args for child in case)
        return ()

    def expression(self, node):
        if node.kind == "common":
            return f"AotRunCommon(${node.args[0]:02X})"
        if node.kind == "test":
            op, *args = node.args
            args.extend((0,) * (2 - len(args)))
            return f"AotTest(${op:02X}, ${args[0]:02X}, ${args[1]:02X})"
        if node.kind == "op":
            op, *args = node.args
            rendered = []
            for arg in args:
                if isinstance(arg, tuple):
                    rendered.append(f"{arg[0]} + ${arg[1]:04X}")
                else:
                    rendered.append(f"${arg:02X}")
            suffix = (" " + " ".join(rendered)) if rendered else ""
            return f"AotOp{op:02d}({', '.join(rendered)})"
        return f"{self.ensure_function(node)}()"

    def render_function(self, name, node):
        lines = [f"[ {name}"]
        if node.kind == "script":
            for item in node.args:
                lines.append(f"    r = {self.expression(item)};")
                lines.append("    if (r ~= 0) return r;")
            lines.append("    return 0;")
        elif node.kind == "list":
            stop_on, items = node.args
            for item in items:
                lines.append(f"    r = {self.expression(item)};")
                lines.append("    if (r == 2) return 2;")
                lines.append(f"    if (r == {stop_on}) return {stop_on};")
            lines.append(f"    return {1 - stop_on};")
        elif node.kind == "not":
            lines.append(f"    r = {self.expression(node.args[0])};")
            lines.append("    if (r == 2) return 2;")
            lines.append("    if (r ~= 0) return 0;")
            lines.append("    return 1;")
        elif node.kind == "phrase":
            phrase, block = node.args
            lines.append(
                f"    if (phrase_form == ${phrase:02X}) "
                f"return {self.expression(block)};"
            )
            lines.append("    return 0;")
        elif node.kind == "dispatch":
            equality_vars = {8: "noun1_num", 9: "noun2_num",
                             10: "phrase_form", 20: "active_obj"}
            test_ops = {
                test.args[0] for test, action in node.args
                if test.kind == "test"
            }
            if len(test_ops) == 1 and next(iter(test_ops)) in equality_vars:
                test_op = next(iter(test_ops))
                lines.append(f"    switch ({equality_vars[test_op]}) {{")
                for test, action in node.args:
                    lines.append(
                        f"        ${test.args[1]:02X}: "
                        f"return {self.expression(action)};"
                    )
                lines.append("    }")
            else:
                for test, action in node.args:
                    lines.append(f"    r = {self.expression(test)};")
                    lines.append("    if (r == 2) return 2;")
                    lines.append(
                        f"    if (r ~= 0) return {self.expression(action)};"
                    )
            lines.append("    return 0;")
        else:
            raise ValueError(f"cannot render {node.kind}")
        if any("r = " in line for line in lines[1:]):
            lines[0] += " r;"
        else:
            lines[0] += ";"
        lines.append("];")
        return lines

    def render_dispatch(self, name, mapping):
        lines = [f"[ {name} key;", "    switch (key) {"]
        for key, node in sorted(mapping.items()):
            lines.append(
                f"        ${key:02X}: return {self.expression(node)};"
            )
        lines.extend(("    }", "    return 0;", "];"))
        return lines

    def render(self):
        main, common, rooms, objects = self.parse_entries()

        entries = [main, *common.values(), *rooms.values()]
        for scripts in objects.values():
            entries.extend(scripts.values())
        for node in entries:
            self.ensure_function(node)

        lines = [
            "! Auto-generated from gamedata.c by generate_zscripts.py.",
            "! Direct routines replace runtime interpretation of game scripts.",
            "",
        ]
        for name, node in self.functions:
            lines.extend(self.render_function(name, node))
            lines.append("")

        lines.extend(
            (
                f"[ AotMainScript; return {self.expression(main)}; ];",
                "",
            )
        )
        dispatchers = (
            ("AotRunCommon", common),
            ("AotRunRoomCommand", rooms),
            ("AotRunNoun2Command", objects[6]),
            ("AotRunNoun1Command", objects[7]),
            ("AotRunTurnCommand", objects[8]),
            ("AotRunDeathCommand", objects[10]),
        )
        for name, mapping in dispatchers:
            lines.extend(self.render_dispatch(name, mapping))
            lines.append("")

        turn_ids = sorted(objects[8])
        lines.append(f"Constant AOT_TURN_COUNT {len(turn_ids)};")
        lines.append(
            "Array aot_turn_obj_ids -> "
            + " ".join(f"${obj:02X}" for obj in turn_ids)
            + ";"
        )
        lines.append("")
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="fail if generated output is stale"
    )
    args = parser.parse_args()

    try:
        arrays = dict(parse_c_arrays(SOURCE.read_text()))
        generated = Compiler(arrays).render()
    except (OSError, ValueError, IndexError) as exc:
        print(f"generate_zscripts.py: {exc}", file=sys.stderr)
        return 1

    if args.check:
        try:
            current = OUTPUT.read_text()
        except OSError as exc:
            print(f"generate_zscripts.py: {exc}", file=sys.stderr)
            return 1
        if current != generated:
            print(f"{OUTPUT} is stale; run generate_zscripts.py", file=sys.stderr)
            return 1
        print(f"{OUTPUT} is current")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(generated)
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
