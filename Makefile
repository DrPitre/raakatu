CC      = gcc
CFLAGS  = -g -O0 -Wall
TARGET  = raakatu-host

# cmoc (6809 C cross-compiler, from ~/Projects/coco-shelf) builds the real
# NitrOS-9 command binary, as opposed to $(TARGET) above which is a native
# build used only for testing game logic on the host.
COCO_SHELF   = $(HOME)/Projects/coco-shelf
CMOC         = $(COCO_SHELF)/bin/cmoc
CMOC_OS9_DIR = $(COCO_SHELF)/cmoc_os9
CMOC_CPP     = --cpp="cpp -Wno-builtin-macro-redefined"
CMOCFLAGS    = $(CMOC_CPP) --os9 -nodefaultlibs -I$(CMOC_OS9_DIR)/include --add-os9-stack-space=16384
CMOCLFLAGS   = -L$(CMOC_OS9_DIR)/lib -lc
OS9TARGET    = raakatu

all: $(TARGET)

# gamedata.c is checked in and verified against raaka-tu.asm -- do NOT
# regenerate it from extract_data.py by default. A regen currently produces
# slightly different room_data bytes than this verified copy (see README).
$(TARGET): raakatu.c gamedata.c
	$(CC) $(CFLAGS) -o $(TARGET) raakatu.c gamedata.c

# Host-only tool: dumps room_data/obj_data/cmd_data/etc as readable
# pseudocode, for scoping a port to another engine. Not part of the game.
decompile: decompile.c gamedata.c
	$(CC) $(CFLAGS) -o decompile decompile.c gamedata.c

os9: $(OS9TARGET)

raakatu.o: raakatu.c
	$(CMOC) $(CMOCFLAGS) --compile -o $@ raakatu.c

gamedata.o: gamedata.c
	$(CMOC) $(CMOCFLAGS) --compile -o $@ gamedata.c

$(OS9TARGET): raakatu.o gamedata.o
	$(CMOC) $(CMOCFLAGS) -o $@ raakatu.o gamedata.o $(CMOCLFLAGS)

# Local copy of the bootable NitrOS-9 Level 2 CoCo 3 floppy image, built via
# `make` in ~/Projects/coco-shelf/nitros9/recipes/coco3/floppy and copied
# here. Not rebuilt by this Makefile -- regenerate it there and re-copy if
# it's ever missing.
DSKIMAGE     = l2_coco3.dsk
OS9COPY      = os9 copy -o=0 -r
OS9ATTR      = os9 attr -q
OS9ATTR_EXEC = $(OS9ATTR) -pe -npw -pr -e -w -r

diskcopy: $(OS9TARGET) $(DSKIMAGE)
	$(OS9COPY) $(OS9TARGET) $(DSKIMAGE),CMDS
	$(OS9ATTR_EXEC) $(DSKIMAGE),CMDS/$(OS9TARGET)

MAME_BINARY  ?= mame
MAME_MACHINE ?= coco3
MAME_FLAGS   ?= -rompath $(MAME_ROM_PATH) -window -nothrottle -skip_gameinfo -autoboot_delay 5 -autoboot_command "DOS\n" -ext fdc -ext:fdc:wd17xx:0 525qd

run: diskcopy
	$(MAME_BINARY) $(MAME_MACHINE) $(MAME_FLAGS) -flop1 $(DSKIMAGE)

regen-gamedata:
	python3 extract_data.py

clean:
	rm -rf $(TARGET) $(TARGET).dSYM raakatu.o gamedata.o $(OS9TARGET) *.list *.map decompile decompile.dSYM

.PHONY: all os9 clean regen-gamedata diskcopy run decompile
