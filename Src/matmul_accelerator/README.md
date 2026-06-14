# Matmul Accelerator — 32-bit Tiny GPU Phase 21

## Overview

`matmul_accelerator.sv` is a memory-mapped INT8 matrix multiplication accelerator used in the 32-bit Tiny GPU project.

It computes:

```text
C = A × Bᵀ
```

where:

* `A` is stored row-major in packed INT8 words.
* `B` is stored transposed as `Bᵀ`.
* Each 32-bit memory word contains four signed INT8 values.
* Each output element is accumulated into signed INT32.
* Optional arithmetic right shift scaling is applied before storing the result.

The accelerator is controlled through MMIO-style control registers and uses a dedicated matrix data-memory port for reading `A`, reading `Bᵀ`, and writing `C`.

This module is used by Phase 21 of the Tiny GPU project.

---

## File Location

```text
Src/matmul_accelerator/
├── Makefile
├── matmul_accelerator.sv
└── tests/
    ├── common.py
    ├── test_matmul_directed.py
    ├── test_matmul_random.py
    └── test_matmul_edge.py
```

---

## Module Interface

```systemverilog
module matmul_accelerator (
    input  logic        clk,
    input  logic        rst,

    input  logic        ctrl_wr_valid,
    input  logic [3:0]  ctrl_wr_addr,
    input  logic [31:0] ctrl_wr_data,

    input  logic [3:0]  ctrl_rd_addr,
    output logic [31:0] ctrl_rd_data,

    output logic        data_req_valid,
    output logic [31:0] data_req_addr,
    output logic        data_req_rw,
    output logic [31:0] data_req_data,
    input  logic        data_resp_valid,
    input  logic [31:0] data_resp_data
);
```

---

## Ports

### Clock and Reset

| Signal | Direction | Width | Description       |
| ------ | --------: | ----: | ----------------- |
| `clk`  |     input |     1 | Main clock        |
| `rst`  |     input |     1 | Active-high reset |

---

### Control Register Write Port

| Signal          | Direction | Width | Description             |
| --------------- | --------: | ----: | ----------------------- |
| `ctrl_wr_valid` |     input |     1 | Control write enable    |
| `ctrl_wr_addr`  |     input |     4 | Control register offset |
| `ctrl_wr_data`  |     input |    32 | Control write data      |

Control registers are written by the GPU/top-level through the MMIO region starting at `0x1F0`.

---

### Control Register Read Port

| Signal         | Direction | Width | Description                  |
| -------------- | --------: | ----: | ---------------------------- |
| `ctrl_rd_addr` |     input |     4 | Control register read offset |
| `ctrl_rd_data` |    output |    32 | Control register read data   |

The main read register is `DONE`, at offset `8`.

---

### Matrix Data Memory Port

| Signal            | Direction | Width | Description                      |
| ----------------- | --------: | ----: | -------------------------------- |
| `data_req_valid`  |    output |     1 | Accelerator memory request valid |
| `data_req_addr`   |    output |    32 | Memory word address              |
| `data_req_rw`     |    output |     1 | `1 = read`, `0 = write`          |
| `data_req_data`   |    output |    32 | Write data                       |
| `data_resp_valid` |     input |     1 | Memory response valid            |
| `data_resp_data`  |     input |    32 | Read response data               |

This port is separate from the normal GPU core data-memory ports.

---

## MMIO Control Register Map

The top-level GPU decodes addresses `>= 0x1F0` and forwards them to this accelerator.

| Absolute Address | Offset | Register | Access | Description                            |
| ---------------: | -----: | -------- | ------ | -------------------------------------- |
|          `0x1F0` |    `0` | `A_BASE` | W/R    | Base address of matrix `A`             |
|          `0x1F1` |    `1` | `B_BASE` | W/R    | Base address of matrix `Bᵀ`            |
|          `0x1F2` |    `2` | `C_BASE` | W/R    | Base address of output matrix `C`      |
|          `0x1F3` |    `3` | `M`      | W/R    | Number of output rows                  |
|          `0x1F4` |    `4` | `N`      | W/R    | Number of output columns               |
|          `0x1F5` |    `5` | `K`      | W/R    | Inner dimension, must be multiple of 4 |
|          `0x1F6` |    `6` | `SCALE`  | W/R    | Arithmetic right shift amount          |
|          `0x1F7` |    `7` | `START`  | W      | Write `1` to launch accelerator        |
|          `0x1F8` |    `8` | `DONE`   | R      | Reads `1` when accelerator completes   |

---

## Matrix Layout

The accelerator expects `B` to be stored transposed as `Bᵀ`.

Each memory word stores four signed INT8 lanes:

```text
word[7:0]    = lane 0
word[15:8]   = lane 1
word[23:16]  = lane 2
word[31:24]  = lane 3
```

For `K`, the accelerator uses:

```text
num_chunks = K / 4
```

### A Layout

```text
A[i][k_chunk] = memory[A_BASE + i * (K / 4) + k_chunk]
```

### Bᵀ Layout

```text
Bᵀ[j][k_chunk] = memory[B_BASE + j * (K / 4) + k_chunk]
```

### C Layout

```text
C[i][j] = memory[C_BASE + i * N + j]
```

---

## Example Layout: 4x4 K=16

For:

```text
M = 4
N = 4
K = 16
K / 4 = 4 chunks
```

Memory layout:

```text
A_BASE = 0
B_BASE = 16
C_BASE = 32
```

```text
A rows:
mem[0..3]    = A row 0, 4 chunks
mem[4..7]    = A row 1, 4 chunks
mem[8..11]   = A row 2, 4 chunks
mem[12..15]  = A row 3, 4 chunks

Bᵀ columns:
mem[16..19]  = Bᵀ col 0, 4 chunks
mem[20..23]  = Bᵀ col 1, 4 chunks
mem[24..27]  = Bᵀ col 2, 4 chunks
mem[28..31]  = Bᵀ col 3, 4 chunks

C output:
mem[32..47]  = 16 INT32 output values
```

Expected output for the directed Phase 20/Phase 21 test:

```text
C[0] = [16, 32,  8,  8]
C[1] = [32, 64, 16, 16]
C[2] = [28, 56, 16, 12]
C[3] = [40, 80, 16, 24]
```

---

## Computation

For each output element:

```text
C[i][j] = sum over k_chunk of DOT4(A[i][k_chunk], Bᵀ[j][k_chunk])
```

Each `DOT4` performs:

```text
dot4 =
    signed(a0) * signed(b0) +
    signed(a1) * signed(b1) +
    signed(a2) * signed(b2) +
    signed(a3) * signed(b3)
```

The full accumulator is signed INT32.

Before storing:

```text
stored_value = signed(accumulator) >>> SCALE
```

This is an arithmetic right shift, so negative values remain signed correctly.

---

## FSM

The accelerator uses a sequential FSM:

```text
IDLE
  ↓
LOAD_A
  ↓
WAIT_A
  ↓
LOAD_B
  ↓
WAIT_B
  ↓
MAC_STATE
  ↓
STORE
  ↓
WAIT_STORE
  ↓
NEXT_IJ
  ↓
DONE_SET
  ↓
IDLE
```

### State Description

| State        | Description                            |
| ------------ | -------------------------------------- |
| `IDLE`       | Wait for `START=1`                     |
| `LOAD_A`     | Issue memory read for `A[i][k_chunk]`  |
| `WAIT_A`     | Wait for A read response               |
| `LOAD_B`     | Issue memory read for `Bᵀ[j][k_chunk]` |
| `WAIT_B`     | Wait for B read response               |
| `MAC_STATE`  | Accumulate one DOT4 result             |
| `STORE`      | Issue memory write for `C[i][j]`       |
| `WAIT_STORE` | Wait for write response                |
| `NEXT_IJ`    | Advance column, then row               |
| `DONE_SET`   | Set `DONE=1` and return to `IDLE`      |

---

## Runtime Config Latching

The accelerator latches all runtime configuration when `START` is written.

Runtime-latched registers:

```systemverilog
run_a_base
run_b_base
run_c_base
run_m
run_n
run_k
run_scale
run_k_chunks
```

This prevents active computation from being corrupted by later MMIO writes.

The host-visible config registers are:

```systemverilog
reg_a_base
reg_b_base
reg_c_base
reg_m
reg_n
reg_k
reg_scale
reg_done
```

Config writes are accepted only while the FSM is in `IDLE`.

This behavior is important because, in the full GPU top-level, multiple cores/threads may access the same global accelerator MMIO region.

---

## DONE Behavior

`DONE` is stored in `reg_done`.

Behavior:

```text
Reset:
    DONE = 0

START:
    DONE = 0

Computation running:
    DONE = 0

All C outputs written:
    DONE = 1
```

A new `START` clears the previous `DONE`.

If memory does not respond, the accelerator must not falsely assert `DONE`.

---

## Top-Level GPU Integration Note

In the full GPU top-level, the dispatcher can finish the GPU core program before the accelerator completes all matrix writes.

Because of this, `top_level_gpu.sv` gates final `kernel_done` using an accelerator inflight tracker.

Conceptually:

```systemverilog
kernel_done = dispatcher_kernel_done && !accel_inflight;
```

This prevents the testbench or host from observing kernel completion before the accelerator has fully written the output matrix.

---

## Makefile

```makefile
TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(shell pwd)/matmul_accelerator.sv
TOPLEVEL = matmul_accelerator
COCOTB_TEST_MODULES ?= tests.test_matmul_directed,tests.test_matmul_random,tests.test_matmul_edge
SIM = icarus
export PYTHONPATH := $(shell pwd):$(PYTHONPATH)
include $(shell cocotb-config --makefiles)/Makefile.sim
```

---

## Running Tests

From the accelerator directory:

```bash
cd ~/gpu-project/Src/matmul_accelerator
make
```

Run only directed tests:

```bash
make COCOTB_TEST_MODULES=tests.test_matmul_directed
```

Run only random tests:

```bash
make COCOTB_TEST_MODULES=tests.test_matmul_random
```

Run only edge/protocol tests:

```bash
make COCOTB_TEST_MODULES=tests.test_matmul_edge
```

Clean generated files:

```bash
rm -rf sim_build results.xml __pycache__ tests/__pycache__
```

---

## Test Files

### `tests/common.py`

Shared cocotb helpers:

| Helper              | Purpose                                                |
| ------------------- | ------------------------------------------------------ |
| `safe_int()`        | Safely convert cocotb signal values to Python integers |
| `u32()`             | Clamp value to unsigned 32-bit                         |
| `u32_to_signed()`   | Convert unsigned 32-bit value to signed INT32          |
| `reset_dut()`       | Reset accelerator and initialize ports                 |
| `write_ctrl()`      | Write MMIO control register                            |
| `poll_done()`       | Poll DONE register until completion                    |
| `accel_mem_model()` | Standalone memory model for accelerator tests          |

---

### `tests/test_matmul_directed.py`

Directed sanity tests.

| Test                  | Purpose                                      |
| --------------------- | -------------------------------------------- |
| `test_matmul_2x2_k4`  | Small 2x2 INT8 matmul smoke test             |
| `test_matmul_4x4_k16` | Full 4x4 K=16 test matching Phase 20/21 data |
| `test_matmul_scale`   | Verifies arithmetic scaling with `SCALE=2`   |

---

### `tests/test_matmul_random.py`

Random correctness tests.

| Test                        | Purpose                                           |
| --------------------------- | ------------------------------------------------- |
| `test_random_correctness`   | Random M/N/K with positive INT8 data              |
| `test_random_scale`         | Random scale values                               |
| `test_random_sequential`    | Multiple sequential accelerator launches          |
| `test_random_negative_data` | Full signed INT8 range, including negative values |

---

### `tests/test_matmul_edge.py`

Edge and protocol coverage.

| Test                                                     | Purpose                                                  |
| -------------------------------------------------------- | -------------------------------------------------------- |
| `test_reset_defaults_and_idle_outputs`                   | Reset clears config, DONE, outputs, and FSM state        |
| `test_ctrl_register_write_readback_and_invalid_access`   | MMIO write/read behavior and invalid reads               |
| `test_done_clears_on_new_start`                          | DONE clears when a new START is issued                   |
| `test_config_writes_ignored_while_running_runtime_latch` | Runtime config latching and ignored writes while running |
| `test_nonzero_bases_and_gap_memory_layout`               | Non-zero base addresses and memory gaps                  |
| `test_exact_read_and_write_address_order_row_major`      | Exact A/B read and C write ordering                      |
| `test_memory_response_stalls_are_handled`                | Wait-state handling for delayed memory responses         |
| `test_signed_extreme_int8_values`                        | Signed INT8 edge values such as -128 and 127             |
| `test_negative_accumulator_arithmetic_scale`             | Arithmetic right shift on negative accumulators          |
| `test_minimal_1x1_k4_shape`                              | Smallest valid matrix shape                              |
| `test_large_supported_4x4_k16_all_negative`              | Large signed stress case                                 |
| `test_no_memory_response_does_not_false_done`            | DONE must not assert without memory responses            |

---

## Latest Verification Result

The current accelerator regression passes:

```text
TESTS=19 PASS=19 FAIL=0 SKIP=0
```

Covered categories:

```text
Directed tests       : 3
Random tests         : 4
Edge/protocol tests  : 12
Total                : 19
```

Important passing checks:

```text
4x4 K=16 directed matmul passed
Random positive INT8 tests passed
Random signed INT8 tests passed
Sequential launch tests passed
Runtime config latch test passed
Memory response stall test passed
No false DONE without memory response passed
```

---

## Known Constraints

Current tested/expected constraints:

```text
K must be a multiple of 4.
A and Bᵀ are stored as packed signed INT8 words.
B must be pre-transposed before accelerator execution.
Output C is stored as signed INT32 words.
```

Current test coverage focuses mainly on:

```text
M = 1..4
N = 1..4
K = 4, 8, 12, 16
SCALE = 0..7
```

Larger shapes may work architecturally, but should be tested separately if used.

---

## Important Design Notes

### 1. B is stored transposed

The accelerator expects `Bᵀ`, not normal row-major `B`.

This simplifies address generation:

```text
Bᵀ[j][k_chunk] = B_BASE + j * (K / 4) + k_chunk
```

---

### 2. Config is latched on START

Do not use live config registers during execution.

Correct behavior:

```text
START written
→ copy reg_* into run_*
→ use run_* for the entire operation
```

This prevents races from later MMIO writes.

---

### 3. Memory responses are required

The accelerator waits for:

```text
data_resp_valid = 1
```

in:

```text
WAIT_A
WAIT_B
WAIT_STORE
```

Without memory responses, it must stay running and must not assert `DONE`.

---

### 4. DONE means all outputs are written

`DONE=1` only after the final C output write has been acknowledged.

It should not indicate only that the final multiply completed.

---

## Debugging Tips

### If DONE never asserts

Check:

```text
data_resp_valid
data_req_valid
data_req_rw
data_req_addr
state
i
j
k_chunk
```

Likely causes:

```text
Memory model not responding
Wrong memory handshake
K = 0
K not multiple of 4
FSM stuck in WAIT_A / WAIT_B / WAIT_STORE
```

---

### If outputs are None/missing

Likely causes:

```text
C write did not happen
Memory model did not record writes
DONE asserted too early
Top-level kernel_done not gated
Wrong C_BASE
Wrong M/N loop bounds
```

---

### If outputs are wrong numbers

Likely causes:

```text
B not stored transposed
Wrong packed INT8 lane order
Signed extension bug
Wrong K value
Wrong SCALE value
Wrong A_BASE or B_BASE
```

---

### If only first few outputs are written

Likely causes:

```text
FSM exits early
DONE asserted too early
M/N corrupted during runtime
Config not latched on START
Top-level test stops before accelerator completion
```

---

## Suggested Commit Message

```text
Add matmul accelerator edge coverage and README
```

Suggested commit body:

```text
- Documented Phase 21 MMIO matmul accelerator interface and behavior
- Added README covering register map, memory layout, FSM, tests, and debug flow
- Added edge/protocol cocotb tests for runtime config latching, DONE behavior, stalls, and address order
- Verified accelerator regression with 19 passing tests
```

---

## Status

Current status:

```text
matmul_accelerator.sv: PASS
Directed tests       : PASS
Random tests         : PASS
Edge tests           : PASS
Total                : 19/19 PASS
```

The accelerator is now ready for continued top-level GPU integration and Phase 21 documentation.
