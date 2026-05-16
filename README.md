# 32-Bit Tiny GPU

A fully parameterized 32-bit GPU architecture implemented in SystemVerilog, built from scratch with cocotb-based verification. Designed as a learning project targeting VLSI/RTL engineering roles.

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

| Opcode (bin) | Hex  | Instruction | Type | Description                        |
|--------------|------|-------------|------|------------------------------------|
| 000000       | 0x00 | NOP         | N    | No operation                       |
| 000001       | 0x01 | ADD         | R    | Rd = Rs1 + Rs2                     |
| 000010       | 0x02 | SUB         | R    | Rd = Rs1 - Rs2                     |
| 000011       | 0x03 | MUL         | R    | Rd = Rs1 × Rs2                     |
| 000100       | 0x04 | DIV         | R    | Rd = Rs1 / Rs2                     |
| 000101       | 0x05 | MOD         | R    | Rd = Rs1 % Rs2                     |
| 000110       | 0x06 | SHL         | R    | Rd = Rs1 << Rs2                    |
| 000111       | 0x07 | SHR         | R    | Rd = Rs1 >> Rs2                    |
| 001000       | 0x08 | AND         | R    | Rd = Rs1 & Rs2                     |
| 001001       | 0x09 | OR          | R    | Rd = Rs1 \| Rs2                    |
| 001010       | 0x0A | XOR         | R    | Rd = Rs1 ^ Rs2                     |
| 001011       | 0x0B | NOT         | R    | Rd = ~Rs1                          |
| 001100       | 0x0C | FMA         | F    | Rd = (Rs1 × Rs2) + Rs3             |
| 001101       | 0x0D | CMP         | R    | Set NZP flags from Rs1 - Rs2       |
| 001110       | 0x0E | BRnzp       | B    | Branch if NZP condition met        |
| 001111       | 0x0F | LDR         | I    | Rd = Memory[Rs + imm]              |
| 010000       | 0x10 | STR         | I    | Memory[Rs + imm] = Rd              |
| 010001       | 0x11 | CONST       | I    | Rd = imm                           |
| 010010       | 0x12 | RET         | N    | End thread block execution         |
| 010011–111111| 0x13–0x3F | reserved | — | —                             |

---

## Register File

32 registers, 32-bit wide each.

| Register | Purpose     | Description                                          |
|----------|-------------|------------------------------------------------------|
| R0       | Hardwired   | Always reads as 0, writes ignored                   |
| R1–R28   | General     | General purpose computation registers               |
| R29      | threadIdx   | Read-only, hardware-injected thread index in block  |
| R30      | blockIdx    | Read-only, hardware-injected block index in grid    |
| R31      | blockDim    | Read-only, hardware-injected block dimension        |

---

## Module Breakdown

### 1. Register File (`registers.sv`)
- 32×32-bit storage array
- Synchronous write with reset (clears R1–R28)
- Asynchronous triple read (R-type and FMA support)
- R0 hardwired to zero, R29/R30/R31 hardware injected

### 2. ALU (`alu.sv`)
- Pure combinational logic
- Supports all 12 arithmetic/logic operations including FMA (3-operand)
- Outputs 32-bit result and 3-bit NZP flag for CMP
- NZP encoding: N=100 (negative), Z=010 (zero), P=001 (positive)

### 3. Program Counter (`pc.sv`)
- Stores per-thread instruction address
- Handles branch evaluation using NZP register
- NZP register updated only on CMP instructions via `nzp_en`
- Default behavior: increment by 1 each cycle

### 4. Decoder (`decoder.sv`)
- Pure combinational instruction decode
- Extracts all fields from 32-bit instruction word
- Generates control signals: `write_back_en`, `mem_read_en`, `mem_write_en`, `branch_en`, `nzp_en`, `ret`

### 5. Fetcher (`fetcher.sv`)
- 2-state FSM (IDLE → WAITING)
- Valid/ready handshake with program memory
- One fetcher per core, shared across all threads in the core

### 6. LSU — Load Store Unit (`lsu.sv`)
- 2-state FSM (IDLE → WAITING)
- Handles both LDR (read) and STR (write) with valid/ready handshake
- `read_write_switch` output signals memory read vs write direction
- One LSU per thread

### 7. Memory Controller (`mem_controller.sv`)
- Parameterized pass-through (`NUM_CORES × THREADS_PER_CORE` channels)
- Direct 1:1 mapping between threads and memory channels
- Pure combinational — no clock required
- Round-robin arbitration planned for future upgrade

### 8. Scheduler (`scheduler.sv`)
- 7-state FSM controlling the core pipeline
- States: `IDLE → FETCH → DECODE → REQUEST → WAIT → EXECUTE → UPDATE`
- Broadcasts enable signals to all threads simultaneously (SIMD)
- Waits for all LSUs via AND-reduction of `lsu_done` signals

```
IDLE    (000) — Wait for core_start
FETCH   (001) — Enable fetcher, wait for done
DECODE  (010) — Latch decoded signals, route to EXECUTE or REQUEST
REQUEST (011) — Enable LSUs for memory operations
WAIT    (100) — Wait until all LSUs complete
EXECUTE (101) — Enable ALUs for computation
UPDATE  (110) — Write back results, check RET
```

### 9. Core (`core.sv`)
- Instantiates 1 Scheduler, 1 Fetcher, 1 Decoder
- Instantiates `THREADS_PER_CORE` each of: ALU, LSU, PC, Register File
- Uses `generate` loop for per-thread instantiation
- Write-back mux selects between ALU result and LSU read data

### 10. Dispatcher (`dispatcher.sv`)
- Assigns thread blocks to available cores
- One block assigned per core per cycle (prevents NBA race conditions)
- Tracks active blocks with signed delta counter
- Asserts `kernel_done` when all blocks processed

### 11. DCR — Device Control Register (`dcr.sv`)
- Host-facing configuration interface
- Address 0x00: `num_blocks`
- Address 0x01: `block_dim`
- Address 0x02: `start` pulse (single cycle)

### 12. Top-Level GPU (`top_level_gpu.sv`)
- Wires DCR → Dispatcher → Cores → Memory
- Parameterized: change `NUM_CORES` and `THREADS_PER_CORE` to scale
- Uses intermediate wires in generate loop for iverilog array compatibility

---

## Parameters

| Parameter        | Default | Description                          |
|-----------------|---------|--------------------------------------|
| NUM_CORES        | 4       | Number of parallel cores             |
| THREADS_PER_CORE | 4       | Threads per core (SIMD width)        |
| TOTAL_THREADS    | 16      | NUM_CORES × THREADS_PER_CORE         |

To scale to 4 cores with 16 threads each, instantiate top level with:
```systemverilog
gpu #(
    .NUM_CORES(4),
    .THREADS_PER_CORE(16)
) gpu_inst ( ... );
```

---

## Project Structure

```
gpu-project/
└── Src/
    ├── alu/
    │   ├── alu.sv
    │   ├── test_alu.py
    │   └── Makefile
    ├── registers/
    │   ├── register_file.sv
    │   ├── test_registers.py
    │   └── Makefile
    ├── pc/
    │   ├── pc.sv
    │   ├── test_pc.py
    │   └── Makefile
    ├── decoder/
    │   ├── decoder.sv
    │   ├── test_decoder.py
    │   └── Makefile
    ├── fetcher/
    │   ├── fetcher.sv
    │   ├── test_fetcher.py
    │   └── Makefile
    ├── lsu/
    │   ├── lsu.sv
    │   ├── test_lsu.py
    │   └── Makefile
    ├── memory_controller/
    │   ├── mem_controller.sv
    │   ├── test_mem_controller.py
    │   └── Makefile
    ├── scheduler/
    │   ├── scheduler.sv
    │   ├── test_scheduler.py
    │   └── Makefile
    ├── core/
    │   ├── core.sv
    │   ├── test_core.py
    │   └── Makefile
    ├── dispatcher/
    │   ├── dispatcher.sv
    │   ├── test_dispatcher.py
    │   └── Makefile
    ├── device_control_register/
    │   ├── dcr.sv
    │   ├── test_dcr.py
    │   └── Makefile
    └── Top_level_GPU/
        ├── top_level_gpu.sv
        ├── test_top_level_gpu.py
        └── Makefile
```

---

## Prerequisites

- [Icarus Verilog](https://steveicarus.github.io/iverilog/) (tested on v12.0)
- Python 3.10+
- [cocotb](https://www.cocotb.org/) v2.0+
- GTKWave (optional, for waveform viewing)

### Install cocotb

```bash
python3 -m venv cocotb-env
source cocotb-env/bin/activate
pip install cocotb
```

---

## Running Tests

Each module has its own Makefile. To test a specific module:

```bash
source ~/cocotb-env/bin/activate
cd Src/<module_name>
make
```

### Test Results Summary

| Module             | Tests | Status |
|--------------------|-------|--------|
| Register File      | 4     | ✅ PASS |
| ALU                | 6     | ✅ PASS |
| Program Counter    | 5     | ✅ PASS |
| Decoder            | 4     | ✅ PASS |
| Fetcher            | 3     | ✅ PASS |
| LSU                | 3     | ✅ PASS |
| Memory Controller  | 3     | ✅ PASS |
| Scheduler          | 3     | ✅ PASS |
| Core               | 1     | ✅ PASS |
| Dispatcher         | 3     | ✅ PASS |
| DCR                | 3     | ✅ PASS |
| Top-Level GPU      | 1     | ✅ PASS |

### Run Top-Level Integration Test

```bash
cd Src/Top_level_GPU
make
```

---

## Waveform Viewing

The top-level module generates a VCD file on simulation:

```bash
cd Src/Top_level_GPU
make
gtkwave gpu.vcd
```

Useful signals to add in GTKWave:
- `clk`, `rst`, `kernel_done`
- `gpu/core_gen[0]/core_inst/shed/state`
- `gpu/core_gen[0]/core_inst/fetch/state`
- `gpu/dispatcher_inst/next_block`

---

## Design Decisions

**Why separate NZP register in the PC module?**  
The NZP flag is only consumed by BRnzp for PC updates. Keeping it co-located with the PC avoids routing flag state across module boundaries.

**Why 1:1 memory controller mapping?**  
Simplicity for initial implementation. The memory controller is designed for round-robin arbitration as a future upgrade — `clk` and `rst` are already stubbed out with comments.

**Why `always_comb` for the decoder?**  
The decoder is purely combinational — no state to store. This avoids unnecessary clock dependencies and reduces simulation complexity.

**Why `write_back_en_sched` vs `write_back_en_dec`?**  
The decoder's `write_back_en` indicates whether the instruction type requires a writeback. The scheduler's `write_back_en` is the actual enable signal gated by pipeline timing. Keeping them separate allows the scheduler to control writeback timing independently of instruction type.

**Why blocking assignments for `assigned` and `delta` in the dispatcher?**  
These variables are used as loop-local accumulators within a single `always_ff` evaluation. Using blocking assignments (`=`) ensures they take effect immediately within the loop iteration, preventing NBA race conditions.

---

## Known Limitations

- Icarus Verilog does not support unpacked array part-selects — intermediate wires used as workaround in top-level generate block
- Memory controller is a pass-through (no arbitration) — round-robin planned
- Program counter is per-thread but fetcher is shared — currently uses `pc_out[0]` for fetch address (single-thread fetch)
- No hazard detection or pipeline stalling between back-to-back instructions

---

## Future Work

- Round-robin arbitration in Memory Controller
- Proper multi-thread PC muxing for fetch
- Assembler for the custom ISA
- Synthesis targeting Gowin FPGA
- UVM-based verification environment
- Hazard detection and pipeline stalling

---

## Author

**Austin Antony**  
B.Tech Applied Electronics and Instrumentation Engineering  
Rajagiri School of Engineering and Technology (2023–2027)  
CTO & Co-founder, Virtusco