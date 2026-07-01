CC      = gcc
CFLAGS  = -g -O0 -Wall
TARGET  = raakatu_test

all: $(TARGET)

# gamedata.c is checked in and verified against raakatu_gold.asm -- do NOT
# regenerate it from extract_data.py by default. A regen currently produces
# slightly different room_data bytes than this verified copy (see README).
$(TARGET): raakatu.c gamedata.c
	$(CC) $(CFLAGS) -o $(TARGET) raakatu.c gamedata.c

regen-gamedata:
	python3 extract_data.py

clean:
	rm -rf $(TARGET) $(TARGET).dSYM

.PHONY: all clean regen-gamedata
