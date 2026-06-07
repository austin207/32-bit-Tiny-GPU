# 32-Bit Tiny GPU

A custom 32-bit SIMT GPU built from scratch in SystemVerilog.

This project includes a custom ISA, AXEL C assembler, cocotb verification suite,
SIMT branch divergence with warp-stack reconvergence, a round-robin memory arbiter,
Q8 fixed-point neural-network workloads, FPGA targeting for the Sipeed Tang Nano 20K,
and a full RTL-to-GDSII run on SkyWater Sky130A via OpenLane 2.

---

## Status

```text
RTL simulation:      47/47 tests passing
Top-level GPU test:  PASSING
SIMT ReLU test:      PASSING
Execution trace:     cycle-accurate CSV logger integrated
Kernel cycle counter: hardware 32-bit counter on kernel_cycles port
PyAXEL runtime:      cocotb subprocess backend, smoke test passing
FPGA target:         Tang Nano 20K (wrapper updated, flash pending)
ASIC flow:           Sky130A GDS, 0 DRC violations, LVS passed
Post-route STA:      32.9 MHz (TT), 18.6 MHz (SS)
```

Key verified regression: Phase 6 SIMT ReLU:

```text
Input:
  mem[0] =  5   mem[1] = -3   mem[2] =  8   mem[3] = -1

Output:
  mem[4] =  5   mem[5] =  0   mem[6] =  8   mem[7] =  0
```

This single test exercises: LDR writeback, CMP, BRnzp, stored NZP flags,
active-mask gating, warp-stack push/pop, SYNC reconvergence, STR, and kernel completion.

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
└── core_gen[i]  (i = 0..3)
    └── core
        ├── fetcher
        ├── decoder
        ├── scheduler
        ├── warp_stack
        ├── mem_controller   (round-robin, 2-state FSM)
        └── thread_gen[j]    (j = 0..3)
            ├── registers
            ├── alu
            ├── lsu
            └── pc
```

Full architecture details: [`docs/architecture.md`](docs/architecture.md)

---

## Documentation

| Document | Path |
|---|---|
| Architecture | [`docs/architecture.md`](docs/architecture.md) |
| ISA | [`docs/isa.md`](docs/isa.md) |
| Memory map | [`docs/memory_map.md`](docs/memory_map.md) |
| Debug log | [`docs/debug_log.md`](docs/debug_log.md) |
| AXEL assembler | [`assembler/README.md`](assembler/README.md) |
| FPGA build | [`fpga/README.md`](fpga/README.md) |
| OpenLane / GDS | [`gds/README.md`](gds/README.md) |
| Post-route STA | [`sta/`](sta/) |

---

## Module Documentation

| Module | README | RTL | Testbench |
|---|---|---|---|
| ALU | [`Src/alu/README.md`](Src/alu/README.md) | [`Src/alu/alu.sv`](Src/alu/alu.sv) | [`Src/alu/test_alu.py`](Src/alu/test_alu.py) |
| Core | [`Src/core/README.md`](Src/core/README.md) | [`Src/core/core.sv`](Src/core/core.sv) | [`Src/core/test_core.py`](Src/core/test_core.py) |
| Decoder | [`Src/decoder/README.md`](Src/decoder/README.md) | [`Src/decoder/decoder.sv`](Src/decoder/decoder.sv) | [`Src/decoder/test_decoder.py`](Src/decoder/test_decoder.py) |
| DCR | [`Src/device_control_register/README.md`](Src/device_control_register/README.md) | [`Src/device_control_register/dcr.sv`](Src/device_control_register/dcr.sv) | [`Src/device_control_register/test_dcr.py`](Src/device_control_register/test_dcr.py) |
| Dispatcher | [`Src/dispatcher/README.md`](Src/dispatcher/README.md) | [`Src/dispatcher/dispatcher.sv`](Src/dispatcher/dispatcher.sv) | [`Src/dispatcher/test_dispatcher.py`](Src/dispatcher/test_dispatcher.py) |
| Fetcher | [`Src/fetcher/README.md`](Src/fetcher/README.md) | [`Src/fetcher/fetcher.sv`](Src/fetcher/fetcher.sv) | [`Src/fetcher/test_fetcher.py`](Src/fetcher/test_fetcher.py) |
| LSU | [`Src/lsu/README.md`](Src/lsu/README.md) | [`Src/lsu/lsu.sv`](Src/lsu/lsu.sv) | [`Src/lsu/test_lsu.py`](Src/lsu/test_lsu.py) |
| Memory Controller | [`Src/memory_controller/README.md`](Src/memory_controller/README.md) | [`Src/memory_controller/mem_controller.sv`](Src/memory_controller/mem_controller.sv) | [`Src/memory_controller/test_mem_controller.py`](Src/memory_controller/test_mem_controller.py) |
| PC | [`Src/pc/README.md`](Src/pc/README.md) | [`Src/pc/pc.sv`](Src/pc/pc.sv) | [`Src/pc/test_pc.py`](Src/pc/test_pc.py) |
| Registers | [`Src/registers/README.md`](Src/registers/README.md) | [`Src/registers/register_file.sv`](Src/registers/register_file.sv) | [`Src/registers/test_registers.py`](Src/registers/test_registers.py) |
| Scheduler | [`Src/scheduler/README.md`](Src/scheduler/README.md) | [`Src/scheduler/scheduler.sv`](Src/scheduler/scheduler.sv) | [`Src/scheduler/test_scheduler.py`](Src/scheduler/test_scheduler.py) |
| Top-Level GPU | [`Src/Top_level_GPU/README.md`](Src/Top_level_GPU/README.md) | [`Src/Top_level_GPU/top_level_gpu.sv`](Src/Top_level_GPU/top_level_gpu.sv) | [`Src/Top_level_GPU/test_top_level_gpu.py`](Src/Top_level_GPU/test_top_level_gpu.py) |
| Warp Stack | [`Src/warp_stack/README.md`](Src/warp_stack/README.md) | [`Src/warp_stack/warp_stack.sv`](Src/warp_stack/warp_stack.sv) | [`Src/warp_stack/test_warp_stack.py`](Src/warp_stack/test_warp_stack.py) |

---

## ISA Summary

The GPU uses 32-bit fixed-width instructions with a 6-bit opcode field.

![Instruction Encoding](assets/Architecture-images/instruction_encoding.png)

Instruction formats:

```text
R-type   register/register ALU operations
I-type   load / store / constant immediate
B-type   BRnzp SIMT branch
N-type   NOP, RET, SYNC
```

Supported instructions:

```text
NOP, ADD, SUB, MUL, DIV, MOD, SHL, SHR,
AND, OR, XOR, NOT, FMA, CMP, BRnzp,
LDR, STR, CONST, RET, IMUL, SAR, SYNC
```

Full ISA documentation: [`docs/isa.md`](docs/isa.md)

---

## SIMT Execution Model

Each thread lane has its own:

```text
register file    independent architectural state
ALU              per-thread arithmetic
LSU              per-thread memory access
PC               per-thread program counter
NZP flag         per-thread condition code
```

Each core shares:

```text
fetcher          single instruction fetch per cycle
decoder          shared decode result broadcast to all lanes
scheduler        active_mask gating, 10-state FSM
warp_stack       depth-4 divergence stack (sync_pc, saved_mask)
mem_controller   round-robin arbiter, 2-state FSM, request buffering
```

Divergence and reconvergence flow:

```text
CMP sets per-thread NZP
BRnzp evaluates taken_mask vs active_mask
divergence_detected triggers warp_stack push
taken group runs with taken_mask as active_mask
SYNC triggers warp_stack pop
saved_mask restored, threads reconverge
```

More detail: [`docs/architecture.md`](docs/architecture.md),
[`Src/warp_stack/README.md`](Src/warp_stack/README.md),
[`Src/scheduler/README.md`](Src/scheduler/README.md)

---

## Memory Controller

Each core contains a round-robin memory arbiter that serialises
the 4 per-thread LSU requests into a single memory channel.

```text
THREADS_PER_CORE = 4 LSU ports in
1 memory channel out

2-state FSM:   IDLE -> WAIT -> IDLE
rr_ptr:        advances after each completed transaction
pending[]:     one-cycle request pulses buffered while busy
resp_data[]:   packed 2D output [THREADS_PER_CORE-1:0][31:0]
```

This means the top-level data memory interface is 4-wide (one port per core),
not 16-wide (one port per thread). The wrapper only needs to model one BRAM
per core.

---

## AXEL Assembler

AXEL is a C-based assembler that emits `.hex` programs for the GPU.

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

Build and run:

```bash
cd assembler
make
```

Example kernel (SIMT ReLU):

```c
AxelGPU gpu;
axel_init(&gpu, 1, 4);          // 1 block, 4 threads

axel_ldr(&gpu, R1, THREAD_IDX, 0);   // load input
axel_cmp(&gpu, R0, R1);              // compare with 0
axel_brnzp(&gpu, NZP_N, skip);      // branch if negative
axel_str(&gpu, R1, THREAD_IDX, 4);  // store result
skip:
axel_const(&gpu, R1, 0);
axel_str(&gpu, R1, THREAD_IDX, 4);  // store 0
axel_sync(&gpu);
axel_ret(&gpu);

axel_compile(&gpu, "output.hex");
```

Full assembler documentation: [`assembler/README.md`](assembler/README.md)

---

## Memory Map

Neural-network workloads use Q8 fixed-point values:

```text
real_value = q8_value / 256
q8_value   = round(real_value * 256)
```

Main data memory layout (inference kernel):

| Address range | Contents |
|---|---|
| `0-15` | `W[4][4]` Q8 weight matrix |
| `16-19` | `x[4]` Q8 input vector |
| `20-23` | `y[4]` Q8 output vector |
| `24-27` | `t[4]` Q8 target vector |

SIMT ReLU kernel layout:

| Address range | Contents |
|---|---|
| `0-3` | Input values (signed) |
| `4-7` | Output values (ReLU applied) |

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

Run only SIMT ReLU (also writes trace_simt_relu.csv):

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

| Module | Tests | Status |
|---|---:|---|
| ALU | 6 | PASS |
| Registers | 4 | PASS |
| PC | 5 | PASS |
| Decoder | 5 | PASS |
| Fetcher | 3 | PASS |
| LSU | 3 | PASS |
| Memory Controller | 3 | PASS |
| Scheduler | 4 | PASS |
| Warp Stack | 3 | PASS |
| Core | 1 | PASS |
| Dispatcher | 3 | PASS |
| DCR | 3 | PASS |
| Top-Level GPU | 2 | PASS |
| **Total** | **47** | **47/47** |

---

## FPGA Target

Target board:

```text
Sipeed Tang Nano 20K
GW2AR-18C QN88
Gowin EDA, SV2017 mode
```

The current FPGA build targets the full SIMT configuration:

| Parameter | Value |
|---|---|
| `NUM_CORES` | 4 |
| `THREADS_PER_CORE` | 4 |
| `num_blocks` | 1 |
| `blockDim` | 4 |
| Clock | 3.375 MHz (27 MHz / 8) |
| UART | 115200 baud, pin 69 |

Each core gets one independent program BRAM and one independent data BRAM.
The round-robin `mem_controller` inside each core handles thread arbitration
before the request reaches the wrapper.

Expected UART output after flash:

```text
SIMT GPU
T:XXXXXXXX
R:00000005 00000000 00000008 00000000
```

Full FPGA documentation: [`fpga/README.md`](fpga/README.md)

---

## OpenLane / Sky130A GDS

The GPU has been taken through the full RTL-to-GDSII flow twice.

![GPU Layout](assets/gds/gpu_layout.png)

### SIMT (current)

| Metric | Value |
|---|---|
| Process | SkyWater Sky130A (130 nm) |
| Standard cell library | sky130_fd_sc_hd |
| Die area | 7.97 mm² (~2.82 x 2.82 mm) |
| Core utilization | 27.9% |
| Total std cells | 300,884 |
| LVS devices matched | 188,812 |
| LVS nets matched | 189,107 |
| Magic DRC violations | **0** |
| LVS result | **Circuits match uniquely** |
| Achievable frequency (TT) | **~32.9 MHz** (25°C / 1.80V, post-route SDF STA) |
| Achievable frequency (SS) | **~18.6 MHz** (100°C / 1.60V, post-route SDF STA) |
| Critical path | Core datapath mux tree (~31 ns, a2111oi + a31oi) |
| Tool | OpenLane 2.3.10 |

### SIMD (baseline)

| Metric | Value |
|---|---|
| Standard cells | 204,938 |
| Chip area | 1.977 mm² |
| Worst setup slack | +8.01 ns (~59 MHz) |
| Magic DRC violations | 5 |
| LVS result | Passed |

Post-route STA scripts and logs: [`sta/`](sta/)

Full GDS documentation: [`gds/README.md`](gds/README.md)

---

## Important Design Rules

1. Keep packed memory response buses aligned across RTL and cocotb.
   `resp_data` in `mem_controller.sv` must be packed 2D `[THREADS_PER_CORE-1:0][31:0]`.
2. Register writeback must be gated by scheduler `write_back_en`, decoder `write_back_en`, and `active_mask`.
3. Inactive SIMT lanes must not issue LSU requests, write registers, or advance PC.
4. `BRnzp` uses stored NZP from the PC module, not raw ALU output from the current cycle.
5. The instruction latch in `core.sv` (`instruction_raw` to `instruction`) is required for stable multicycle execution.
6. LSU request pulses are one cycle wide. The memory controller buffers them in `pending[]` while busy.

Detailed debug history: [`docs/debug_log.md`](docs/debug_log.md)

---

## Project Structure

```text
32-bit-Tiny-GPU/
├── Makefile
├── README.md
├── Src
│   ├── Top_level_GPU
│   │   ├── Makefile
│   │   ├── README.md
│   │   ├── __pycache__
│   │   │   └── test_top_level_gpu.cpython-312-pytest-9.0.3.pyc
│   │   ├── inference.py
│   │   ├── results.xml
│   │   ├── sim_build
│   │   │   ├── cmds.f
│   │   │   └── sim.vvp
│   │   ├── test_top_level_gpu.py
│   │   ├── tests
│   │   │   ├── __init__.py
│   │   │   ├── __pycache__
│   │   │   │   ├── __init__.cpython-312-pytest-9.0.3.pyc
│   │   │   │   ├── common.cpython-312-pytest-9.0.3.pyc
│   │   │   │   ├── memory_models.cpython-312-pytest-9.0.3.pyc
│   │   │   │   ├── test_phase08_mlp.cpython-312-pytest-9.0.3.pyc
│   │   │   │   ├── test_phase09_ldr.cpython-312-pytest-9.0.3.pyc
│   │   │   │   ├── test_phase10_mlp_8out.cpython-312-pytest-9.0.3.pyc
│   │   │   │   ├── test_phase11_mlp_8in.cpython-312-pytest-9.0.3.pyc
│   │   │   │   ├── test_phase12_mlp_q6.cpython-312-pytest-9.0.3.pyc
│   │   │   │   ├── test_phase13_digit_hidden.cpython-312-pytest-9.0.3.pyc
│   │   │   │   ├── test_phase14_digit_output.cpython-312-pytest-9.0.3.pyc
│   │   │   │   ├── test_phase15_digit64_hidden.cpython-312-pytest-9.0.3.pyc
│   │   │   │   ├── test_phase16_digit64_classifier.cpython-312-pytest-9.0.3.pyc
│   │   │   │   ├── test_phase17_q8_matvec.cpython-312-pytest-9.0.3.pyc
│   │   │   │   ├── test_phase18_q8_matmul.cpython-312-pytest-9.0.3.pyc
│   │   │   │   └── test_phase19_q8_matmul_4x8.cpython-312-pytest-9.0.3.pyc
│   │   │   ├── common.py
│   │   │   ├── memory_models.py
│   │   │   ├── test_phase08_mlp.py
│   │   │   ├── test_phase09_ldr.py
│   │   │   ├── test_phase10_mlp_8out.py
│   │   │   ├── test_phase11_mlp_8in.py
│   │   │   ├── test_phase12_mlp_q6.py
│   │   │   ├── test_phase13_digit_hidden.py
│   │   │   ├── test_phase14_digit_output.py
│   │   │   ├── test_phase15_digit64_hidden.py
│   │   │   ├── test_phase16_digit64_classifier.py
│   │   │   ├── test_phase17_q8_matvec.py
│   │   │   ├── test_phase18_q8_matmul.py
│   │   │   └── test_phase19_q8_matmul_4x8.py
│   │   ├── top_level_gpu.sv
│   │   └── trace_simt_relu.csv
│   ├── alu
│   │   ├── Makefile
│   │   ├── README.md
│   │   ├── __pycache__
│   │   │   └── test_alu.cpython-312-pytest-9.0.3.pyc
│   │   ├── alu.sv
│   │   ├── legacy
│   │   │   └── test_alu_old.py
│   │   ├── results.xml
│   │   ├── sim_build
│   │   │   ├── cmds.f
│   │   │   └── sim.vvp
│   │   └── tests
│   │       ├── __init__.py
│   │       ├── __pycache__
│   │       │   ├── __init__.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── common.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── test_alu_directed.cpython-312-pytest-9.0.3.pyc
│   │       │   └── test_alu_random.cpython-312-pytest-9.0.3.pyc
│   │       ├── common.py
│   │       ├── test_alu_directed.py
│   │       └── test_alu_random.py
│   ├── core
│   │   ├── Makefile
│   │   ├── README.md
│   │   ├── __pycache__
│   │   │   └── test_core.cpython-312-pytest-9.0.3.pyc
│   │   ├── core.sv
│   │   ├── legacy
│   │   │   └── test_core_old.py
│   │   ├── results.xml
│   │   ├── sim_build
│   │   │   ├── cmds.f
│   │   │   └── sim.vvp
│   │   └── tests
│   │       ├── __init__.py
│   │       ├── __pycache__
│   │       │   ├── __init__.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── common.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── test_core_directed.cpython-312-pytest-9.0.3.pyc
│   │       │   └── test_core_random.cpython-312-pytest-9.0.3.pyc
│   │       ├── common.py
│   │       ├── test_core_directed.py
│   │       └── test_core_random.py
│   ├── decoder
│   │   ├── Makefile
│   │   ├── README.md
│   │   ├── __pycache__
│   │   │   └── test_decoder.cpython-312-pytest-9.0.3.pyc
│   │   ├── decoder.sv
│   │   ├── legacy
│   │   │   └── test_decoder_old.py
│   │   ├── results.xml
│   │   ├── sim_build
│   │   │   ├── cmds.f
│   │   │   └── sim.vvp
│   │   └── tests
│   │       ├── __init__.py
│   │       ├── __pycache__
│   │       │   ├── __init__.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── common.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── test_decoder_directed.cpython-312-pytest-9.0.3.pyc
│   │       │   └── test_decoder_random.cpython-312-pytest-9.0.3.pyc
│   │       ├── common.py
│   │       ├── test_decoder_directed.py
│   │       └── test_decoder_random.py
│   ├── device_control_register
│   │   ├── Makefile
│   │   ├── README.md
│   │   ├── __pycache__
│   │   │   └── test_dcr.cpython-312-pytest-9.0.3.pyc
│   │   ├── dcr.sv
│   │   ├── legacy
│   │   │   └── test_dcr_old.py
│   │   ├── results.xml
│   │   ├── sim_build
│   │   │   ├── cmds.f
│   │   │   └── sim.vvp
│   │   └── tests
│   │       ├── __init__.py
│   │       ├── __pycache__
│   │       │   ├── __init__.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── common.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── test_dcr_directed.cpython-312-pytest-9.0.3.pyc
│   │       │   └── test_dcr_random.cpython-312-pytest-9.0.3.pyc
│   │       ├── common.py
│   │       ├── test_dcr_directed.py
│   │       └── test_dcr_random.py
│   ├── dispatcher
│   │   ├── Makefile
│   │   ├── README.md
│   │   ├── __pycache__
│   │   │   └── test_dispatcher.cpython-312-pytest-9.0.3.pyc
│   │   ├── dispatcher.sv
│   │   ├── legacy
│   │   │   └── test_dispatcher_old.py
│   │   ├── results.xml
│   │   ├── sim_build
│   │   │   ├── cmds.f
│   │   │   └── sim.vvp
│   │   └── tests
│   │       ├── __init__.py
│   │       ├── __pycache__
│   │       │   ├── __init__.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── common.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── test_dispatcher_directed.cpython-312-pytest-9.0.3.pyc
│   │       │   └── test_dispatcher_random.cpython-312-pytest-9.0.3.pyc
│   │       ├── common.py
│   │       ├── test_dispatcher_directed.py
│   │       └── test_dispatcher_random.py
│   ├── fetcher
│   │   ├── Makefile
│   │   ├── README.md
│   │   ├── __pycache__
│   │   │   └── test_fetcher.cpython-312-pytest-9.0.3.pyc
│   │   ├── fetcher.sv
│   │   ├── legacy
│   │   │   └── test_fetcher_old.py
│   │   ├── results.xml
│   │   ├── sim_build
│   │   │   ├── cmds.f
│   │   │   └── sim.vvp
│   │   └── tests
│   │       ├── __init__.py
│   │       ├── __pycache__
│   │       │   ├── __init__.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── common.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── test_fetcher_directed.cpython-312-pytest-9.0.3.pyc
│   │       │   └── test_fetcher_random.cpython-312-pytest-9.0.3.pyc
│   │       ├── common.py
│   │       ├── test_fetcher_directed.py
│   │       └── test_fetcher_random.py
│   ├── lsu
│   │   ├── Makefile
│   │   ├── README.md
│   │   ├── __pycache__
│   │   │   └── test_lsu.cpython-312-pytest-9.0.3.pyc
│   │   ├── legacy
│   │   │   └── test_lsu_old.py
│   │   ├── lsu.sv
│   │   ├── results.xml
│   │   ├── sim_build
│   │   │   ├── cmds.f
│   │   │   └── sim.vvp
│   │   └── tests
│   │       ├── __init__.py
│   │       ├── __pycache__
│   │       │   ├── __init__.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── common.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── test_lsu_directed.cpython-312-pytest-9.0.3.pyc
│   │       │   └── test_lsu_random.cpython-312-pytest-9.0.3.pyc
│   │       ├── common.py
│   │       ├── test_lsu_directed.py
│   │       └── test_lsu_random.py
│   ├── memory_controller
│   │   ├── Makefile
│   │   ├── README.md
│   │   ├── __pycache__
│   │   │   └── test_mem_controller.cpython-312-pytest-9.0.3.pyc
│   │   ├── legacy
│   │   │   └── test_mem_controller_old.py
│   │   ├── mem_controller.sv
│   │   ├── results.xml
│   │   ├── sim_build
│   │   │   ├── cmds.f
│   │   │   └── sim.vvp
│   │   └── tests
│   │       ├── __init__.py
│   │       ├── __pycache__
│   │       │   ├── __init__.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── common.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── test_mem_controller_directed.cpython-312-pytest-9.0.3.pyc
│   │       │   └── test_mem_controller_random.cpython-312-pytest-9.0.3.pyc
│   │       ├── common.py
│   │       ├── test_mem_controller_directed.py
│   │       └── test_mem_controller_random.py
│   ├── pc
│   │   ├── Makefile
│   │   ├── README.md
│   │   ├── __pycache__
│   │   │   └── test_pc.cpython-312-pytest-9.0.3.pyc
│   │   ├── legacy
│   │   │   └── test_pc_old.py
│   │   ├── pc.sv
│   │   ├── results.xml
│   │   ├── sim_build
│   │   │   ├── cmds.f
│   │   │   └── sim.vvp
│   │   └── tests
│   │       ├── __init__.py
│   │       ├── __pycache__
│   │       │   ├── __init__.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── common.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── test_pc_directed.cpython-312-pytest-9.0.3.pyc
│   │       │   └── test_pc_random.cpython-312-pytest-9.0.3.pyc
│   │       ├── common.py
│   │       ├── test_pc_directed.py
│   │       └── test_pc_random.py
│   ├── registers
│   │   ├── Makefile
│   │   ├── README.md
│   │   ├── __pycache__
│   │   │   └── test_registers.cpython-312-pytest-9.0.3.pyc
│   │   ├── legacy
│   │   │   └── test_registers_old.py
│   │   ├── register_file.sv
│   │   ├── results.xml
│   │   ├── sim_build
│   │   │   ├── cmds.f
│   │   │   └── sim.vvp
│   │   └── tests
│   │       ├── __init__.py
│   │       ├── __pycache__
│   │       │   ├── __init__.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── common.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── test_registers_directed.cpython-312-pytest-9.0.3.pyc
│   │       │   └── test_registers_random.cpython-312-pytest-9.0.3.pyc
│   │       ├── common.py
│   │       ├── test_registers_directed.py
│   │       └── test_registers_random.py
│   ├── scheduler
│   │   ├── Makefile
│   │   ├── README.md
│   │   ├── __pycache__
│   │   │   └── test_scheduler.cpython-312-pytest-9.0.3.pyc
│   │   ├── legacy
│   │   │   └── test_scheduler_old.py
│   │   ├── results.xml
│   │   ├── scheduler.sv
│   │   ├── sim_build
│   │   │   ├── cmds.f
│   │   │   └── sim.vvp
│   │   └── tests
│   │       ├── __init__.py
│   │       ├── __pycache__
│   │       │   ├── __init__.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── common.cpython-312-pytest-9.0.3.pyc
│   │       │   ├── test_scheduler_directed.cpython-312-pytest-9.0.3.pyc
│   │       │   └── test_scheduler_random.cpython-312-pytest-9.0.3.pyc
│   │       ├── common.py
│   │       ├── test_scheduler_directed.py
│   │       └── test_scheduler_random.py
│   └── warp_stack
│       ├── Makefile
│       ├── README.md
│       ├── __pycache__
│       │   └── test_warp_stack.cpython-312-pytest-9.0.3.pyc
│       ├── legacy
│       │   └── test_warp_stack_old.py
│       ├── results.xml
│       ├── sim_build
│       │   ├── cmds.f
│       │   └── sim.vvp
│       ├── tests
│       │   ├── __init__.py
│       │   ├── __pycache__
│       │   │   ├── __init__.cpython-312-pytest-9.0.3.pyc
│       │   │   ├── common.cpython-312-pytest-9.0.3.pyc
│       │   │   ├── test_warp_stack_directed.cpython-312-pytest-9.0.3.pyc
│       │   │   └── test_warp_stack_random.cpython-312-pytest-9.0.3.pyc
│       │   ├── common.py
│       │   ├── test_warp_stack_directed.py
│       │   └── test_warp_stack_random.py
│       └── warp_stack.sv
├── assembler
│   ├── Makefile
│   ├── README.md
│   ├── builds
│   │   ├── bin
│   │   │   ├── phase10_mlp_8out.axelbin
│   │   │   ├── phase11_mlp_8in.axelbin
│   │   │   ├── phase12_mlp_q6.axelbin
│   │   │   ├── phase13_digit_hidden.axelbin
│   │   │   ├── phase14_digit_output.axelbin
│   │   │   ├── phase15_digit64_hidden.axelbin
│   │   │   ├── phase16_digit64_output.axelbin
│   │   │   ├── phase17_q8_matvec_4x4.axelbin
│   │   │   ├── phase18_q8_matmul_4x4.axelbin
│   │   │   ├── phase19_q8_matmul_4x8.axelbin
│   │   │   ├── phase1_ldr_test.axelbin
│   │   │   ├── phase2_matmul.axelbin
│   │   │   ├── phase3_relu.axelbin
│   │   │   ├── phase4_forward.axelbin
│   │   │   ├── phase5_weight_update.axelbin
│   │   │   ├── phase6_simt_relu.axelbin
│   │   │   ├── phase7_dot4_test.axelbin
│   │   │   ├── phase8_mlp_inference.axelbin
│   │   │   ├── phase9_ldr_regbase_broadcast.axelbin
│   │   │   └── phase9_ldr_regbase_single.axelbin
│   │   ├── hex
│   │   │   ├── phase10_mlp_8out.hex
│   │   │   ├── phase11_mlp_8in.hex
│   │   │   ├── phase12_mlp_q6.hex
│   │   │   ├── phase13_digit_hidden.hex
│   │   │   ├── phase14_digit_output.hex
│   │   │   ├── phase15_digit64_hidden.hex
│   │   │   ├── phase16_digit64_output.hex
│   │   │   ├── phase17_q8_matvec_4x4.hex
│   │   │   ├── phase18_q8_matmul_4x4.hex
│   │   │   ├── phase19_q8_matmul_4x8.hex
│   │   │   ├── phase1_ldr_test.hex
│   │   │   ├── phase2_matmul.hex
│   │   │   ├── phase3_relu.hex
│   │   │   ├── phase4_forward.hex
│   │   │   ├── phase5_weight_update.hex
│   │   │   ├── phase6_simt_relu.hex
│   │   │   ├── phase7_dot4_test.hex
│   │   │   ├── phase8_mlp_inference.hex
│   │   │   ├── phase9_ldr_regbase_broadcast.hex
│   │   │   └── phase9_ldr_regbase_single.hex
│   │   ├── phase1
│   │   ├── phase10
│   │   ├── phase11
│   │   ├── phase12
│   │   ├── phase13
│   │   ├── phase14
│   │   ├── phase15
│   │   ├── phase16
│   │   ├── phase17
│   │   ├── phase18
│   │   ├── phase19
│   │   ├── phase2
│   │   ├── phase3
│   │   ├── phase4
│   │   ├── phase5
│   │   ├── phase6
│   │   ├── phase7
│   │   ├── phase8
│   │   ├── phase9_broadcast
│   │   ├── phase9_single
│   │   └── weights.json
│   ├── examples
│   │   ├── phase10_mlp_8out.c
│   │   ├── phase11_mlp_8in.c
│   │   ├── phase12_mlp_q6.c
│   │   ├── phase13_digit_hidden.c
│   │   ├── phase14_digit_output.c
│   │   ├── phase15_digit64_hidden.c
│   │   ├── phase16_digit64_output.c
│   │   ├── phase17_q8_matvec_4x4.c
│   │   ├── phase18_q8_matmul_4x4.c
│   │   ├── phase19_q8_matmul_4x8.c
│   │   ├── phase1_ldr_test.c
│   │   ├── phase2_matmul.c
│   │   ├── phase3_relu.c
│   │   ├── phase4_forward.c
│   │   ├── phase5_weight_update.c
│   │   ├── phase6_simt_relu.c
│   │   ├── phase7_dot4_test.c
│   │   ├── phase8_mlp_inference.c
│   │   ├── phase9_ldr_regbase_broadcast.c
│   │   ├── phase9_ldr_regbase_single.c
│   │   ├── test_add.c
│   │   └── test_axel.c
│   ├── include
│   │   ├── axel.h
│   │   └── gpu_asm.h
│   ├── src
│   │   ├── axel.c
│   │   └── gpu_asm.c
│   └── tools
│       ├── __pycache__
│       │   └── axelbin.cpython-312-pytest-9.0.3.pyc
│       └── axelbin.py
├── assets
│   ├── Architecture-images
│   │   ├── gpu_architecture.png
│   │   ├── instruction_encoding.png
│   │   └── software_layer_architecture.png
│   ├── Images-Components
│   │   ├── ALU-page-00001.jpg
│   │   ├── Core-page-00001.jpg
│   │   ├── DCR-page-00001.jpg
│   │   ├── Decoder-page-00001.jpg
│   │   ├── Dispatcher-page-00001.jpg
│   │   ├── Fetcher-page-00001.jpg
│   │   ├── GPU-page-00001.jpg
│   │   ├── LSU-page-00001.jpg
│   │   ├── Memory Controller-page-00001.jpg
│   │   ├── PC-page-00001.jpg
│   │   ├── Register-page-00001.jpg
│   │   ├── Scheduler-page-00001.jpg
│   │   └── warp_stack_page-0001.jpg
│   ├── PDFs
│   │   ├── ALU.pdf
│   │   ├── Core.pdf
│   │   ├── DCR.pdf
│   │   ├── Decoder.pdf
│   │   ├── Dispatcher.pdf
│   │   ├── Fetcher.pdf
│   │   ├── GPU.pdf
│   │   ├── LSU.pdf
│   │   ├── Memory Controller.pdf
│   │   ├── PC.pdf
│   │   ├── Register.pdf
│   │   ├── Scheduler.pdf
│   │   └── warp_stack.pdf
│   └── gds
│       └── gpu_layout.png
├── docs
│   ├── ai_inference_milestones.md
│   ├── architecture.md
│   ├── debug_log.md
│   ├── info.md
│   ├── isa.md
│   └── memory_map.md
├── fpga
│   ├── README.md
│   ├── constraints
│   │   └── gpu_top.cst
│   ├── data_mem.hex
│   ├── gpu_combined.v
│   ├── gpu_fpga_top.sv
│   └── prog_mem.hex
├── gds
│   ├── README.md
│   ├── gpu_simd_sky130a.gds
│   ├── gpu_simt_sky130a.def
│   ├── gpu_simt_sky130a.gds
│   ├── gpu_simt_sky130a.magic.gds
│   ├── metrics_simt.csv
│   ├── metrics_simt.json
│   └── reports
│       ├── drc_violations.magic.rpt
│       ├── gpu.drc
│       └── lvs_simt.rpt
├── info.yaml
├── make_leaf_schematic.sh
├── pyaxel
│   ├── README.md
│   ├── __init__.py
│   └── gpu.py
├── reports
│   ├── chk.rpt
│   ├── latch.rpt
│   ├── manufacturability.rpt
│   ├── post_dff.rpt
│   ├── pre_synth_chk.rpt
│   ├── pre_techmap.rpt
│   └── stat.rpt
├── schematics
│   ├── _build
│   │   ├── alu_sv2v.v
│   │   ├── core_sv2v.v
│   │   ├── dcr_sv2v.v
│   │   ├── decoder_sv2v.v
│   │   ├── dispatcher_sv2v.v
│   │   ├── fetcher_sv2v.v
│   │   ├── gpu_sv2v.v
│   │   ├── lsu_sv2v.v
│   │   ├── memory_controller_sv2v.v
│   │   ├── pc_sv2v.v
│   │   ├── registers_sv2v.v
│   │   ├── scheduler_sv2v.v
│   │   └── warp_stack_sv2v.v
│   ├── json
│   │   ├── alu.json
│   │   ├── core.json
│   │   ├── dcr.json
│   │   ├── decoder.json
│   │   ├── dispatcher.json
│   │   ├── fetcher.json
│   │   ├── gpu.json
│   │   ├── lsu.json
│   │   ├── memory_controller.json
│   │   ├── pc.json
│   │   ├── registers.json
│   │   ├── scheduler.json
│   │   └── warp_stack.json
│   ├── logs
│   │   ├── alu.files.log
│   │   ├── alu.netlistsvg.log
│   │   ├── alu.sv2v.log
│   │   ├── alu.yosys.log
│   │   ├── core.files.log
│   │   ├── core.netlistsvg.log
│   │   ├── core.sv2v.log
│   │   ├── core.yosys.log
│   │   ├── dcr.files.log
│   │   ├── dcr.netlistsvg.log
│   │   ├── dcr.sv2v.log
│   │   ├── dcr.yosys.log
│   │   ├── decoder.files.log
│   │   ├── decoder.netlistsvg.log
│   │   ├── decoder.sv2v.log
│   │   ├── decoder.yosys.log
│   │   ├── dispatcher.files.log
│   │   ├── dispatcher.netlistsvg.log
│   │   ├── dispatcher.sv2v.log
│   │   ├── dispatcher.yosys.log
│   │   ├── fetcher.files.log
│   │   ├── fetcher.netlistsvg.log
│   │   ├── fetcher.sv2v.log
│   │   ├── fetcher.yosys.log
│   │   ├── gpu.files.log
│   │   ├── gpu.netlistsvg.log
│   │   ├── gpu.sv2v.log
│   │   ├── gpu.yosys.log
│   │   ├── lsu.files.log
│   │   ├── lsu.netlistsvg.log
│   │   ├── lsu.sv2v.log
│   │   ├── lsu.yosys.log
│   │   ├── memory_controller.files.log
│   │   ├── memory_controller.netlistsvg.log
│   │   ├── memory_controller.sv2v.log
│   │   ├── memory_controller.yosys.log
│   │   ├── pc.files.log
│   │   ├── pc.netlistsvg.log
│   │   ├── pc.sv2v.log
│   │   ├── pc.yosys.log
│   │   ├── registers.files.log
│   │   ├── registers.netlistsvg.log
│   │   ├── registers.sv2v.log
│   │   ├── registers.yosys.log
│   │   ├── scheduler.files.log
│   │   ├── scheduler.netlistsvg.log
│   │   ├── scheduler.sv2v.log
│   │   ├── scheduler.yosys.log
│   │   ├── warp_stack.files.log
│   │   ├── warp_stack.netlistsvg.log
│   │   ├── warp_stack.sv2v.log
│   │   └── warp_stack.yosys.log
│   ├── sv2v
│   │   ├── alu_sv2v.v
│   │   ├── core_sv2v.v
│   │   ├── dcr_sv2v.v
│   │   ├── decoder_sv2v.v
│   │   ├── dispatcher_sv2v.v
│   │   ├── fetcher_sv2v.v
│   │   ├── gpu_sv2v.v
│   │   ├── lsu_sv2v.v
│   │   ├── memory_controller_sv2v.v
│   │   ├── pc_sv2v.v
│   │   ├── registers_sv2v.v
│   │   ├── scheduler_sv2v.v
│   │   └── warp_stack_sv2v.v
│   └── svg
│       ├── alu.svg
│       ├── core.svg
│       ├── dcr.svg
│       ├── decoder.svg
│       ├── dispatcher.svg
│       ├── fetcher.svg
│       ├── gpu.svg
│       ├── lsu.svg
│       ├── memory_controller.svg
│       ├── pc.svg
│       ├── registers.svg
│       ├── scheduler.svg
│       └── warp_stack.svg
└── sta
    ├── sta_ss.log
    ├── sta_ss.tcl
    ├── sta_tt.log
    └── sta_tt.tcl
```
---

## Known Limitations

- Program and data memories are modeled in cocotb for simulation (no RTL SRAM block).
- Memory is word-addressed only. Byte-addressable access is not implemented.
- Branch offsets are unsigned forward-only. Backward branches require assembler workarounds.
- `CONST` loads a 16-bit zero-extended immediate only. No sign-extension variant.
- `DIV` and `MOD` are replaced with `32'b0` in the synthesis target (no hardware divider on Sky130A).
- `kernel_done` is sticky until reset. Repeated kernel launches require a full reset cycle.
- Critical path is a wide mux tree through `a2111oi_2` and `a31oi_2` cells, limiting TT frequency to ~32.9 MHz. A floorplan re-run with tighter placement constraints is planned.

---

## Future Work

- Tighten floorplan to reduce 7.97 mm² die area and improve critical path
- Implement AXEL-C compiler (C subset to AXEL assembly)
- Flash and verify FPGA SIMT build on Tang Nano 20K
- Implement DIV/MOD as iterative multi-cycle hardware units
- UVM verification suite
- Cadence Genus/Xcelium synthesis (pending lab access)
- Phase 1: AI ISA extensions (DOT4, RELU, CLAMP, ARGMAX)
- Phase 2: Q8 neural network inference on GPU
- Phase 4: Memory-mapped matmul accelerator

---

## Author

**Austin Antony**
B.Tech Applied Electronics and Instrumentation Engineering
Rajagiri School of Engineering and Technology
CTO and Co-founder, Virtusco