# FPGA Build: Sipeed Tang Nano 20K

## Overview

This folder contains the FPGA build files for the 32-bit Tiny GPU.

The target board is:

```text
Sipeed Tang Nano 20K
FPGA: Gowin GW2AR-18C QN88
Onboard clock: 27 MHz
````

The FPGA build proves that the Tiny GPU RTL can be synthesized, placed, routed, flashed, and observed on real hardware.

Because the Tang Nano 20K is resource-limited compared to the full simulation configuration, the FPGA version uses a reduced single-core, single-thread configuration and executes multiple blocks sequentially.

---

## Source Files

```text
fpga/
├── gpu_combined.v
├── gpu_fpga_top.sv
├── prog_mem.hex
├── data_mem.hex
└── constraints/
    └── gpu_top.cst
```

| File                      | Purpose                                                                    |
| ------------------------- | -------------------------------------------------------------------------- |
| `gpu_combined.v`          | Flattened/synthesis-ready Verilog version of the GPU RTL                   |
| `gpu_fpga_top.sv`         | FPGA wrapper/top module for clock, LEDs, UART, memory init, and launch FSM |
| `prog_mem.hex`            | Program memory contents loaded by the FPGA wrapper                         |
| `data_mem.hex`            | Initial data memory contents loaded by the FPGA wrapper                    |
| `constraints/gpu_top.cst` | Tang Nano 20K pin constraints                                              |

---

## FPGA Configuration

The full simulation design uses 4 cores and 4 threads per core.

The FPGA build uses a smaller configuration:

| Parameter          | Simulation |       FPGA |
| ------------------ | ---------: | ---------: |
| `NUM_CORES`        |          4 |          1 |
| `THREADS_PER_CORE` |          4 |          1 |
| `num_blocks`       |          1 |          4 |
| Execution model    |   Parallel | Sequential |

In simulation:

```text
4 cores × 4 threads/core = 16 total thread lanes
```

In the FPGA build:

```text
1 core × 1 thread/core = 1 physical thread lane
```

To preserve the same output behavior, the FPGA version launches 4 blocks sequentially. Each block acts like one logical thread.

---

## Why the FPGA Build Uses 1 Core × 1 Thread

The Tang Nano 20K has limited LUTs, registers, and routing resources.

A full 4-core × 4-thread configuration is much larger because it duplicates:

```text
register files
ALUs
LSUs
PCs
thread-lane wiring
memory request paths
scheduler-related control fanout
```

The reduced FPGA build keeps the architecture demonstrable while fitting the board.

The key idea is:

```text
Simulation:
  one block with four parallel threads

FPGA:
  four blocks with one thread each
```

This gives numerically equivalent output for the current kernels.

---

## `THREAD_IDX` FPGA Patch

In normal simulation mode:

```text
R29 / THREAD_IDX = threadIdx
```

But in the FPGA configuration:

```text
THREADS_PER_CORE = 1
blockDim = 1
```

There is only one physical thread, so `threadIdx` would always be zero.

To make each sequential block compute a different output element, the register file returns `blockIdx` as `THREAD_IDX` when `blockDim == 1`.

Behavior:

```text
if blockDim == 1:
    R29 / THREAD_IDX = blockIdx
else:
    R29 / THREAD_IDX = threadIdx
```

This allows four sequential blocks to behave like four logical thread indices.

|   Block | `blockIdx` | Effective `THREAD_IDX` |
| ------: | ---------: | ---------------------: |
| Block 0 |          0 |                      0 |
| Block 1 |          1 |                      1 |
| Block 2 |          2 |                      2 |
| Block 3 |          3 |                      3 |

This patch is implemented in the register file logic used by the FPGA build.

---

## FPGA-Specific RTL Notes

The FPGA build uses `gpu_combined.v`, which is a synthesis-ready combined Verilog file.

Important FPGA-specific changes may include:

```text
simulation-only code removed
$dumpfile / $dumpvars removed
single-thread configuration
thread_keep_alive output retained
synthesis keep attributes added where needed
DIV/MOD disabled or simplified in synthesis-target versions if required
```

### `thread_keep_alive`

The FPGA wrapper uses `thread_keep_alive` to keep internal datapath activity visible to synthesis.

Without an externally observable signal, synthesis tools can sometimes optimize away logic that appears unused from the top-level outputs.

The signal is typically derived from activity inside the core/thread datapath and then connected to an LED or other observable output.

---

## Top-Level FPGA Wrapper

The FPGA wrapper is:

```text
fpga/gpu_fpga_top.sv
```

It is responsible for board-level integration:

```text
clock input
reset/start sequencing
program memory initialization
data memory initialization
DCR launch writes
kernel_done observation
UART output
LED output
```

The wrapper acts like a small hardware testbench around the GPU.

Typical flow:

```text
1. Initialize program memory from prog_mem.hex.
2. Initialize data memory from data_mem.hex.
3. Write num_blocks through DCR.
4. Write blockDim through DCR.
5. Pulse start through DCR.
6. Wait for kernel_done.
7. Print results over UART.
8. Drive LEDs for status/debug.
```

---

## Pin Assignments

Tang Nano 20K pin assignments:

| Signal    | Pin | Notes                               |
| --------- | --: | ----------------------------------- |
| `clk`     |  52 | 27 MHz onboard oscillator           |
| `led[0]`  |  10 | `kernel_done` indicator, active-low |
| `led[1]`  |  11 | Heartbeat blink, active-low         |
| `led[2]`  |  13 | Debug/status LED                    |
| `led[3]`  |  14 | Debug/status LED                    |
| `led[4]`  |  15 | Debug/status LED                    |
| `led[5]`  |  16 | Debug/status LED                    |
| `uart_tx` |  69 | UART TX to BL616 USB-UART bridge    |

Check the active-low LED behavior before interpreting output:

```text
LED output 0 -> LED ON
LED output 1 -> LED OFF
```

---

## Constraints File

Pin constraints are stored in:

```text
fpga/constraints/gpu_top.cst
```

The `.cst` file maps the FPGA top-level ports to physical Tang Nano 20K pins.

Make sure the top-level module port names in `gpu_fpga_top.sv` match the names used in the `.cst` file.

---

## UART Output

After flashing, open the board’s UART port at:

```text
115200 baud
8 data bits
no parity
1 stop bit
```

Expected output format:

```text
GPU DONE
T:XXXXXXXX
Y: YYYYYYYY YYYYYYYY YYYYYYYY YYYYYYYY
```

Meaning:

| Output       | Meaning                                       |
| ------------ | --------------------------------------------- |
| `GPU DONE`   | Kernel completed                              |
| `T:XXXXXXXX` | Cycle count until `kernel_done`               |
| `Y:`         | Output vector values in Q8 hexadecimal format |

To convert Q8 output to real value:

```text
real_value = signed_q8_value / 256.0
```

Example:

```text
0x00000200 -> 512 / 256 = 2.0
```

For negative values, interpret the 32-bit value as signed two’s complement first.

---

## Toolchain

Typical tool split:

```text
WSL / Ubuntu side:
  sv2v
  Icarus Verilog
  cocotb
  assembler build
  hex generation

Windows side:
  Gowin EDA Education Edition
  Tang Nano 20K synthesis / place / route / flash
  Zadig driver setup if needed
```

Recommended tools:

| Tool                        | Purpose                                          |
| --------------------------- | ------------------------------------------------ |
| `sv2v`                      | Convert SystemVerilog to Verilog if needed       |
| `iverilog`                  | Simulation                                       |
| `cocotb`                    | Verification                                     |
| `gcc`                       | Build AXEL assembler examples                    |
| Gowin EDA Education Edition | FPGA synthesis/place/route/programming           |
| Zadig                       | One-time USB driver setup on Windows if required |

---

## Gowin Project Settings

Use these board/device settings in Gowin EDA:

```text
Device family: GW2AR
Device: GW2AR-18C
Package: QN88
Board: Sipeed Tang Nano 20K
Language: Verilog / SystemVerilog
```

If Gowin asks for a language version, use SystemVerilog 2017 where available.

---

## Build Flow

## 1. Generate AXEL program hex

From the repository root:

```bash
cd assembler
make
```

This generates kernel `.hex` files in:

```text
assembler/builds/
```

For FPGA, copy or convert the intended program into:

```text
fpga/prog_mem.hex
```

---

## 2. Prepare initial data memory

Create or update:

```text
fpga/data_mem.hex
```

This file should contain initial data memory values needed by the FPGA kernel.

For Q8 inference/forward tests, data memory usually contains:

```text
W[0..15]   -> weights
x[16..19]  -> input vector
```

See:

```text
../docs/memory_map.md
```

for the full memory layout.

---

## 3. Generate combined Verilog if needed

If using `sv2v`, generate a synthesis-ready combined Verilog file from the RTL sources.

Typical idea:

```bash
sv2v <RTL source files> > fpga/gpu_combined.v
```

The exact command depends on the current module list and include paths.

After generation, inspect `gpu_combined.v` for:

```text
no $dumpfile
no $dumpvars
no simulation-only code
top-level module names match the wrapper
```

---

## 4. Open Gowin EDA

Open the Gowin project or create a new one with:

```text
fpga/gpu_fpga_top.sv
fpga/gpu_combined.v
fpga/constraints/gpu_top.cst
```

Set the top-level module to the FPGA wrapper, usually:

```text
gpu_fpga_top
```

---

## 5. Synthesize, place, and route

In Gowin EDA, run:

```text
Synthesis
Place & Route
Timing Analysis
Bitstream Generation
```

Check that:

```text
no critical synthesis errors
clock pin is correctly constrained
UART pin is correctly constrained
LED pins are correctly constrained
timing is acceptable for the 27 MHz board clock
```

---

## 6. Flash the board

Use the Gowin Programmer to flash the generated bitstream to the Tang Nano 20K.

If the board is not detected, check:

```text
USB cable supports data
correct driver installed
Zadig WinUSB driver configured if needed
board appears in Device Manager / lsusb
```

---

## 7. Open UART

Open the higher-numbered COM port at:

```text
115200 baud
8N1
```

Then reset or power-cycle the board.

Expected result:

```text
GPU DONE
T:...
Y: ...
```

---

## Program and Data Memory Files

## `prog_mem.hex`

This file contains GPU instruction memory for the FPGA wrapper.

Each line should be one 32-bit instruction word:

```text
3C3D0000
34010000
38802002
44200000
54000000
403D0004
48000000
```

No `0x` prefix is required.

## `data_mem.hex`

This file contains initial data memory values.

Each line should be one 32-bit word.

Example for a small ReLU test:

```text
00000005
FFFFFFFD
00000008
FFFFFFFF
00000000
00000000
00000000
00000000
```

---

## FPGA Execution Model

The FPGA execution model is sequential block execution.

For example, a 4-output kernel runs as:

```text
Block 0 computes y[0]
Block 1 computes y[1]
Block 2 computes y[2]
Block 3 computes y[3]
```

This is different from the simulation model, where four thread lanes can compute outputs in parallel.

However, because `THREAD_IDX` maps to `blockIdx` in single-thread mode, the address calculations remain the same.

Example instruction:

```text
STR R1, THREAD_IDX, 4
```

In FPGA mode:

```text
THREAD_IDX = blockIdx
```

So:

```text
Block 0 -> Memory[4] = R1
Block 1 -> Memory[5] = R1
Block 2 -> Memory[6] = R1
Block 3 -> Memory[7] = R1
```

---

## Expected FPGA Output

For the SIMT ReLU-style input:

```text
mem[0] =  5
mem[1] = -3
mem[2] =  8
mem[3] = -1
```

Expected output:

```text
mem[4] = 5
mem[5] = 0
mem[6] = 8
mem[7] = 0
```

UART may print these as hex:

```text
Y: 00000005 00000000 00000008 00000000
```

---

## Relationship to Simulation

Simulation target:

```text
NUM_CORES        = 4
THREADS_PER_CORE = 4
num_blocks       = 1
```

FPGA target:

```text
NUM_CORES        = 1
THREADS_PER_CORE = 1
num_blocks       = 4
blockDim         = 1
```

The result is intended to be numerically equivalent for supported kernels.

The main difference is performance:

```text
simulation architecture -> parallel logical execution
FPGA build              -> sequential execution across blocks
```

---

## Current Limitations


- FPGA build uses 1 core and 1 thread for area reasons.
- It does not exercise full 4-core × 4-thread parallel SIMT hardware.
- Full warp-stack divergence is not meaningfully stressed when THREADS_PER_CORE = 1.
- Some synthesis-target versions may disable DIV/MOD.
- FPGA memory is initialized from hex files rather than loaded dynamically by a host.
- No full runtime driver exists yet.
- UART output is simple debug text, not a structured protocol.
- Timing/resource numbers should be updated after each Gowin build.


---

## Recommended Future Work


1. Add exact Gowin utilization report.
2. Add Fmax/timing report.
3. Add screenshots of Gowin synthesis/place-route success.
4. Add UART output screenshot.
5. Add a repeatable script to regenerate gpu_combined.v.
6. Add an automated hex-copy step from assembler/builds to fpga/.
7. Expand the FPGA build toward NUM_CORES=4, THREADS_PER_CORE=4 if resources allow.
8. Add a small host-side UART parser for output values.
9. Add BRAM-based program/data memory with cleaner initialization.
10. Add switches/buttons for selecting kernels or restarting execution.

---

## Related Documentation

| Document       | Path                                                               |
| -------------- | ------------------------------------------------------------------ |
| Root README    | [`../README.md`](../README.md)                                     |
| Architecture   | [`../docs/architecture.md`](../docs/architecture.md)               |
| ISA            | [`../docs/isa.md`](../docs/isa.md)                                 |
| Memory map     | [`../docs/memory_map.md`](../docs/memory_map.md)                   |
| Debug log      | [`../docs/debug_log.md`](../docs/debug_log.md)                     |
| AXEL assembler | [`../assembler/README.md`](../assembler/README.md)                 |
| Top-level GPU  | [`../Src/Top_level_GPU/README.md`](../Src/Top_level_GPU/README.md) |
| Register file  | [`../Src/registers/README.md`](../Src/registers/README.md)         |
| OpenLane / GDS | [`../gds/README.md`](../gds/README.md)                             |

---

## Summary

The FPGA build demonstrates that the Tiny GPU can move beyond simulation and run on real hardware.

The key implementation choice is the reduced single-core, single-thread configuration:

```text
1 core
1 thread
4 sequential blocks
```

combined with the register-file helper:

```text
THREAD_IDX = blockIdx when blockDim == 1
```

This lets the FPGA build produce the same logical output as the 4-thread simulation while fitting on the Tang Nano 20K.

The current FPGA build is therefore a practical hardware validation target, while the full 4-core × 4-thread configuration remains the main simulation and ASIC architecture.