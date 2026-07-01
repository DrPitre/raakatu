CC      = gcc
CFLAGS  = -g -O0 -Wall
TARGET  = raakatu_test

# cmoc (6809 C cross-compiler, from ~/Projects/coco-shelf) builds the real
# NitrOS-9 command binary, as opposed to $(TARGET) above which is a native
# build used only for testing game logic on the host.
COCO_SHELF   = $(HOME)/Projects/coco-shelf
CMOC         = $(COCO_SHELF)/bin/cmoc
CMOC_OS9_DIR = $(COCO_SHELF)/cmoc_os9
CMOC_CPP     = --cpp="cpp -Wno-builtin-macro-redefined"
CMOCFLAGS    = $(CMOC_CPP) --os9 -nodefaultlibs -I$(CMOC_OS9_DIR)/include
CMOCLFLAGS   = -L$(CMOC_OS9_DIR)/lib -lc
OS9TARGET    = raakatu

all: $(TARGET)

# gamedata.c is checked in and verified against raakatu_gold.asm -- do NOT
# regenerate it from extract_data.py by default. A regen currently produces
# slightly different room_data bytes than this verified copy (see README).
$(TARGET): raakatu.c gamedata.c
	$(CC) $(CFLAGS) -o $(TARGET) raakatu.c gamedata.c

os9: $(OS9TARGET)

raakatu.o: raakatu.c
	$(CMOC) $(CMOCFLAGS) --compile -o $@ raakatu.c

gamedata.o: gamedata.c
	$(CMOC) $(CMOCFLAGS) --compile -o $@ gamedata.c

$(OS9TARGET): raakatu.o gamedata.o
	$(CMOC) $(CMOCFLAGS) -o $@ raakatu.o gamedata.o $(CMOCLFLAGS)

regen-gamedata:
	python3 extract_data.py

clean:
	rm -rf $(TARGET) $(TARGET).dSYM raakatu.o gamedata.o $(OS9TARGET) *.list *.map

.PHONY: all os9 clean regen-gamedata
