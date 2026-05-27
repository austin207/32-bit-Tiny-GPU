# 32-Bit Tiny GPU

A fully parameterized 32-bit GPU architecture implemented in SystemVerilog, built from scratch with a custom ISA, AXEL C assembler, cocotb-based verification, and an end-to-end neural network training and inference pipeline running on the simulated hardware.

---

## What This Is

This project implements a complete GPU stack entirely from scratch:

- Custom 32-bit ISA (21 instructions, 4 formats)
- SystemVerilog RTL with 12 modules, fully parameterized
- AXEL C assembler library that emits `.hex` kernels
- cocotb/Icarus Verilog simulation and verification suite
- A 4×4 linear layer neural network that trains on the GPU and runs inference

The GPU trains a matrix multiplication kernel over 20 epochs in Q8 fixed-point arithmetic, converges to within 2.5% of the target, and runs inference with a single `make infer`.

---

## Architecture Overview

```
Host CPU
    │
    ▼
┌──────────────────────────────────────────────────────┐
│                     GPU (Top Level)                  │
│                                                      │
│  ┌──────┐    ┌────────────┐    ┌─────────────────┐   │
│  │ DCR  │───►│ Dispatcher │───►│   Core (×N)     │   │
│  └──────┘    └────────────┘    │                 │   │
│                                │  ┌───────────┐  │   │
│                                │  │ Scheduler │  │   │
│                                │  ├───────────┤  │   │
│                                │  │  Fetcher  │  │   │
│                                │  ├───────────┤  │   │
│                                │  │  Decoder  │  │   │
│                                │  ├───────────┤  │   │
│                                │  │ ALU (×T)  │  │   │
│                                │  ├───────────┤  │   │
│                                │  │ LSU (×T)  │  │   │
│                                │  ├───────────┤  │   │
│                                │  │  PC (×T)  │  │   │
│                                │  ├───────────┤  │   │
│                                │  │RegFile(×T)│  │   │
│                                │  └───────────┘  │   │
│                                └─────────────────┘   │
│                                         │            │
│                              ┌───────────────────┐   │
│                              │ Memory Controller │   │
│                              └───────────────────┘   │
└──────────────────────────────────────┬───────────────┘
                                       │
                              Program + Data Memory
```

**N** = NUM_CORES (default: 4)
**T** = THREADS_PER_CORE (default: 4)
**Total threads** = N × T (default: 16)

---

## Instruction Set Architecture (ISA)

32-bit fixed-width instructions. 6-bit opcode field. Four instruction formats:

```
R-type: [31:26] opcode | [25:21] Rd | [20:16] Rs1 | [15:11] Rs2 | [10:6] Rs3 | [5:0] unused
I-type: [31:26] opcode | [25:21] Rd | [20:16] Rs  | [15:0] imm[15:0]
B-type: [31:26] opcode | [25:23] nzp | [22:0] PC offset
N-type: [31:26] opcode | [25:0] unused
```

### Opcode Table

| Opcode | Hex  | Instruction | Type | Description                              |
|--------|------|-------------|------|------------------------------------------|
| 000000 | 0x00 | NOP         | N    | No operation                             |
| 000001 | 0x01 | ADD         | R    | Rd = Rs1 + Rs2                           |
| 000010 | 0x02 | SUB         | R    | Rd = Rs1 − Rs2                           |
| 000011 | 0x03 | MUL         | R    | Rd = Rs1 × Rs2 (unsigned)                |
| 000100 | 0x04 | DIV         | R    | Rd = Rs1 / Rs2                           |
| 000101 | 0x05 | MOD         | R    | Rd = Rs1 % Rs2                           |
| 000110 | 0x06 | SHL         | R    | Rd = Rs1 << Rs2                          |
| 000111 | 0x07 | SHR         | R    | Rd = Rs1 >> Rs2 (logical)                |
| 001000 | 0x08 | AND         | R    | Rd = Rs1 & Rs2                           |
| 001001 | 0x09 | OR          | R    | Rd = Rs1 \| Rs2                          |
| 001010 | 0x0A | XOR         | R    | Rd = Rs1 ^ Rs2                           |
| 001011 | 0x0B | NOT         | R    | Rd = ~Rs1                                |
| 001100 | 0x0C | FMA         | R    | Rd = (Rs1 × Rs2) + Rs3                   |
| 001101 | 0x0D | CMP         | R    | Set NZP flags from Rs1 − Rs2             |
| 001110 | 0x0E | BRnzp       | B    | Branch if NZP condition met              |
| 001111 | 0x0F | LDR         | I    | Rd = Memory[Rs + imm]                    |
| 010000 | 0x10 | STR         | I    | Memory[Rs + imm] = Rd                    |
| 010001 | 0x11 | CONST       | I    | Rd = zero_extend(imm)                    |
| 010010 | 0x12 | RET         | N    | End thread block execution               |
| 010011 | 0x13 | IMUL        | R    | Rd = $signed(Rs1) × $signed(Rs2)         |
| 010100 | 0x14 | SAR         | R    | Rd = $signed(Rs1) >>> Rs2 (arithmetic)   |

IMUL and SAR were added to support Q8 fixed-point gradient computation. SHR fills with zeros, which corrupts the sign of negative gradients; SAR preserves it.

---

## Register File

32 registers, 32-bit wide each.

| Register  | Purpose    | Description                                         |
|-----------|-----------|-----------------------------------------------------|
| R0        | Hardwired  | Always reads as 0; writes ignored                  |
| R1–R28    | General    | General purpose computation registers              |
| R29       | threadIdx  | Read-only; hardware-injected thread index in block |
| R30       | blockIdx   | Read-only; hardware-injected block index in grid   |
| R31       | blockDim   | Read-only; hardware-injected block dimension       |

---

## Module Breakdown

### 1. Register File (`register_file.sv`)
![Register File Diagram](assets/Images-Components/Register-page-00001.jpg)

32×32-bit storage. Synchronous write with reset (clears R1–R28). Asynchronous triple read (supports R-type and FMA). R0 hardwired to zero; R29/R30/R31 hardware injected.

### 2. ALU (`alu.sv`)
![ALU Diagram](assets/Images-Components/ALU-page-00001.jpg)

Pure combinational logic. Supports all 21 ISA operations including FMA (3-operand multiply-accumulate), IMUL (signed multiply), and SAR (arithmetic right shift). Outputs 32-bit result and 3-bit NZP flag. NZP encoding: N=100 (negative), Z=010 (zero), P=001 (positive).

### 3. Program Counter (`pc.sv`)
![PC Diagram](assets/Images-Components/PC-page-00001.jpg)

Per-thread instruction address register. Handles branch evaluation using NZP register. NZP register updated only on CMP via `nzp_en`. Uses independent `if` blocks for `nzp_en` and `pc_en` — critical for correct CMP+BRnzp sequencing.

### 4. Decoder (`decoder.sv`)
![Decoder Diagram](assets/Images-Components/Decoder-page-00001.jpg)

Pure combinational instruction decode. Extracts all fields from the 32-bit instruction word. Generates control signals: `write_back_en`, `mem_read_en`, `mem_write_en`, `branch_en`, `nzp_en`, `ret`.

### 5. Fetcher (`fetcher.sv`)
![Fetcher Diagram](assets/Images-Components/Fetcher-page-00001.jpg)

2-state FSM (IDLE → WAITING). Valid/ready handshake with program memory. One fetcher per core, shared across all threads (SIMD fetch from thread 0's PC).

### 6. LSU — Load Store Unit (`lsu.sv`)
![LSU Diagram](assets/Images-Components/LSU-page-00001.jpg)

2-state FSM (IDLE → WAITING). Handles LDR and STR with valid/ready handshake. `read_write_switch` signals memory read vs write direction. `is_read` explicitly cleared in the write path to prevent stale state. One LSU per thread.

### 7. Memory Controller (`mem_controller.sv`)
![Memory Controller Diagram](assets/Images-Components/Memory%20Controller-page-00001.jpg)

Parameterized pass-through (NUM_CORES × THREADS_PER_CORE channels). Direct 1:1 mapping between threads and memory channels. Pure combinational. Round-robin arbitration planned.

### 8. Scheduler (`scheduler.sv`)
![Scheduler Diagram](assets/Images-Components/Scheduler-page-00001.jpg)

7-state FSM controlling the core pipeline. Broadcasts enable signals to all threads simultaneously (SIMD). Waits for all LSUs via AND-reduction of `lsu_done`. Outputs `pc_en` on the UPDATE→FETCH transition to advance the program counter.

```
IDLE    (000) — Wait for core_start
FETCH   (001) — Enable fetcher, wait for done
DECODE  (010) — Route to EXECUTE or REQUEST based on instruction type
REQUEST (011) — Enable LSUs for memory operations
WAIT    (100) — Wait until all LSUs complete
EXECUTE (101) — Enable ALUs for computation
UPDATE  (110) — Write back results, assert pc_en, check RET
```

### 9. Core (`core.sv`)
![Core Diagram](assets/Images-Components/Core-page-00001.jpg)

Instantiates 1 Scheduler, 1 Fetcher, 1 Decoder, and THREADS_PER_CORE instances each of ALU, LSU, PC, Register File. Write-back mux selects: LSU read data for LDR, zero-extended immediate for CONST, ALU result otherwise. STR address computed as `Rs + sign_extend(imm)`, and STR data reads via r_addr3 using Rd.

### 10. Dispatcher (`dispatcher.sv`)
![Dispatcher Diagram](assets/Images-Components/Dispatcher-page-00001.jpg)

Assigns thread blocks to available cores. One block assigned per core per cycle. Tracks active blocks with a signed delta accumulator using blocking assignments (required to prevent NBA race conditions in always_ff). Asserts `kernel_done` when all blocks processed. Uses packed 2D `blockIdx_out[NUM_CORES-1:0][31:0]` for Icarus compatibility.

### 11. DCR — Device Control Register (`dcr.sv`)
![DCR Diagram](assets/Images-Components/DCR-page-00001.jpg)

Host-facing configuration interface. Address 0x00: `num_blocks`. Address 0x01: `block_dim`. Address 0x10: `start` pulse (single cycle).

### 12. Top-Level GPU (`top_level_gpu.sv`)
![GPU Diagram](assets/Images-Components/GPU-page-00001.jpg)

Wires DCR → Dispatcher → Cores → Memory. Parameterized: change NUM_CORES and THREADS_PER_CORE to scale. Uses intermediate wires in generate loop for Icarus VPI unpacked array compatibility.

---

## Parameters

| Parameter         | Default | Description                         |
|------------------|---------|-------------------------------------|
| NUM_CORES         | 4       | Number of parallel cores            |
| THREADS_PER_CORE  | 4       | Threads per core (SIMD width)       |
| TOTAL_THREADS     | 16      | NUM_CORES × THREADS_PER_CORE        |

To scale to 4 cores × 16 threads each:

```systemverilog
gpu #(
    .NUM_CORES(4),
    .THREADS_PER_CORE(16)
) gpu_inst ( ... );
```

---

## AXEL Assembler

AXEL is a C library that emits `.hex` kernel files for the GPU. It provides two layers: `gpu_asm` (low-level `emit_*` functions) and `axel` (higher-level kernel API with register name aliases).

### Build

```bash
cd assembler
make phase4    # compiles and emits builds/phase4_forward.hex
make phase5    # compiles and emits builds/phase5_weight_update.hex
make           # builds all phases
```

### Register aliases

```c
R0–R28        // general purpose
THREAD_IDX    // R29 — hardware-injected thread index
BLOCK_IDX     // R30 — hardware-injected block index
BLOCK_DIM     // R31 — hardware-injected block dimension
```

### Example kernel

```c
AxelGPU gpu;
axel_init(&gpu, 1, 4);

axel_ldr(&gpu, R1, THREAD_IDX, 0);   // R1 = mem[threadIdx]
axel_add(&gpu, R2, R1, R1);           // R2 = 2 * R1
axel_str(&gpu, R2, THREAD_IDX, 4);   // mem[threadIdx + 4] = R2
axel_ret(&gpu);

axel_compile(&gpu, "output.hex");
```

---

## Neural Network — End-to-End Training and Inference

The GPU trains a 4×4 linear layer with ReLU activation in Q8 fixed-point arithmetic using gradient descent.

### Q8 Fixed-Point Encoding

All values are stored as integers where `real_value = stored_int / 256`.

| Real value | Q8 raw |
|-----------|--------|
| 1.0       | 256    |
| 2.0       | 512    |
| −0.5      | 0xFFFFFF80 |

Q8 multiply produces Q16, which is scale-downed by SAR >>8 back to Q8. The gradient step combines Q8 scale-down and learning rate into a single SAR >>12 (lr = 1/16 in Q8 space).

### Memory Layout

| Address   | Contents                        |
|-----------|---------------------------------|
| 0–15      | W[4][4] — weights (Q8), W[i][j] at addr i×4+j |
| 16–19     | x[4] — input vector (Q8)        |
| 20–23     | y[4] — forward pass output (Q8) |
| 24–27     | t[4] — target vector (Q8)       |

### Kernel Phases

| Phase | File                     | Instructions | What it does                         |
|-------|--------------------------|-------------|--------------------------------------|
| 1     | `phase1_ldr_test.c`      | 4           | LDR/STR end-to-end smoke test        |
| 2     | `phase2_matmul.c`        | 19          | 4×4 matrix-vector multiply           |
| 3     | `phase3_relu.c`          | 8           | Branchless ReLU via bit masking      |
| 4     | `phase4_forward.c`       | 26          | Linear layer + ReLU in Q8            |
| 5     | `phase5_weight_update.c` | 36          | Gradient descent weight update in Q8 |

### Training Results

```
x (real) = [1.0, 2.0, 3.0, 4.0]
t (real) = [2.0, 4.0, 6.0, 8.0]  (target: W ≈ 2×I)

Epoch  1 | y=[1.0, 1.99, 3.0, 3.99] | err=[-1.0, -2.0, -3.0, -4.0]
Epoch 10 | y=[1.76, 3.55, 5.34, 7.14] | err=[-0.24, -0.45, -0.66, -0.86]
Epoch 20 | y=[1.95, 3.94, 5.94, 7.94] | err=[-0.05, -0.06, -0.06, -0.06]

Final W diagonal ≈ [1.06, 1.14, 1.29, 1.50]
```

Residual ~0.05 error is the Q8 quantization floor (1/256 ≈ 0.004 per gradient step). The network converges and stays there.

### Inference

```bash
cd Src/Top_level_GPU
make infer
```

Output:

```
=============================================
  Input  (Q8 raw) : [256, 512, 768, 1024]
  Input  (real)   : [1.0, 2.0, 3.0, 4.0]
=============================================
  Output (Q8 raw) : [499, 1010, 1523, 2035]
  Output (real)   : [1.9492, 3.9453, 5.9492, 7.9492]
=============================================
```

Trained weights persist in `assembler/builds/weights.json` between runs. The training loop loads them automatically on next `make`.

To run inference on a different input, edit `X_INPUT` at the top of `Src/Top_level_GPU/inference.py`:

```python
X_INPUT = [128, 256, 384, 512]   # [0.5, 1.0, 1.5, 2.0] in Q8
```

---

## Project Structure

```
gpu-project/
├── README.md
├── .gitignore
├── assembler/
│   ├── Makefile
│   ├── include/
│   │   ├── axel.h          ← register aliases + all axel_ declarations
│   │   └── gpu_asm.h       ← opcode defines + emit_ declarations
│   ├── src/
│   │   ├── axel.c          ← axel_ wrappers
│   │   └── gpu_asm.c       ← encode_r/i/b/n + all emit_ implementations
│   ├── examples/
│   │   ├── phase1_ldr_test.c
│   │   ├── phase2_matmul.c
│   │   ├── phase3_relu.c
│   │   ├── phase4_forward.c      ← model architecture (Q8, SAR >>8)
│   │   └── phase5_weight_update.c ← gradient step (IMUL + SAR >>12)
│   └── builds/
│       ├── phase4_forward.hex
│       ├── phase5_weight_update.hex
│       └── weights.json          ← trained model weights (persists between runs)
└── Src/
    ├── alu/                  alu.sv, test_alu.py, Makefile
    ├── registers/            register_file.sv, test_registers.py, Makefile
    ├── pc/                   pc.sv, test_pc.py, Makefile
    ├── decoder/              decoder.sv, test_decoder.py, Makefile
    ├── fetcher/              fetcher.sv, test_fetcher.py, Makefile
    ├── lsu/                  lsu.sv, test_lsu.py, Makefile
    ├── memory_controller/    mem_controller.sv, test_mem_controller.py, Makefile
    ├── scheduler/            scheduler.sv, test_scheduler.py, Makefile
    ├── core/                 core.sv, test_core.py, Makefile
    ├── dispatcher/           dispatcher.sv, test_dispatcher.py, Makefile
    ├── device_control_register/ dcr.sv, test_dcr.py, Makefile
    └── Top_level_GPU/
        ├── top_level_gpu.sv
        ├── test_top_level_gpu.py  ← training loop (20 epochs)
        ├── inference.py           ← single forward pass with trained weights
        └── Makefile               ← includes `make infer` target
```

---

## Prerequisites

- [Icarus Verilog](https://steveicarus.github.io/iverilog/) v12.0+
- Python 3.10+
- [cocotb](https://www.cocotb.org/) v2.0+
- GCC (for assembler)
- GTKWave (optional, for waveform viewing)

### Install cocotb

```bash
python3 -m venv cocotb-env
source cocotb-env/bin/activate
pip install cocotb
```

---

## Running Tests

Each module has its own Makefile:

```bash
source ~/cocotb-env/bin/activate
cd Src/<module_name>
make
```

### Test Results

| Module              | Tests | Status  |
|---------------------|-------|---------|
| Register File       | 4     | ✅ PASS |
| ALU                 | 6     | ✅ PASS |
| Program Counter     | 5     | ✅ PASS |
| Decoder             | 4     | ✅ PASS |
| Fetcher             | 3     | ✅ PASS |
| LSU                 | 3     | ✅ PASS |
| Memory Controller   | 3     | ✅ PASS |
| Scheduler           | 3     | ✅ PASS |
| Core                | 1     | ✅ PASS |
| Dispatcher          | 3     | ✅ PASS |
| DCR                 | 3     | ✅ PASS |
| Top-Level GPU       | 1     | ✅ PASS |

### Top-Level Integration

```bash
cd Src/Top_level_GPU
make          # runs training test (20 epochs, saves weights.json)
make infer    # runs inference with saved weights
```

---

## Waveform Viewing

```bash
cd Src/Top_level_GPU
make
gtkwave gpu.vcd
```

Useful signals in GTKWave:

- `clk`, `rst`, `kernel_done`
- `gpu/core_gen[0]/core_inst/shed/state`
- `gpu/core_gen[0]/core_inst/fetch/state`
- `gpu/dispatcher_inst/next_block`
- `gpu/core_gen[0]/core_inst/thread_gen[0]/lsu_inst/mem_data_address`

---

## Design Decisions

**Why separate NZP register in the PC module?**
The NZP flag is only consumed by BRnzp for PC updates. Keeping it co-located with the PC avoids routing flag state across module boundaries. Independent `if` blocks (not `else if`) in pc.sv ensure NZP can be written and PC can advance in the same cycle.

**Why 1:1 memory controller mapping?**
Simplicity for the initial implementation. The memory controller is designed for round-robin arbitration as a future upgrade — `clk` and `rst` are already stubbed out with comments.

**Why `write_back_en_sched` vs `write_back_en_dec`?**
The decoder's `write_back_en` indicates whether the instruction type requires a writeback. The scheduler's version is the actual enable signal gated by pipeline timing, allowing the scheduler to control writeback independently of instruction type.

**Why blocking assignments for `assigned` and `delta` in the dispatcher?**
These are loop-local accumulators within a single `always_ff` evaluation. Blocking assignments ensure they take effect immediately within the loop iteration, preventing NBA race conditions when assigning multiple cores in one cycle.

**Why IMUL instead of MUL for gradient computation?**
MUL treats operands as unsigned. Gradient errors are signed Q8 values — a negative error like `−0.25` (0xFFFFFFC0 in two's complement) would be interpreted as a large positive number by MUL, giving completely wrong weight updates. IMUL uses `$signed` casting on both operands.

**Why SAR instead of SHR?**
SHR fills vacated bits with 0. On a negative product (negative gradient), SHR would produce a large positive number instead of a small negative one. SAR sign-extends, preserving the sign across the scale-down.

**Why branchless ReLU?**
The GPU is SIMD — all threads in a core execute the same instruction. If threads branch differently (some positive, some negative), only thread 0's outcome drives the PC, corrupting all other threads. The branchless bit-mask approach computes `max(0, x)` arithmetically, with no branch divergence.

---

## Known Limitations

- Icarus Verilog does not support unpacked array part-selects — intermediate wires used as workaround in the top-level generate block
- Memory controller is a pass-through with no arbitration — round-robin planned
- Fetcher is shared per core and uses thread 0's PC only (SIMD intentional; multi-PC fetch not supported)
- No hazard detection or pipeline stalling between back-to-back instructions
- Decoder generates ~32 "constant selects in always_*" warnings from Icarus (cosmetic — simulation correct; fix: move static field assignments to `assign` statements outside `always_comb`)

---

## Future Work

- Round-robin arbitration in Memory Controller
- Decoder warning fix (move static field decodes to `assign`)
- Higher Q-scale (Q10 = 1024 base) for ~0.001 precision floor vs current ~0.004
- Python AXEL runtime: write kernels in clean Python syntax, emit `.hex` directly
- Synthesis targeting Gowin FPGA
- UVM-based verification environment

---

## Author

**Austin Antony**
B.Tech Applied Electronics and Instrumentation Engineering
Rajagiri School of Engineering and Technology (2023–2027)
CTO & Co-founder, Virtusco