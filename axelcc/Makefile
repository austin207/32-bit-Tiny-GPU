CC     = gcc
CFLAGS = -Wall -Wextra -std=c11 -g -Isrc
SRC    = $(wildcard src/*.c)
OBJ    = $(SRC:src/%.c=build/%.o)
TARGET = axelcc

all: $(TARGET)

$(TARGET): $(OBJ)
	$(CC) $(CFLAGS) -o $@ $^

build/%.o: src/%.c | build
	$(CC) $(CFLAGS) -c -o $@ $<

build:
	mkdir -p build

clean:
	rm -rf build $(TARGET)

test: $(TARGET)
	./$(TARGET) --tokens examples/relu.axelc

# Every valid (compiles successfully) example kernel, recompiled fresh and
# copied into assembler/builds/ on every run. Depends on $(TARGET), so make's
# own incremental rebuild kicks in if src/*.c changed -- this is what closes
# the "edited codegen.c but never rebuilt axelcc before recompiling" class of
# bug for good (see matmultest hang, axelcc verification session 2/3).
#
# test_nestedif.axelc is deliberately excluded: it's a negative test for
# sema.c's nested-if rejection and is *supposed* to fail to compile.
EXAMPLES = relu test_loopsum test_fmatest test_ifelse test_ltcheck test_matmultest test_dot4test

HEXDIR = ../assembler/builds/hex
BINDIR = ../assembler/builds/bin

examples: $(TARGET)
	@mkdir -p $(HEXDIR) $(BINDIR)
	@for k in $(EXAMPLES); do \
		./$(TARGET) examples/$$k.axelc || exit 1; \
	done
	cp relu.hex           $(HEXDIR)/axelcc_relu.hex
	cp relu.axelbin       $(BINDIR)/axelcc_relu.axelbin
	@for k in test_loopsum test_fmatest test_ifelse test_ltcheck test_matmultest test_dot4test; do \
		cp $$k.hex     $(HEXDIR)/$$k.hex; \
		cp $$k.axelbin $(BINDIR)/$$k.axelbin; \
	done

.PHONY: all clean test examples