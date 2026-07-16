#!/bin/sh
set -eu

ZTERP=${ZTERP:-dfrotz}

if ! command -v "$ZTERP" >/dev/null 2>&1; then
    echo "Z-machine interpreter not found: $ZTERP" >&2
    exit 1
fi

tmpdir=$(mktemp -d "${TMPDIR:-/tmp}/raakatu-z3.XXXXXX")
trap 'rm -rf "$tmpdir"' EXIT HUP INT TERM

awk 'found { print } /^Full command list$/ { getline; getline; found=1 }' \
    full_playthrough.txt > "$tmpdir/commands.txt"

./raakatu-host < "$tmpdir/commands.txt" > "$tmpdir/host.txt"
"$ZTERP" -q -m -p raakatu.z3 < "$tmpdir/commands.txt" \
    > "$tmpdir/zmachine.txt" 2> "$tmpdir/zmachine.err"

python3 - "$tmpdir/host.txt" "$tmpdir/zmachine.txt" <<'PY'
import re
import sys


def normalize(path):
    text = open(path, encoding="utf-8").read()
    text = re.sub(
        r"^>?\s*Raaka-Tu\s+Score:.*(?:\n|$)",
        "",
        text,
        flags=re.MULTILINE,
    )
    text = text.replace("> ", " ")
    return " ".join(text.split())


host = normalize(sys.argv[1])
zmachine = normalize(sys.argv[2])
if host != zmachine:
    for index, (left, right) in enumerate(zip(host, zmachine)):
        if left != right:
            start = max(0, index - 100)
            end = index + 160
            print("Host and Z-machine transcripts diverge:", file=sys.stderr)
            print("host:     " + host[start:end], file=sys.stderr)
            print("zmachine: " + zmachine[start:end], file=sys.stderr)
            break
    else:
        print("Host and Z-machine transcript lengths differ", file=sys.stderr)
    raise SystemExit(1)

if "your score is 50." not in zmachine.lower():
    print("The full playthrough did not reach 50/50", file=sys.stderr)
    raise SystemExit(1)
PY

if grep -Eiq 'fatal error|interpreter error' "$tmpdir/zmachine.err"; then
    cat "$tmpdir/zmachine.err" >&2
    exit 1
fi

printf 'NORTH\nTAKE TORCH\n' | "$ZTERP" -q -m -p raakatu.z3 \
    > "$tmpdir/smoke.txt" 2> "$tmpdir/smoke.err"
grep -qi 'dense damp dark jungle' "$tmpdir/smoke.txt"
grep -qi '?what?' "$tmpdir/smoke.txt"

printf 'NORTH\nWEST\nWEST\nNORTH\nWEST\nEAST\nTAKE COIN\n' \
    | "$ZTERP" -q -m -p raakatu.z3 \
    > "$tmpdir/status.txt" 2> "$tmpdir/status.err"
grep -Eq 'Score: +5 +Moves: +7' "$tmpdir/status.txt"

savefile="$tmpdir/raakatu.qzl"
printf 'NORTH\nSAVE\n%s\nSOUTH\nRESTORE\n%s\nLOOK\n' \
    "$savefile" "$savefile" | "$ZTERP" -q -m -p raakatu.z3 \
    > "$tmpdir/save-restore.txt" 2> "$tmpdir/save-restore.err"
test -s "$savefile"
test "$(grep -ic 'dense damp dark jungle' "$tmpdir/save-restore.txt")" -ge 2

printf 'NORTH\nRESTART\nSCORE\n' | "$ZTERP" -q -m -p raakatu.z3 \
    > "$tmpdir/restart.txt" 2> "$tmpdir/restart.err"
test "$(grep -c '^RAAKA-TU$' "$tmpdir/restart.txt")" -eq 2
grep -qi 'your score is  *00' "$tmpdir/restart.txt"

echo "Z-machine parity tests passed (50/50 walkthrough, smoke, save/restore, restart)."
