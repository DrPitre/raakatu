# Raaka-Tu (C port)

A C port of the 1982 Tandy Color Computer text adventure *Raaka-Tu*,
originally written in 6809 assembly.

## Files

- `raakatu.c` — the game engine: a small bytecode VM that interprets the
  original game's data tables (rooms, objects, vocabulary, phrases, scripts).
- `gamedata.c` — the game's data tables, extracted from the original binary.
  **This file is checked in and verified against `raaka-tu.asm`** (see
  below) — do not regenerate it casually.
- `raaka-tu.asm` — an annotated, ground-truth disassembly of the original
  6809 binary; source for `extract_data.py`. Treated as read-only.
- `extract_data.py` — parses `raaka-tu.asm` and generates `gamedata.c`.
  Its output matches `raaka-tu.asm` byte-for-byte.
  A prior hand-patched `gamedata.c` had diverged from this at one table
  entry (room A6's `CLIMB HOLE` guard was dropped) — fixed by regenerating
  from `extract_data.py` and diffing before committing. Run via
  `make regen-gamedata` if you want to regenerate, but always diff against
  the checked-in copy before overwriting it.
- `test_game.sh` — a minimal smoke-test script.
- `l2_coco3.dsk` — a bootable NitrOS-9 Level 2 CoCo 3 floppy image, used to
  run the real OS-9 binary under emulation (see below).

## Build

```
make
./raakatu_test
```

## Running on OS-9 (MAME)

This builds the real 6809 binary with [cmoc](https://github.com/BackupGGCode/cmoc)
and boots it under [MAME](https://www.mamedev.org/) using the checked-in
NitrOS-9 disk image.

Prerequisites:

- `cmoc`, a 6809 C cross-compiler, plus its OS-9 runtime (`cmoc_os9`),
  checked out under `~/Projects/coco-shelf` (or point `COCO_SHELF` in the
  Makefile at wherever you have them).
- [Toolshed](https://github.com/boisy/toolshed)'s `os9` utility on your
  `PATH`, used to copy the built binary onto the disk image.
- `mame`, with a CoCo 3 ROM set available; point `MAME_ROM_PATH` at the
  directory containing it, e.g. `export MAME_ROM_PATH=$HOME/roms`.

Then:

```
make run
```

This cross-compiles `raakatu` via `os9` target, copies it onto
`l2_coco3.dsk` under `CMDS/`, and boots MAME with that disk in drive 0. Once
NitrOS-9 finishes booting to the `DOS` prompt, run:

```
raakatu
```

If you just want to rebuild the binary and copy it onto the disk without
launching MAME, use `make diskcopy` instead.

## Notes on RNG semantics

The original assembly's random-number opcode
(`is_less_equal_last_random`) never rolls a new random number — it just
re-reads a cached byte that's refreshed at exactly two sites in the whole
game: once per keystroke while reading input, and once per object with a
turn script, right before that script executes. A multi-threshold switch
(e.g. a monster's attack table) therefore buckets a *single* roll across
every branch, not one independent roll per branch. `raakatu.c` mirrors this
via a `g_last_random` cache (see comments in `raakatu.c` around
`op_cmp_rand`, `run_turn_scripts`, and `read_input`).

Because the RNG is seeded deterministically (`rand_seed` in `gamedata.c`),
the entire game is fully deterministic given a command sequence — retrying
the same commands never changes the outcome; only changing the command
sequence (and thus the number of prior rolls) does.
