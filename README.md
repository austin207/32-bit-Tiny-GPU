# 32-Bit Tiny GPU

A custom 32-bit SIMT-style GPU built from scratch in SystemVerilog.

This project includes a custom ISA, AXEL C assembler, cocotb verification, SIMT branch divergence with warp-stack reconvergence, Q8 fixed-point neural-network workloads, FPGA targeting for the Sipeed Tang Nano 20K, and a Sky130A OpenLane GDS run.

---

## Status

```text
RTL simulation:      PASSING
Top-level GPU test:  PASSING
SIMT ReLU test:      PASSING
FPGA target:         Tang Nano 20K
ASIC flow:           Sky130A GDS generated
````

Key verified regression:

```text
Phase 6 SIMT ReLU

Input:
  mem[0] =  5
  mem[1] = -3
  mem[2] =  8
  mem[3] = -1

Expected output:
  mem[4] = 5
  mem[5] = 0
  mem[6] = 8
  mem[7] = 0
```

This verifies load, register writeback, CMP, BRnzp, stored NZP flags, active-mask gating, warp-stack reconvergence, store, and kernel completion.

---

## Architecture

![GPU Architecture](assets/Architecture-images/gpu_architecture.png)

Default simulation configuration:

```text
NUM_CORES        = 4
THREADS_PER_CORE = 4
TOTAL_THREADS    = 16
```

Top-level hierarchy:

```text
gpu
├── dcr
├── dispatcher
└── core_gen[i]
    └── core
        ├── fetcher
        ├── decoder
        ├── scheduler
        ├── warp_stack
        ├── mem_controller
        └── thread_gen[j]
            ├── registers
            ├── alu
            ├── lsu
            └── pc
```

Full architecture details are in [`docs/architecture.md`](docs/architecture.md).

---

## Documentation

| Document       | Path                                           |
| -------------- | ---------------------------------------------- |
| Architecture   | [`docs/architecture.md`](docs/architecture.md) |
| ISA            | [`docs/isa.md`](docs/isa.md)                   |
| Memory map     | [`docs/memory_map.md`](docs/memory_map.md)     |
| Debug log      | [`docs/debug_log.md`](docs/debug_log.md)       |
| AXEL assembler | [`assembler/README.md`](assembler/README.md)   |
| FPGA build     | [`fpga/README.md`](fpga/README.md)             |
| OpenLane / GDS | [`gds/README.md`](gds/README.md)               |

---

## Module Documentation

| Module            | README                                                                           | RTL                                                                                  | Testbench                                                                                      |
| ----------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| ALU               | [`Src/alu/README.md`](Src/alu/README.md)                                         | [`Src/alu/alu.sv`](Src/alu/alu.sv)                                                   | [`Src/alu/test_alu.py`](Src/alu/test_alu.py)                                                   |
| Core              | [`Src/core/README.md`](Src/core/README.md)                                       | [`Src/core/core.sv`](Src/core/core.sv)                                               | [`Src/core/test_core.py`](Src/core/test_core.py)                                               |
| Decoder           | [`Src/decoder/README.md`](Src/decoder/README.md)                                 | [`Src/decoder/decoder.sv`](Src/decoder/decoder.sv)                                   | [`Src/decoder/test_decoder.py`](Src/decoder/test_decoder.py)                                   |
| DCR               | [`Src/device_control_register/README.md`](Src/device_control_register/README.md) | [`Src/device_control_register/dcr.sv`](Src/device_control_register/dcr.sv)           | [`Src/device_control_register/test_dcr.py`](Src/device_control_register/test_dcr.py)           |
| Dispatcher        | [`Src/dispatcher/README.md`](Src/dispatcher/README.md)                           | [`Src/dispatcher/dispatcher.sv`](Src/dispatcher/dispatcher.sv)                       | [`Src/dispatcher/test_dispatcher.py`](Src/dispatcher/test_dispatcher.py)                       |
| Fetcher           | [`Src/fetcher/README.md`](Src/fetcher/README.md)                                 | [`Src/fetcher/fetcher.sv`](Src/fetcher/fetcher.sv)                                   | [`Src/fetcher/test_fetcher.py`](Src/fetcher/test_fetcher.py)                                   |
| LSU               | [`Src/lsu/README.md`](Src/lsu/README.md)                                         | [`Src/lsu/lsu.sv`](Src/lsu/lsu.sv)                                                   | [`Src/lsu/test_lsu.py`](Src/lsu/test_lsu.py)                                                   |
| Memory Controller | [`Src/memory_controller/README.md`](Src/memory_controller/README.md)             | [`Src/memory_controller/mem_controller.sv`](Src/memory_controller/mem_controller.sv) | [`Src/memory_controller/test_mem_controller.py`](Src/memory_controller/test_mem_controller.py) |
| PC                | [`Src/pc/README.md`](Src/pc/README.md)                                           | [`Src/pc/pc.sv`](Src/pc/pc.sv)                                                       | [`Src/pc/test_pc.py`](Src/pc/test_pc.py)                                                       |
| Registers         | [`Src/registers/README.md`](Src/registers/README.md)                             | [`Src/registers/register_file.sv`](Src/registers/register_file.sv)                   | [`Src/registers/test_registers.py`](Src/registers/test_registers.py)                           |
| Scheduler         | [`Src/scheduler/README.md`](Src/scheduler/README.md)                             | [`Src/scheduler/scheduler.sv`](Src/scheduler/scheduler.sv)                           | [`Src/scheduler/test_scheduler.py`](Src/scheduler/test_scheduler.py)                           |
| Top-Level GPU     | [`Src/Top_level_GPU/README.md`](Src/Top_level_GPU/README.md)                     | [`Src/Top_level_GPU/top_level_gpu.sv`](Src/Top_level_GPU/top_level_gpu.sv)           | [`Src/Top_level_GPU/test_top_level_gpu.py`](Src/Top_level_GPU/test_top_level_gpu.py)           |
| Warp Stack        | [`Src/warp_stack/README.md`](Src/warp_stack/README.md)                           | [`Src/warp_stack/warp_stack.sv`](Src/warp_stack/warp_stack.sv)                       | [`Src/warp_stack/test_warp_stack.py`](Src/warp_stack/test_warp_stack.py)                       |

---

## ISA Summary

The GPU uses 32-bit fixed-width instructions with a 6-bit opcode field.

![Instruction Encoding](assets/Architecture-images/instruction_encoding.png)

Instruction formats:

```text
R-type  -> register/register ALU operations
I-type  -> load/store/constant immediate
B-type  -> BRnzp SIMT branch
N-type  -> NOP, RET, SYNC
```

Supported instructions:

```text
NOP, ADD, SUB, MUL, DIV, MOD, SHL, SHR,
AND, OR, XOR, NOT, FMA, CMP, BRnzp,
LDR, STR, CONST, RET, IMUL, SAR, SYNC
```

Full ISA documentation: [`docs/isa.md`](docs/isa.md)

---

## SIMT Execution

Each thread lane has its own:

```text
register file
ALU
LSU
PC
NZP flag
```

Each core has shared:

```text
fetcher
decoder
scheduler
memory controller
warp stack
```

The scheduler controls `active_mask`. Inactive lanes cannot issue memory requests, write registers, or advance PC.

Divergence flow:

```text
CMP sets per-thread NZP
BRnzp computes taken_mask
taken group runs first
not-taken mask is saved in warp_stack
SYNC restores saved mask
threads reconverge
```

More detail: [`docs/architecture.md`](docs/architecture.md), [`Src/warp_stack/README.md`](Src/warp_stack/README.md), [`Src/scheduler/README.md`](Src/scheduler/README.md)

---

## AXEL Assembler

AXEL is a C-based assembler layer that emits `.hex` programs for the GPU.

![Software Layer Architecture](assets/Architecture-images/software_layer_architecture.png)

Main files:

```text
assembler/include/axel.h
assembler/include/gpu_asm.h
assembler/src/axel.c
assembler/src/gpu_asm.c
assembler/examples/
assembler/builds/
```

Build assembler programs:

```bash
cd assembler
make
```

Example kernel:

```c
AxelGPU gpu;
axel_init(&gpu, 1, 4);

axel_ldr(&gpu, R1, THREAD_IDX, 0);
axel_add(&gpu, R2, R1, R1);
axel_str(&gpu, R2, THREAD_IDX, 4);
axel_ret(&gpu);

axel_compile(&gpu, "output.hex");
```

Full assembler documentation: [`assembler/README.md`](assembler/README.md)

---

## Memory Map

The neural-network examples use Q8 fixed-point values.

```text
real_value = q8_value / 256
q8_value   = round(real_value * 256)
```

Main data memory layout:

| Address range | Contents                |
| ------------: | ----------------------- |
|        `0-15` | `W[4][4]` Q8 weights    |
|       `16-19` | `x[4]` Q8 input vector  |
|       `20-23` | `y[4]` Q8 output vector |
|       `24-27` | `t[4]` Q8 target vector |

Full memory documentation: [`docs/memory_map.md`](docs/memory_map.md)

---

## Running Tests

Activate the cocotb environment:

```bash
source ~/cocotb-env/bin/activate
```

Run all tests from the repository root:

```bash
make test
```

Run one module test:

```bash
cd Src/<module_name>
make
```

Run top-level GPU tests:

```bash
cd Src/Top_level_GPU
make
```

Run only SIMT ReLU:

```bash
cd Src/Top_level_GPU
make COCOTB_TEST_FILTER='test_simt_relu$'
```

Run inference:

```bash
cd Src/Top_level_GPU
make infer
```

---

## Test Coverage

| Module            | Tests | Status |
| ----------------- | ----: | ------ |
| ALU               |     6 | PASS   |
| Registers         |     4 | PASS   |
| PC                |     5 | PASS   |
| Decoder           |     5 | PASS   |
| Fetcher           |     3 | PASS   |
| LSU               |     3 | PASS   |
| Memory Controller |     3 | PASS   |
| Scheduler         |     4 | PASS   |
| Warp Stack        |     3 | PASS   |
| Core              |     1 | PASS   |
| Dispatcher        |     3 | PASS   |
| DCR               |     3 | PASS   |
| Top-Level GPU     |     2 | PASS   |

---

## FPGA Target

Target board:

```text
Sipeed Tang Nano 20K
GW2AR-18C QN88
```

The FPGA build uses a reduced configuration:

| Parameter          | Simulation |       FPGA |
| ------------------ | ---------: | ---------: |
| `NUM_CORES`        |          4 |          1 |
| `THREADS_PER_CORE` |          4 |          1 |
| `num_blocks`       |          1 |          4 |
| Execution          |   Parallel | Sequential |

Full FPGA documentation: [`fpga/README.md`](fpga/README.md)

---

## OpenLane / Sky130A GDS

The GPU has been taken through an OpenLane 2.3.10 Sky130A RTL-to-GDSII flow.

![GPU Layout](assets/gds/gpu_layout.png)

Summary:

| Metric            |     Value |
| ----------------- | --------: |
| Standard cells    |   204,938 |
| Chip area         | 1.977 mm² |
| Flip-flops        |    16,138 |
| Clock target      |    40 MHz |
| Worst setup slack |  +8.01 ns |
| LVS               |    Passed |
| GDS               | Generated |

Full GDS documentation: [`gds/README.md`](gds/README.md)

---

## Important Design Rules

1. Keep packed memory response buses aligned across RTL and cocotb.
2. Register writeback must be gated by scheduler writeback, decoder writeback, and active mask.
3. Inactive SIMT lanes must not issue LSU requests, write registers, or advance PC.
4. `BRnzp` uses stored NZP from the PC module, not raw ALU output.
5. Keep the instruction latch in `core.sv` for stable multicycle execution.
6. LSU request pulses must be buffered by the memory controller.

Detailed debug history: [`docs/debug_log.md`](docs/debug_log.md)

---

## Project Structure

```text
gpu-project/
├── README.md
├── Makefile
├── assembler/
├── assets/
│   ├── Architecture-images/
│   ├── Images-Components/
│   ├── gds/
│   └── PDFs/
├── docs/
│   ├── architecture.md
│   ├── isa.md
│   ├── memory_map.md
│   └── debug_log.md
├── fpga/
├── gds/
├── reports/
├── schematics/
└── Src/
    ├── alu/
    ├── core/
    ├── decoder/
    ├── device_control_register/
    ├── dispatcher/
    ├── fetcher/
    ├── lsu/
    ├── memory_controller/
    ├── pc/
    ├── registers/
    ├── scheduler/
    ├── Top_level_GPU/
    └── warp_stack/
```

---

## Known Limitations

* Program and data memories are currently modeled in cocotb for simulation.
* No final top-level SRAM/BRAM subsystem is integrated yet.
* Memory is word-addressed only.
* Branch offsets are currently unsigned forward offsets.
* `CONST` only loads a 16-bit zero-extended immediate.
* `DIV` and `MOD` are expensive for synthesis and are disabled/replaced in some synthesis targets.
* `kernel_done` is sticky until reset.
* Architecture image still needs an update to show `warp_stack` inside each core.

---

## Future Work

* Update architecture diagram to include `warp_stack`
* Add top-level RTL memory/BRAM integration
* Add repeated-kernel launch support without full reset
* Add more branch/SYNC trace tests
* Add Python AXEL runtime
* Expand FPGA build toward full 4-core, 4-thread configuration
* Re-run OpenLane on latest SIMT RTL
* Fix remaining ASIC DRC/signoff items

---

## Author

**Austin Antony**
B.Tech Applied Electronics and Instrumentation Engineering
Rajagiri School of Engineering and Technology
CTO & Co-founder, Virtusco
