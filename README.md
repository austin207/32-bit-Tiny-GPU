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
│   ├── gpu_combined.v        (sv2v output, 13 modules)
│   ├── gpu_fpga_top.sv       (Tang Nano 20K wrapper)
│   ├── prog_mem.hex
│   └── data_mem.hex
├── gds/
│   ├── gpu_simt_sky130a.gds
│   ├── gpu_simd_sky130a.gds
│   ├── metrics_simt.json
│   └── reports/
├── pyaxel/
│   ├── __init__.py
│   ├── gpu.py
│   └── README.md
├── reports/
├── schematics/
├── sta/
│   ├── sta_tt.tcl            (TT corner STA script)
│   ├── sta_ss.tcl            (SS corner STA script)
│   ├── sta_tt.log            (TT corner results)
│   └── sta_ss.log            (SS corner results)
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