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
* ReLU kernel execution on full GPU RTL

Known verified RTL test:

```text
tests.test_axelcc_relu.test_axelcc_relu PASS

input:
  mem[0] = 5
  mem[1] = -3
  mem[2] = 8
  mem[3] = -1

output:
  mem[4] = 5
  mem[5] = 0
  mem[6] = 8
  mem[7] = 0
```

The compiler-generated ReLU kernel currently executes on the full `Top_level_GPU` cocotb testbench.

---

## Directory Layout

```text
axelcc/
├── Makefile
├── README.md
├── examples/
│   └── relu.axelc
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

Compile an AXEL C source file:

```bash
cd ~/gpu-project/axelcc
./axelcc examples/relu.axelc
```

This generates:

```text
relu.hex
relu.axelbin
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

After compiling:

```bash
cd ~/gpu-project/axelcc
make clean && make
./axelcc examples/relu.axelc
```

Copy the generated output into the assembler build folders:

```bash
cd ~/gpu-project
mkdir -p assembler/builds/hex assembler/builds/bin

cp axelcc/relu.hex assembler/builds/hex/axelcc_relu.hex
cp axelcc/relu.axelbin assembler/builds/bin/axelcc_relu.axelbin
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

Maps to the GPU `DOT4` instruction.

Used for packed INT8 dot products.

### fma

```c
int y = fma(a, b, c);
```

Maps to the GPU fused multiply-add path if supported by the backend.

### exp8

```c
int y = exp8(x);
```

Reserved for approximate exponential / transformer-style kernels.

### mmio_matmul

```c
mmio_matmul(a_base, b_base, c_base, M, N, K, scale);
```

Reserved for launching the MMIO matmul accelerator.

Current Phase 21 accelerator is verified separately through hand-written assembly/C kernel flow.

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

The generated structure is conceptually:

```text
CMP lhs, rhs
BRnzp condition_mask, sync_offset, branch_offset

else_body
SYNC

then_body
SYNC
```

This matches the GPU's divergence/reconvergence stack behavior.

Nested `if` statements are not supported yet.

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
axelcc/*.hex
axelcc/*.axelbin
```

Recommended `.gitignore` entries:

```gitignore
# axelcc generated files
axelcc/axelcc
axelcc/build/
axelcc/*.hex
axelcc/*.axelbin
```

---

## Current Verification

The compiler has been validated with a ReLU kernel on full GPU RTL.

Verified behavior:

```text
input  = [5, -3, 8, -1]
output = [5,  0, 8,  0]
```

Test:

```bash
cd ~/gpu-project/Src/Top_level_GPU
make COCOTB_TEST_MODULES=tests.test_axelcc_relu
```

Expected:

```text
tests.test_axelcc_relu.test_axelcc_relu PASS
```

---

## Known Limitations

Current limitations:

1. No full kernel parameter ABI in RTL test flow.
2. One kernel per source file.
3. No nested `if`.
4. No general function calls.
5. No pointer support.
6. No local arrays.
7. No optimizer.
8. Generated code is longer than hand-written AXEL assembly.
9. Register allocation is simple and not spill-aware.
10. `.axelbin` metadata fields are mostly placeholders.
11. `mmio_matmul` builtin is reserved but not yet fully integrated through axelcc-generated kernels.
12. Transformer kernels are not yet implemented.

---

## Development Roadmap

Near-term:

* Add compiler README and lock current ReLU verification.
* Add more compiler examples.
* Add tests for generated `.hex` and `.axelbin`.
* Add parameter ABI or host-side launch argument loading.
* Add axelcc-generated DOT4 matvec test.
* Add axelcc-generated Q8 matmul test.
* Add axelcc lowering for MMIO matmul launch.
* Begin Phase 5 transformer kernels.

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
make clean && make
./axelcc examples/relu.axelc

cd ~/gpu-project
mkdir -p assembler/builds/hex assembler/builds/bin
cp axelcc/relu.hex assembler/builds/hex/axelcc_relu.hex
cp axelcc/relu.axelbin assembler/builds/bin/axelcc_relu.axelbin

cd ~/gpu-project/Src/Top_level_GPU
make COCOTB_TEST_MODULES=tests.test_axelcc_relu
```

Expected:

```text
TESTS=1 PASS=1 FAIL=0 SKIP=0
```

---

## Notes

`axelcc` is currently a bring-up compiler, not a production compiler.

Its purpose is to reduce hand-written assembly effort and enable higher-level kernel development for the AXEL GPU project. It is already sufficient for simple SIMT kernels such as ReLU and is the base for future transformer/ML kernel generation.
