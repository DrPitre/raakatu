# Raaka-Tu reference implementation and Z-machine source

This repository preserves and documents the 1982 Tandy Color Computer text
adventure *Raaka-Tu*, originally written in 6809 assembly.

## Preferred game distribution

The preferred place to obtain and play the packaged game is the
[infocom-os9-port repository](https://github.com/rlucente-retro/infocom-os9-port),
which bundles `raakatu.dat` with the native NitrOS-9 Infocom interpreter and
includes it in the generated OS-9 disk image.

The C implementation in this repository is retained for reference purposes
only. It documents the original engine, provides a convenient behavioral
oracle, and is used to verify that the Z-machine port produces the same full
playthrough. It is not the preferred distributed version of the game.

The repository also contains a standalone Inform 6 port targeting Version 3
of Infocom's Z-machine. Version 3 is intentional: the native NitrOS-9 ZIP
interpreter in `~/Projects/infocom-os9-port` runs V3 story files.

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
- `full_playthrough.txt` — a narrated walkthrough achieving the maximum
  score (50/50), followed by the raw command sequence that produces it.
- `zmachine/raakatu.inf` — the standalone Inform 6 V3 runtime. It interprets
  the same Raaka-Tu bytecode as the C port rather than replacing the game with
  Inform library rooms and actions.
- `zmachine/gamedata.inf` — checked-in Inform byte arrays generated from the
  verified `gamedata.c` snapshot.
- `generate_zdata.py` — regenerates or verifies the Inform arrays without
  rewriting `gamedata.c` or `raaka-tu.asm`.
- `test_zmachine.sh` — compares the complete Z-machine playthrough with the C
  engine after normalizing terminal wrapping and the V3 status line.
- `l2_coco3.dsk` — a bootable NitrOS-9 Level 2 CoCo 3 floppy image, used to
  run the real OS-9 binary under emulation (see below).

## Build

```
make
./raakatu-host
```

## Z-machine Version 3

Prerequisites:

- Inform 6 (`inform`) to compile the story file.
- A command-line Z-machine interpreter such as `dfrotz` for host-side tests.
- The NitrOS-9 interpreter repository at `~/Projects/infocom-os9-port` for the
  real OS-9 target. Override `INFOCOM_OS9_PORT` if it is elsewhere.

Build and test the story file:

```
make zmachine
make test-zmachine
```

This produces `raakatu.z3`. The test runs both engines through the full
walkthrough and requires identical normalized output and a final score of
50/50.

To create a separate bootable disk without changing either checked-in disk
image:

```
make zmachine-disk
make run-zmachine
```

At the NitrOS-9 prompt, run:

```
infocom raakatu.dat
```

The story adds `SAVE`, `RESTORE`, and `RESTART` as V3 meta-commands. `QUIT`
retains the original game's behavior. V3 has no undo opcode, so `UNDO` is not
provided. The V3 input opcode returns the completed line rather than each raw
keystroke; therefore erased and overflow keystrokes cannot affect the custom
RNG, while normal command sequences remain byte-for-byte deterministic with
the C port.

Regenerate or verify the Inform game-data snapshot with:

```
make regen-zdata
make check-zdata
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
