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
# test_nestedif.axelc and test_func_nested_reject.axelc are deliberately
# excluded: negative tests for sema.c's nested-if and nested-call rejection,
# both *supposed* to fail to compile.
EXAMPLES = relu test_loopsum test_fmatest test_ifelse test_ltcheck test_matmultest test_dot4test test_chain1 test_chain2 test_chain3 test_divmod test_nestedfor attn_scores test_expif test_ifdiverge attn_softmax attn_weighted_v test_params test_relu_builtin test_constfold test_fma_alias test_regreuse_stress test_clamp_builtin test_blockidx dscnn_dwconv dscnn_pwconv dscnn_stem_conv dscnn_maxpool dscnn_fc dscnn_softmax test_func_basic

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
	@for k in test_loopsum test_fmatest test_ifelse test_ltcheck test_matmultest test_dot4test test_chain1 test_chain2 test_chain3 test_divmod test_nestedfor attn_scores test_expif test_ifdiverge attn_softmax attn_weighted_v test_params test_relu_builtin test_constfold test_fma_alias test_regreuse_stress test_clamp_builtin test_blockidx dscnn_dwconv dscnn_pwconv dscnn_stem_conv dscnn_maxpool dscnn_fc dscnn_softmax test_func_basic; do \
		cp $(OUTDIR)/$$k.hex     $(HEXDIR)/$$k.hex; \
		cp $(OUTDIR)/$$k.axelbin $(BINDIR)/$$k.axelbin; \
	done

# Golden-output tests: compare compiled .hex instruction words against a
# hardcoded expected sequence (tests/golden_test.py). Depends on `examples`
# so it always runs against freshly rebuilt binaries -- catches codegen
# regressions without needing a full RTL simulation.
golden: examples
	python3 tests/golden_test.py

.PHONY: all clean test examples golden