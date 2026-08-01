# axelcc — AXEL C Subset Compiler

`axelcc` is a small C-like compiler for the custom 32-bit Tiny GPU / AXEL GPU project.

It compiles a restricted kernel-oriented C subset into AXEL GPU machine code and emits:

* `.hex` instruction files for cocotb / RTL simulation
* `.axelbin` binary kernel files using the `AXLB` format

The current compiler is intended for small GPU kernels, ISA validation, and early ML/transformer kernel bring-up.

---

## Current Status

Verified working:

* Lexer
* Parser
* AST generation
* Semantic checks
* Register allocation
* Code generation
* `.hex` emission
* `.axelbin` emission using `AXLB` format
* `if`/`else` (both branches, uniform and divergent data)
* `for` loops (`<`-only condition)
* `dot4()` builtin -> packed INT8x4 `DOT4` opcode (`0x16`)
* `fma()` builtin -> scalar `FMA` opcode (`0x0C`)
* `mmio_matmul()` builtin -> full MMIO matmul accelerator launch + poll sequence
* All of the above executing on the full GPU RTL (`Top_level_GPU` cocotb testbench)

Known verified RTL tests (`Src/Top_level_GPU/tests/test_axelcc_*.py`):

```text
tests.test_axelcc_relu.test_axelcc_relu                      PASS
tests.test_axelcc_loopsum.test_axelcc_loopsum                 PASS
tests.test_axelcc_fmatest.test_axelcc_fmatest                 PASS
tests.test_axelcc_ifelse.test_axelcc_ifelse_then_branch       PASS
tests.test_axelcc_ifelse.test_axelcc_ifelse_else_branch       PASS
tests.test_axelcc_ltcheck.test_axelcc_ltcheck_true             PASS
tests.test_axelcc_ltcheck.test_axelcc_ltcheck_false            PASS
tests.test_axelcc_matmultest.test_axelcc_matmultest            PASS
tests.test_axelcc_dot4test.test_axelcc_dot4test                PASS
```

Two real compiler bugs were found and fixed during verification of the
else-branch/false-branch and `dot4()`/matmul cases (both only manifested
once real regression tests existed to exercise them):

* **`STMT_IF` else-branch fallthrough** — codegen had no instruction to skip
  the `then` body when the branch was not taken, so control flow walked
  through both bodies and the `then` body's write always won last,
  regardless of the actual condition. Fixed by emitting an unconditional
  `BRnzp` after the `else` body that jumps past the `then` body. See
  "SIMT Branching Model" below for the corrected layout.
* **`EXPR_DOT4` wrong opcode** — `dot4(a, b)` calls were silently lowered
  to `emit_fma()` (opcode `0x0C`, one 32-bit scalar multiply-add) instead
  of the packed INT8x4 `DOT4` opcode (`0x16`). Fixed by adding a dedicated
  `emit_dot()` and wiring `EXPR_DOT4` to it.

A third bug (`test_matmultest` hanging for 100k cycles) turned out not to be
a compiler-logic bug at all: the `axelcc` *binary* had gone stale relative
to a source fix in `codegen.c` and was never rebuilt before being used to
recompile the test kernel. See "Build" below — `make examples` now closes
this off structurally by always rebuilding `axelcc` from source before
recompiling any kernel.

---

## Directory Layout

```text
axelcc/
├── Makefile
├── README.md
├── examples/
│   ├── relu.axelc
│   ├── test_loopsum.axelc
│   ├── test_fmatest.axelc
│   ├── test_ifelse.axelc
│   ├── test_ltcheck.axelc
│   ├── test_matmultest.axelc
│   ├── test_dot4test.axelc
│   └── test_nestedif.axelc      (negative test -- deliberately rejected by sema.c)
├── test_binaries/                (generated .hex/.axelbin output, gitignored, made by `make examples`)
└── src/
    ├── ast.c / ast.h
    ├── codegen.c / codegen.h
    ├── emit.c / emit.h
    ├── lexer.c / lexer.h
    ├── main.c
    ├── parser.c / parser.h
    ├── sema.c / sema.h
    └── writer.c / writer.h
```

---

## Build

From the compiler directory:

```bash
cd ~/gpu-project/axelcc
make clean && make
```

This builds the compiler executable:

```text
axelcc/axelcc
```

---

## Usage

Compile an AXEL C source file. With no `-o`, output lands in the current
directory using the input's stem as the base name:

```bash
cd ~/gpu-project/axelcc
./axelcc examples/relu.axelc
```

This generates:

```text
relu.hex
relu.axelbin
```

To keep the compiler directory clean, pass `-o` to write into
`test_binaries/` instead (this is what `make examples` does for every
kernel):

```bash
mkdir -p test_binaries
./axelcc examples/relu.axelc -o test_binaries/relu
```

The `.hex` file contains one 32-bit instruction per line.

The `.axelbin` file contains a binary kernel package using the `AXLB` format.

---

## Example Kernel

```c
// relu.axelc
// Each thread loads input[threadIdx], applies ReLU, and stores output[threadIdx].

kernel void simt_relu() {
    int tid = threadIdx;
    int val = mem[tid];

    if (val > 0) {
        // val remains unchanged
    } else {
        val = 0;
    }

    mem[4 + tid] = val;
    return;
}
```

Expected memory layout:

```text
input:
  mem[0..3]

output:
  mem[4..7]
```

---

## Running the Compiler Output on RTL

Recommended: `make examples` rebuilds `axelcc` from source (via normal
`make` incremental rebuild -- it only relinks if `src/*.c` changed) and
recompiles every valid example kernel fresh, copying the `.hex`/`.axelbin`
output into `assembler/builds/hex/` and `assembler/builds/bin/`:

```bash
cd ~/gpu-project/axelcc
make examples
```

This is also run automatically as part of the root `make test` (see the
root `Makefile`'s `assembler` target), so every full test run always
exercises a freshly-built compiler and freshly-compiled kernels -- no
manual copy step, and no risk of a stale `axelcc` binary being used to
produce a test's `.hex` file (a real bug hit during verification, see
"Current Status" above).

Manual/single-kernel version, if you just want to compile and copy one file:

```bash
cd ~/gpu-project/axelcc
make clean && make
mkdir -p test_binaries
./axelcc examples/relu.axelc -o test_binaries/relu

cd ~/gpu-project
mkdir -p assembler/builds/hex assembler/builds/bin
cp axelcc/test_binaries/relu.hex assembler/builds/hex/axelcc_relu.hex
cp axelcc/test_binaries/relu.axelbin assembler/builds/bin/axelcc_relu.axelbin
```

Run the full GPU RTL test:

```bash
cd ~/gpu-project/Src/Top_level_GPU
make COCOTB_TEST_MODULES=tests.test_axelcc_relu
```

Expected result:

```text
TESTS=1 PASS=1 FAIL=0 SKIP=0
```

---

## Language Subset

The compiler supports a restricted C-like syntax designed for GPU kernels.

### Kernel Declaration

```c
kernel void name() {
    ...
}
```

Kernel parameters are supported syntactically:

```c
kernel void name(int in_base, int out_base) {
    ...
}
```

However, the current RTL test flow does not yet provide a full kernel parameter ABI. For RTL tests, prefer hardcoded memory bases until a parameter-loading ABI is added.

---

## Supported Types

Only 32-bit integer variables are supported:

```c
int x;
int y = 5;
```

There is no support yet for:

* pointers
* arrays as local variables
* structs
* floating point
* function calls except builtins
* multiple kernels per file

---

## Memory Access

Global memory is accessed through `mem[...]`.

Examples:

```c
int x = mem[0];
int y = mem[base + tid];

mem[4 + tid] = x;
```

Memory addresses are word addresses, not byte addresses.

---

## Special Registers

The compiler exposes GPU special registers as keywords:

```c
threadIdx
blockIdx
blockDim
```

Current register mapping:

```text
threadIdx -> R29
blockIdx  -> R30
blockDim  -> R31
```

---

## Register Allocation

Current register convention:

```text
R0   -> zero register
R1+  -> kernel parameters / user variables
R20-R27 -> compiler temporaries
R28  -> reserved helper constant register
R29  -> threadIdx
R30  -> blockIdx
R31  -> blockDim
```

User variables are allocated sequentially.

The current practical limit is around 19 user-visible registers before temporary register conflicts become likely.

---

## Supported Statements

### Variable Declaration

```c
int x = 5;
int tid = threadIdx;
```

### Assignment

```c
x = 10;
x = y + z;
```

### Memory Load

```c
int val = mem[tid];
```

### Memory Store

```c
mem[4 + tid] = val;
```

### If / Else

```c
if (val > 0) {
    // then body
} else {
    val = 0;
}
```

### Return

```c
return;
```

---

## Supported Operators

Arithmetic:

```text
+
-
*
```

Comparisons:

```text
>
<
==
!=
>=
<=
```

Current comparison support depends on the backend branch/NZP lowering.

---

## Builtins

The compiler includes builtins for GPU/ML instructions.

### dot4

```c
int y = dot4(a, b);
```

Maps to the GPU `DOT4` instruction (opcode `0x16`, `emit_dot()`): four
independent signed INT8 lane multiplies packed into the two 32-bit operand
words, summed. Not the same circuit as `fma()` below -- same instruction
shape (4 register operands), different math. Verified by
`test_axelcc_dot4test`.

### fma

```c
int y = fma(a, b, c);
```

Maps to the GPU `FMA` instruction (opcode `0x0C`, `emit_fma()`): a plain
32-bit scalar multiply-add, `rd = rs1*rs2 + rs3`. Verified by
`test_axelcc_fmatest`.

### exp8

```c
int y = exp8(x);
```

Reserved for approximate exponential / transformer-style kernels.

### mmio_matmul

```c
mmio_matmul(a_base, b_base, c_base, M, N, K, scale);
```

Launches the MMIO matmul accelerator: writes all seven ctrl registers
(`A_BASE..SCALE`) at `0x1F0..0x1F6`, writes `START` at `0x1F7`, then polls
`DONE` at `0x1F8` in a loop until it reads nonzero. Verified by
`test_axelcc_matmultest` against the same golden data as the hand-assembled
Phase 21 kernel (`assembler/examples/phase21_accel_matmul.c`) -- 16/16
correct `C` matrix elements, 724 cycles.

---

## SIMT Branching Model

The compiler lowers `if/else` into the GPU SIMT branch model using:

* `CMP`
* `BRnzp`
* `SYNC`

For an if/else block:

```c
if (condition) {
    then_body;
} else {
    else_body;
}
```

The generated structure is:

```text
CMP lhs, rhs
BRnzp condition_mask, S1, B1     -- taken: jump to the first SYNC below

else_body
BRnzp ALL, S2, B2                -- not-taken: unconditional skip past then_body
SYNC                             -- taken lands here, falls through into then_body

then_body
SYNC                             -- full reconvergence
```

Each thread's PC advances every cycle based on its own stored NZP flags,
independent of whether the scheduler's divergence-detection logic fires
(`core.sv`: `pc_en & active_mask[i]` gates the update, but the
branch/fall-through decision itself is per-thread). Divergence detection
only decides which threads get frozen for later cycles -- it has no bearing
on whether a single thread, or a uniform group, follows its own branch. The
unconditional `BRnzp` after `else_body` is therefore required unconditionally,
not just under real per-thread divergence: without it, a not-taken thread has
nothing to jump over `then_body` with, and falls straight through into it,
so the `then_body`'s write silently wins even when the condition was false.

The unconditional skip is always taken uniformly by whichever group
currently holds `active_mask` (its `nzp_mask` is `ALL`, always matching),
so it never triggers `divergence_detected` and does not disturb the real
per-thread divergence/warp-stack reconvergence mechanism used when the
condition genuinely differs across threads.

Nested `if` statements are not supported. This is enforced by `sema.c`
(`if_depth >= 1` is rejected) and covered by a negative-test example,
`examples/test_nestedif.axelc`, which is expected to fail to compile.

---

## Output Formats

### `.hex`

Plain text instruction output.

Example:

```text
043D0000
3E810000
04540000
46800000
...
```

Used directly by cocotb tests that load instruction memory manually.

### `.axelbin`

Binary kernel package.

Header format:

```text
Offset  Size  Field
0       4     magic       "AXLB"
4       1     version     0x01
5       1     flags       0x00
6       2     reserved
8       4     num_blocks
12      4     blockDim
16      4     text_words
20      4     data_words
24      4     entry_point
28      4     reserved
```

After the 32-byte header:

```text
text segment: text_words x uint32
data segment: data_words x uint32
```

The compiler currently emits:

```text
num_blocks  = 0
blockDim    = 0
entry_point = 0
data_words  = 0
```

The host/testbench can override launch configuration.

---

## Generated Files

The following are generated and should not be committed:

```text
axelcc/axelcc
axelcc/build/
axelcc/test_binaries/
```

Recommended `.gitignore` entries (already in the repo's root `.gitignore`):

```gitignore
# axelcc generated files
axelcc/axelcc
axelcc/build/
axelcc/test_binaries/
```

---

## Current Verification

The compiler has been validated on full GPU RTL across 9 cocotb tests
covering `if`/`else` (both branches), `for` loops, `dot4()`, `fma()`, and
`mmio_matmul()`.

Test:

```bash
cd ~/gpu-project/Src/Top_level_GPU
make COCOTB_TEST_MODULES=tests.test_axelcc_relu,tests.test_axelcc_loopsum,tests.test_axelcc_fmatest,tests.test_axelcc_ifelse,tests.test_axelcc_ltcheck,tests.test_axelcc_matmultest,tests.test_axelcc_dot4test
```

Expected:

```text
TESTS=9 PASS=9 FAIL=0 SKIP=0
```

Or, from the repo root, `make test` runs these alongside every other RTL
module's own testbenches (323/323 tests passing project-wide as of this
writing).

---

## Known Limitations

Current limitations:

1. No full kernel parameter ABI in RTL test flow -- kernel parameters
   parse but nothing loads registers with caller values; use hardcoded
   `mem[]` addresses in RTL test kernels instead.
2. One kernel per source file.
3. No nested `if` (enforced by `sema.c`, by design -- not a bug to fix).
4. No general function calls.
5. No pointer support.
6. No local arrays.
7. No optimizer.
8. Generated code is longer than hand-written AXEL assembly.
9. Register allocation is simple and not spill-aware.
10. `.axelbin` metadata fields are mostly placeholders.
11. `for` loops only support a `<` condition (hardcoded in `parser.c`).
12. Transformer kernels are not yet implemented -- blocked on missing
    infra for reloading program memory between sequential kernel launches
    in the cocotb test environment, not on compiler support.

---

## Development Roadmap

Done:

* ~~Add more compiler examples.~~ (loopsum, fmatest, ifelse, ltcheck, matmultest, dot4test, nestedif)
* ~~Add axelcc-generated DOT4 matvec test.~~ (`test_axelcc_dot4test`, and fixed a real `EXPR_DOT4` opcode bug in the process)
* ~~Add axelcc lowering for MMIO matmul launch.~~ (`test_axelcc_matmultest`, hardware-verified against Phase 21's golden data)
* ~~Fix `if`/`else` else-branch codegen bug.~~ (uniform/non-divergent conditions previously fell through into the `then` body)

Near-term:

* Add tests for generated `.hex` and `.axelbin` themselves (golden-output tests), not just RTL execution.
* Add parameter ABI or host-side launch argument loading.
* Add axelcc-generated Q8 matmul test (beyond the single MMIO-accelerator path).
* Build sequential-kernel-launch infra in the cocotb harness, then begin Phase 5 transformer kernels.

Longer-term:

* Add basic optimizer passes.
* Add constant folding.
* Add dead code elimination.
* Improve register allocation.
* Add local array support.
* Add better diagnostics.
* Add frontend tests for lexer/parser/sema.
* Add compiler golden-output tests.
* Add multi-kernel package support.

---

## Clean Build

```bash
cd ~/gpu-project/axelcc
make clean
make
```

---

## Smoke Test

```bash
cd ~/gpu-project/axelcc
make examples

cd ~/gpu-project/Src/Top_level_GPU
make COCOTB_TEST_MODULES=tests.test_axelcc_relu
```

Expected:

```text
TESTS=1 PASS=1 FAIL=0 SKIP=0
```

Or just run `make test` from the repo root, which does all of the above for
every kernel automatically.

---

## Notes

`axelcc` is currently a bring-up compiler, not a production compiler.

Its purpose is to reduce hand-written assembly effort and enable higher-level kernel development for the AXEL GPU project. It is already sufficient for simple SIMT kernels such as ReLU and is the base for future transformer/ML kernel generation.
