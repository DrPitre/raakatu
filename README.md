# Raaka-Tu (C port)

A C port of the 1982 Tandy Color Computer text adventure *Raaka-Tu*,
originally written in 6809 assembly.

## Files

- `raakatu.c` — the game engine: a small bytecode VM that interprets the
  original game's data tables (rooms, objects, vocabulary, phrases, scripts).
- `gamedata.c` — the game's data tables, extracted from the original binary.
  **This file is checked in and verified against `raakatu_gold.asm`** (see
  below) — do not regenerate it casually.
- `raaka-tu.asm` — a disassembly of the original 6809 binary; source for
  `extract_data.py`.
- `raakatu_gold.asm` — an annotated, ground-truth disassembly used as the
  reference when tracing opcode/game-logic behavior. Treated as read-only.
- `extract_data.py` — parses `raaka-tu.asm` and generates `gamedata.c`.
  Its output matches `raaka-tu.asm` and `raakatu_gold.asm` byte-for-byte.
  A prior hand-patched `gamedata.c` had diverged from this at one table
  entry (room A6's `CLIMB HOLE` guard was dropped) — fixed by regenerating
  from `extract_data.py` and diffing before committing. Run via
  `make regen-gamedata` if you want to regenerate, but always diff against
  the checked-in copy before overwriting it.
- `test_game.sh` — a minimal smoke-test script.

## Build

```
make
./raakatu_test
```

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
