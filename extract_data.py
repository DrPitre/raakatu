#!/usr/bin/env python3
"""
Extract binary game data from raaka-tu.asm and generate gamedata.c.
"""
import re
import sys
import os

# Match $XX or $XXXX hex values, ignoring trailing garbage
HEX_RE = re.compile(r'\$([0-9A-Fa-f]{1,4})')
DEC_RE = re.compile(r'^(-?\d+)$')

def parse_bytes_from_line(line):
    s = line.split(';')[0]  # strip ; comments

    # fcb directive: collect all $XX hex or decimal values
    m = re.search(r'\bfcb\b\s+(.+)$', s, re.IGNORECASE)
    if m:
        args = m.group(1)
        result = []
        for tok in args.split(','):
            tok = tok.strip()
            if not tok:
                continue
            hm = HEX_RE.match(tok)
            if hm:
                result.append(int(hm.group(1), 16) & 0xFF)
            else:
                dm = DEC_RE.match(tok)
                if dm:
                    result.append(int(dm.group(1)) & 0xFF)
                # else: skip (undelimited comment text, label expressions, etc.)
        return result if result else None

    # fcc /string/ — use / as delimiters
    m = re.search(r'\bfcc\b\s+/([^/]*)/\s*$', s, re.IGNORECASE)
    if m:
        return [ord(c) for c in m.group(1)]

    # fcc "string" — use " as delimiters
    m = re.search(r'\bfcc\b\s+"([^"]*)"\s*$', s, re.IGNORECASE)
    if m:
        return [ord(c) for c in m.group(1)]

    return None


def extract_section(lines, start_label, end_label):
    in_section = False
    data = []
    for line in lines:
        m = re.match(r'^(\w+)', line)
        if m:
            label = m.group(1)
            if label == end_label and in_section:
                break
            if label == start_label:
                in_section = True
        if in_section:
            b = parse_bytes_from_line(line)
            if b is not None:
                data.extend(b)
    return data


def bytes_to_c_array(name, data, cols=16):
    out = ['unsigned char %s[] = {' % name]
    for i in range(0, len(data), cols):
        chunk = data[i:i+cols]
        out.append('    ' + ', '.join('0x%02X' % b for b in chunk) + ',')
    out.append('};')
    out.append('int %s_len = %d;' % (name, len(data)))
    return '\n'.join(out)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    asm_path = os.path.join(script_dir, 'raaka-tu.asm')
    out_path = os.path.join(script_dir, 'gamedata.c')

    print('Reading %s ...' % asm_path, file=sys.stderr)
    with open(asm_path, 'r', errors='replace') as f:
        lines = f.readlines()

    # (c_var_name, start_label, end_label)
    # rand_seed: start at L1333 (multi-verb $00 + 8 seed bytes),
    #   actual seed starts at offset 1 — handled in C
    sections = [
        ('chartab',    'L1279',  'L12A1'),
        ('rand_seed',  'L1333',  'L133C'),   # byte 0 = multivb; bytes 1-8 = seed
        ('msg_qverb',  'L133C',  'L1343'),
        ('msg_qwhat',  'L1343',  'L134A'),
        ('msg_qwhich', 'L134A',  'L1352'),
        ('msg_qphrase','L1352',  'L135B'),
        ('phrase_list','L135B',  'L1523'),
        ('room_data',  'L1523',  'L20FF'),
        ('obj_data',   'L20FF',  'L323C'),
        ('cmd_data',   'L323C',  'L37FA'),
        ('ccmd_data',  'L37FA',  'L3C29'),
        ('vocab_data', 'L3C29',  'L3ECF'),
        ('prep_data',  'L3ECF',  'os9read'),
    ]

    out_lines = [
        '/* Auto-generated from raaka-tu.asm -- do not edit */',
        '',
    ]

    total = 0
    for c_name, start, end in sections:
        data = extract_section(lines, start, end)
        if not data:
            print('WARNING: no data for %s (%s to %s)' % (c_name, start, end),
                  file=sys.stderr)
        else:
            print('%s: %d bytes' % (c_name, len(data)), file=sys.stderr)
            total += len(data)
        out_lines.append(bytes_to_c_array(c_name, data))
        out_lines.append('')

    with open(out_path, 'w') as f:
        f.write('\n'.join(out_lines))

    print('Wrote %s (%d bytes total)' % (out_path, total), file=sys.stderr)


if __name__ == '__main__':
    main()
