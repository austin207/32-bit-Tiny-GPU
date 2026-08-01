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
	rm -rf build $(TARGET) test_binaries

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
EXAMPLES = relu test_loopsum test_fmatest test_ifelse test_ltcheck test_matmultest test_dot4test test_chain1 test_chain2 test_chain3 test_divmod test_nestedfor attn_scores test_expif test_ifdiverge attn_softmax attn_weighted_v test_params

OUTDIR = test_binaries
HEXDIR = ../assembler/builds/hex
BINDIR = ../assembler/builds/bin

examples: $(TARGET)
	@mkdir -p $(OUTDIR) $(HEXDIR) $(BINDIR)
	@for k in $(EXAMPLES); do \
		./$(TARGET) examples/$$k.axelc -o $(OUTDIR)/$$k || exit 1; \
	done
	cp $(OUTDIR)/relu.hex           $(HEXDIR)/axelcc_relu.hex
	cp $(OUTDIR)/relu.axelbin       $(BINDIR)/axelcc_relu.axelbin
	@for k in test_loopsum test_fmatest test_ifelse test_ltcheck test_matmultest test_dot4test test_chain1 test_chain2 test_chain3 test_divmod test_nestedfor attn_scores test_expif test_ifdiverge attn_softmax attn_weighted_v test_params; do \
		cp $(OUTDIR)/$$k.hex     $(HEXDIR)/$$k.hex; \
		cp $(OUTDIR)/$$k.axelbin $(BINDIR)/$$k.axelbin; \
	done

.PHONY: all clean test examples