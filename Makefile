CC      = gcc
CFLAGS  = -g -O0 -Wall
TARGET  = raakatu-host

# Inform 6 / Z-machine Version 3 port. Version 3 is required by the native
# NitrOS-9 ZIP interpreter in infocom-os9-port.
INFORM              ?= inform
ZTERP               ?= dfrotz
ZTARGET               = raakatu.z3
INFOCOM_OS9_PORT     ?= $(HOME)/Projects/infocom-os9-port
ZDSKIMAGE             = raakatu-z3.dsk

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
# it's ever missing. Treated as a read-only template: diskcopy below copies
# it to $(BOOTDSK) rather than writing into it directly, so it never shows
# up dirty in git.
DSKIMAGE     = l2_coco3.dsk
BOOTDSK      = $(OS9TARGET).dsk
OS9COPY      = os9 copy -o=0 -r
OS9ATTR      = os9 attr -q
OS9ATTR_EXEC = $(OS9ATTR) -pe -npw -pr -e -w -r

diskcopy: $(OS9TARGET) $(DSKIMAGE)
	cp $(DSKIMAGE) $(BOOTDSK)
	$(OS9COPY) $(OS9TARGET) $(BOOTDSK),CMDS
	$(OS9ATTR_EXEC) $(BOOTDSK),CMDS/$(OS9TARGET)

MAME_BINARY  ?= mame
MAME_MACHINE ?= coco3
MAME_FLAGS   ?= -rompath $(MAME_ROM_PATH) -window -nothrottle -skip_gameinfo -autoboot_delay 5 -autoboot_command "DOS\n" -ext fdc -ext:fdc:wd17xx:0 525qd

run: diskcopy
	$(MAME_BINARY) $(MAME_MACHINE) $(MAME_FLAGS) -flop1 $(BOOTDSK)

zmachine: $(ZTARGET)

$(ZTARGET): zmachine/raakatu.inf zmachine/gamedata.inf
	$(INFORM) -v3 +include_path=. $< $@

zmachine/gamedata.inf: gamedata.c generate_zdata.py
	python3 generate_zdata.py

regen-zdata:
	python3 generate_zdata.py

check-zdata:
	python3 generate_zdata.py --check

test-zmachine: $(TARGET) $(ZTARGET) check-zdata
	ZTERP=$(ZTERP) ./test_zmachine.sh

$(ZDSKIMAGE): $(ZTARGET) $(INFOCOM_OS9_PORT)/zork.dsk $(INFOCOM_OS9_PORT)/infocom
	cp $(INFOCOM_OS9_PORT)/zork.dsk $@
	os9 copy -o=0 -r $(INFOCOM_OS9_PORT)/infocom $@,CMDS/infocom
	os9 attr -q -pe -npw -pr -e -w -r $@,CMDS/infocom
	os9 copy -o=0 -r $(ZTARGET) $@,raakatu.dat

zmachine-disk: $(ZDSKIMAGE)

run-zmachine: $(ZDSKIMAGE)
	$(MAME_BINARY) $(MAME_MACHINE) $(MAME_FLAGS) -flop1 $(ZDSKIMAGE)

regen-gamedata:
	python3 extract_data.py

clean:
	rm -rf $(TARGET) $(TARGET).dSYM raakatu.o gamedata.o $(OS9TARGET) \
		$(ZDSKIMAGE) *.list *.map decompile decompile.dSYM $(BOOTDSK)

.PHONY: all os9 clean regen-gamedata diskcopy run decompile zmachine regen-zdata \
	check-zdata test-zmachine zmachine-disk run-zmachine
