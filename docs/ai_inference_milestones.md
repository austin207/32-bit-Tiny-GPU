# AI Inference Milestones — 32-bit Tiny GPU

Custom 32-bit SIMT GPU built from scratch in SystemVerilog.  
Target process: SkyWater Sky130A 130nm (OpenLane 2, 300,884 std cells, 7.97 mm²).  
Verification: 76/76 cocotb tests passing.

---

## Milestone Table

| Phase | Kernel | Shape | Compute Mode | Blocks × Threads | Cycles | Feature Proved | Status |
|-------|--------|-------|--------------|-----------------|--------|----------------|--------|
| 8  | `phase8_mlp_inference`     | 4→4 Q8 MLP        | DOT4 (packed INT8)      | 1×4  | 103   | First neural-network kernel, SIMT parallelism, end-to-end inference pipeline | PASS |
| 9  | `phase9_ldr_regbase`       | LDR base test      | LDR/STR                 | 1×1, 1×4 | 27, 55 | General-purpose register (R0–R28) valid as LDR base in single and multi-thread SIMT mode after `lsu_done_latch` fix | PASS |
| 10 | `phase10_mlp_8out`         | 4→8 Q8 MLP        | DOT4 (packed INT8)      | 2×4  | 131   | Multi-block dispatch correctness: `neuron_id = BLOCK_IDX * 4 + THREAD_IDX`, block 0 → neurons 0–3, block 1 → neurons 4–7 | PASS |
| 11 | `phase11_mlp_8in`          | 8→4 Q8 MLP        | DOT4 ×2 accumulation    | 1×4  | 171   | Double-DOT4 accumulation per thread: 8-element dot product via two sequential DOT4 instructions using `rs3=rd` accumulator | PASS |
| 12 | `phase12_mlp_q6`           | 4→4 Q6 MLP        | DOT4 (packed INT8)      | 1×4  | 103   | Quantization scale is a kernel-level choice: SAR 6 (scale=64) instead of SAR 8 (scale=256), zero RTL changes | PASS |
| 13 | `phase13_digit_hidden`     | 16→4 hidden layer  | DOT4 (packed INT8)      | 1×4  | 279   | Two-pass classifier pass 1: packed INT8 DOT4 hidden layer writes `h[0..3]` to data memory for pass 2 | PASS |
| 14 | `phase14_digit_output`     | 4→4 output layer   | Scalar IMUL + ADD       | 1×4  | 314   | Two-pass classifier pass 2: scalar INT32 IMUL accumulation over INT32 hidden activations, demonstrates both compute modes in one pipeline | PASS |
| 15 | `phase15_digit64_hidden`   | 64→16 hidden layer | DOT4 ×16 accumulation   | 4×4  | 864   | True digit classifier hidden layer: 16 DOT4 instructions per thread, 4-block dispatch, 16 hidden neurons computed in parallel | PASS |
| 16 | `phase16_digit64_output`   | 16→10 output layer | Scalar IMUL + ADD ×16   | 3×4  | 990   | True 64→16→10 digit classifier: chained two-pass inference, 10 output classes, 2 padding lanes, argmax verified | PASS |

**Total two-pass inference (Phase 15 + 16): 1854 cycles**

---

## Memory Layouts

### Phase 8 — 4→4 Q8 MLP

```
mem[0..3]   = W_row[0..3]  packed INT8x4
mem[4..7]   = x replicated (INT8x4)
mem[8..11]  = y[0..3]      INT32 output
```

### Phase 10 — 4→8 (2 blocks)

```
mem[0..7]   = W_row[0..7]  packed INT8x4
mem[8]      = x            packed INT8x4  (single copy, GP-reg base load)
mem[12..19] = y[0..7]      INT32 output
```

### Phase 11 — 8→4 (2× DOT4)

```
mem[0,1]    = W_row_0_low, W_row_0_high
...
mem[6,7]    = W_row_3_low, W_row_3_high
mem[8]      = x_low   packed INT8x4
mem[9]      = x_high  packed INT8x4
mem[10..13] = y[0..3] INT32 output
```

### Phase 13/14 — Small two-pass classifier

```
mem[0..15]  = W_h[4][4]   packed INT8x4
mem[16..19] = x[4]        packed INT8x4
mem[20..23] = h[0..3]     INT32  (pass 1 output, pass 2 input)
mem[24..39] = W_o[4][4]   INT32 scalars
mem[40..43] = y[0..3]     INT32 output
```

### Phase 15/16 — True 64→16→10 classifier

```
mem[0..255]   = W_h[16][16]  packed INT8x4  (hidden weights)
mem[256..271] = x[64]        packed INT8x4  (16 words)
mem[272..287] = h[0..15]     INT32          (pass 1 output, pass 2 input)
mem[288..479] = W_o[12][16]  INT32 scalars  (10 real + 2 padding classes)
mem[480..491] = y[0..11]     INT32          (y[0..9] real, y[10..11] ignored)
```

---

## ISA Features Exercised

| Instruction | First used | Purpose |
|------------|-----------|---------|
| `DOT4`     | Phase 8   | Packed INT8×4 multiply-accumulate |
| `RELU`     | Phase 8   | Zero negative activations |
| `CLAMP`    | Phase 8   | Saturate to INT8 range [-128, 127] |
| `SAR`      | Phase 8   | Arithmetic right shift for requantization |
| `LDR`      | Phase 8   | Load weight and input words from data memory |
| `STR`      | Phase 8   | Write output activations to data memory |
| `CONST`    | Phase 8   | Load immediate constants (bases, shift amounts) |
| `MUL`      | Phase 10  | Compute `BLOCK_IDX * blockDim` for neuron addressing |
| `ADD`      | Phase 10  | Compute `neuron_id = block_offset + THREAD_IDX` |
| `SHL`      | Phase 15  | Compute `hidden_id * 16` weight base via shift |
| `IMUL`     | Phase 14  | Signed multiply for INT32 scalar accumulation |

---

## Kernel Patterns

### SIMT weight-addressing pattern

All parallel inference kernels use:

```
neuron_id = BLOCK_IDX * blockDim + THREAD_IDX
weight_base = neuron_id * weights_per_neuron
```

This is the direct equivalent of CUDA `blockIdx.x * blockDim.x + threadIdx.x`.

### DOT4 accumulation pattern

```
R3 = 0  (register reset default)
LDR R1, weight_base, k
LDR R2, x_base, k
DOT4 R3, R1, R2       // R3 += dot(INT8x4(R1), INT8x4(R2))
```

Second and subsequent DOT4 calls accumulate into `R3` via the `rs3=rd` encoding.

### Requantization pattern

```
CONST R5, shift        // shift = 8 for Q8, 6 for Q6
SAR   R4, R3, R5       // R4 = R3 >> shift  (arithmetic, sign-preserving)
RELU  R4, R4, R1       // R4 = max(0, R4)
CLAMP R4, R4, R1       // R4 = clamp(R4, -128, 127)
```

### Two-pass chained inference

Phase 15 and Phase 16 share the same `data_memory` dict in the cocotb test. Phase 15 writes `h[272..287]`. Phase 16 reads from those addresses without a memory clear between dispatches. This models host-managed weight/activation memory as used in real GPU inference pipelines.

---

## Quantization Comparison

| Kernel | Scale factor | Shift | Max useful weight | Notes |
|--------|-------------|-------|------------------|-------|
| Phase 8–16 (default) | 256 | SAR 8 | ±127 | Standard Q8 |
| Phase 12 | 64 | SAR 6 | ±127 | Q6, finer resolution |

Scale factor is a compile-time kernel constant, not a hardware parameter. Changing quantization requires only changing the `CONST` immediate passed to `SAR`.

---

## Dispatcher Behavior

The dispatcher assigns blocks to free cores round-robin. For `num_blocks > NUM_CORES`:

```
Initial:  core0→block0  core1→block1  core2→block2  core3→block3
core0 done → core0→block4
core1 done → core1→block5
...
```

Phase 15 (4 blocks, 4 cores) uses all 4 cores simultaneously.  
Phase 16 (3 blocks, 4 cores) uses 3 cores; core3 idles.

`dispatch_en` is a one-cycle launch pulse. Holding it high causes spurious re-launches.

---

## Verified Results

```
Phase 8  y[0..3]    = [20, 48, 25, 8]
Phase 10 y[0..7]    = [16, 37, 36, 15, 30, 0, 41, 0]
Phase 11 y[0..3]    = [20, 15, 28, 6]
Phase 12 y[0..3]    = [35, 89, 79, 49]
Phase 13 h[0..3]    = [42, 37, 0, 6]
Phase 14 y[0..3]    = [7, 5, 2, 5]  (argmax = class 0)
Phase 15 h[0..15]   = [7, 0, 0, 5, 0, 0, 2, 0, 0, 0, 0, 2, 0, 0, 3, 0]
Phase 16 y[0..9]    = [2, 0, 0, 0, 0, 0, 0, 0, 0, 0]  (argmax = class 0)
```

All verified against Python golden reference computed from the same weight/input values.

---

## Repository

```
https://github.com/austin207/32-bit-Tiny-GPU.git
```

Kernel source files: `assembler/examples/phase8_*.c` through `phase16_*.c`  
Cocotb tests: `Src/Top_level_GPU/tests/test_phase08_mlp.py` through `test_phase16_digit64_classifier.py`  
Assembler builds: `assembler/builds/bin/*.axelbin`