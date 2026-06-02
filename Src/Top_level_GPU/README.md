# Top-Level GPU

## Overview

`gpu` is the top-level integration module for the Tiny GPU.

It connects the launch-control path, block dispatcher, multiple SIMT cores, program memory interface, data memory interface, and top-level debug/keep-alive output.

At this level, the design contains:

```text
DCR
dispatcher
NUM_CORES × core
program memory request/response ports
data memory request/response ports
thread_keep_alive reduction logic
```

The top-level module does not execute instructions directly. It coordinates launch configuration, block assignment, per-core execution, and external memory communication.

## RTL schematic

![Top-Level GPU RTL schematic](../../assets/Images-Components/Top%20Level%20GPU-page-00001.jpg)

If the image file has a different exact name, update the path above to match the file in `assets/Images-Components/`.

## Source files

```text
Src/Top_level_GPU/top_level_gpu.sv
Src/Top_level_GPU/test_top_level_gpu.py
Src/Top_level_GPU/inference.py
Src/Top_level_GPU/Makefile
```

Related modules:

```text
Src/device_control_register/dcr.sv
Src/dispatcher/dispatcher.sv
Src/core/core.sv
Src/scheduler/scheduler.sv
Src/fetcher/fetcher.sv
Src/decoder/decoder.sv
Src/alu/alu.sv
Src/lsu/lsu.sv
Src/pc/pc.sv
Src/registers/register_file.sv
Src/memory_controller/mem_controller.sv
Src/warp_stack/warp_stack.sv
```

## Position in the project

`gpu` is the main hardware top for simulation.

```text
host / cocotb testbench
        │
        │ DCR writes
        ▼
      gpu
        │
        ├── DCR
        ├── dispatcher
        ├── core_gen[0]
        ├── core_gen[1]
        ├── core_gen[2]
        ├── core_gen[3]
        ├── program memory interface
        └── data memory interface
```

The top-level cocotb tests act as the external host and memory system.

## Module declaration

```systemverilog
module gpu #(
    parameter NUM_CORES        = 4,
    parameter THREADS_PER_CORE = 4,
    parameter TOTAL_THREADS    = NUM_CORES * THREADS_PER_CORE
) (
    input  logic clk,
    input  logic rst,

    input  logic        dcr_write_en,
    input  logic [1:0]  dcr_addr,
    input  logic [31:0] dcr_data,
    output logic        kernel_done,

    output logic [31:0] thread_keep_alive,

    output logic [NUM_CORES-1:0]       prog_mem_req_valid,
    output logic [31:0]                prog_mem_req_addr  [NUM_CORES-1:0],
    input  logic [NUM_CORES-1:0]       prog_mem_resp_valid,
    input  logic [31:0]                prog_mem_resp_data [NUM_CORES-1:0],

    output logic [NUM_CORES-1:0]       data_mem_req_valid,
    output logic [31:0]                data_mem_req_addr  [NUM_CORES-1:0],
    output logic [NUM_CORES-1:0]       data_mem_req_rw,
    output logic [31:0]                data_mem_req_data  [NUM_CORES-1:0],
    input  logic [NUM_CORES-1:0]       data_mem_resp_valid,
    input  logic [NUM_CORES-1:0][31:0] data_mem_resp_data
);
```

## Parameters

| Parameter          |                        Default | Description                                  |
| ------------------ | -----------------------------: | -------------------------------------------- |
| `NUM_CORES`        |                            `4` | Number of GPU cores instantiated             |
| `THREADS_PER_CORE` |                            `4` | Number of SIMT thread lanes inside each core |
| `TOTAL_THREADS`    | `NUM_CORES * THREADS_PER_CORE` | Total logical thread lanes across all cores  |

## Port description

| Port                  | Direction | Width / Type                   | Description                                            |
| --------------------- | --------- | ------------------------------ | ------------------------------------------------------ |
| `clk`                 | input     | 1                              | Clock                                                  |
| `rst`                 | input     | 1                              | Reset                                                  |
| `dcr_write_en`        | input     | 1                              | Host/testbench DCR write enable                        |
| `dcr_addr`            | input     | 2                              | DCR register/action address                            |
| `dcr_data`            | input     | 32                             | DCR write data                                         |
| `kernel_done`         | output    | 1                              | Asserted when dispatcher completes all launched blocks |
| `thread_keep_alive`   | output    | 32                             | XOR-reduced debug/keep-alive signal from all cores     |
| `prog_mem_req_valid`  | output    | `NUM_CORES`                    | Per-core program memory request-valid                  |
| `prog_mem_req_addr`   | output    | unpacked `[31:0] [NUM_CORES]`  | Per-core program memory request address                |
| `prog_mem_resp_valid` | input     | `NUM_CORES`                    | Per-core program memory response-valid                 |
| `prog_mem_resp_data`  | input     | unpacked `[31:0] [NUM_CORES]`  | Per-core program memory instruction data               |
| `data_mem_req_valid`  | output    | `NUM_CORES`                    | Per-core data memory request-valid                     |
| `data_mem_req_addr`   | output    | unpacked `[31:0] [NUM_CORES]`  | Per-core data memory request address                   |
| `data_mem_req_rw`     | output    | `NUM_CORES`                    | Per-core read/write selector. `1 = read`, `0 = write`  |
| `data_mem_req_data`   | output    | unpacked `[31:0] [NUM_CORES]`  | Per-core data memory write data                        |
| `data_mem_resp_valid` | input     | `NUM_CORES`                    | Per-core data memory response-valid                    |
| `data_mem_resp_data`  | input     | packed `[NUM_CORES-1:0][31:0]` | Packed per-core data memory response data              |

## Top-level architecture

```text
DCR
 │
 │ num_blocks, blockDim, start
 ▼
dispatcher
 │
 │ core_start[i], blockIdx_out[i]
 ▼
core_gen[i].core_inst
 │
 ├── program memory interface
 ├── data memory interface
 ├── block_done[i]
 └── core_keep_alive[i]
```

The top-level `gpu` module wires together the DCR, dispatcher, and all core instances.

## DCR integration

The DCR receives writes from the host/testbench:

```systemverilog
dcr dcr_inst (
    .clk          (clk),
    .rst          (rst),
    .dcr_write_en (dcr_write_en),
    .dcr_addr     (dcr_addr),
    .dcr_data     (dcr_data),
    .num_blocks   (num_blocks),
    .blockDim     (blockDim),
    .start        (start)
);
```

DCR outputs:

```text
num_blocks -> total blocks to launch
blockDim   -> threads per block
start      -> one-cycle start pulse
```

## Dispatcher integration

The dispatcher receives launch configuration from DCR and completion signals from cores.

```systemverilog
dispatcher dispatcher_inst (
    .clk          (clk),
    .rst          (rst),
    .dispatch_en  (start),
    .num_blocks   (num_blocks),
    .blockDim     (blockDim),
    .block_done   (block_done),
    .core_start   (core_start),
    .blockIdx_out (blockIdx_out),
    .kernel_done  (kernel_done)
);
```

Dispatcher outputs:

```text
core_start[i]   -> starts/marks core i active
blockIdx_out[i] -> block index assigned to core i
kernel_done     -> all blocks assigned and completed
```

## Core generation

The top-level instantiates `NUM_CORES` core instances using a generate loop:

```systemverilog
generate
    for (i = 0; i < NUM_CORES; i = i + 1) begin : core_gen
        ...
        core #(.THREADS_PER_CORE(THREADS_PER_CORE)) core_inst (...);
    end
endgenerate
```

Each generated core gets:

```text
core_start[i]
blockIdx_out[i]
blockDim
program memory lane i
data memory lane i
block_done[i]
core_keep_alive[i]
```

## Per-core wiring

Each core has local intermediate wires for some array ports:

```systemverilog
logic [31:0] data_mem_req_addr_wire;
logic [31:0] data_mem_req_data_wire;
logic [31:0] data_mem_resp_data_wire;
logic [31:0] prog_mem_req_addr_wire;
logic [31:0] prog_mem_resp_data_wire;
```

These wires connect the core instance to the top-level memory arrays:

```systemverilog
assign prog_mem_req_addr[i]    = prog_mem_req_addr_wire;
assign prog_mem_resp_data_wire = prog_mem_resp_data[i];

assign data_mem_req_addr[i]    = data_mem_req_addr_wire;
assign data_mem_req_data[i]    = data_mem_req_data_wire;
assign data_mem_resp_data_wire = data_mem_resp_data[i];
```

## Program memory interface

The program memory interface is per-core.

```text
request:
  prog_mem_req_valid[i]
  prog_mem_req_addr[i]

response:
  prog_mem_resp_valid[i]
  prog_mem_resp_data[i]
```

At top level, `prog_mem_resp_data` remains unpacked:

```systemverilog
input logic [31:0] prog_mem_resp_data [NUM_CORES-1:0]
```

In cocotb, this means the testbench can drive per-core instruction data directly:

```python
dut.prog_mem_resp_data[i].value = instruction
```

The top-level program memory model fetches the instruction based on each core’s fetch address.

## Data memory interface

The data memory request interface is per-core:

```text
request:
  data_mem_req_valid[i]
  data_mem_req_addr[i]
  data_mem_req_rw[i]
  data_mem_req_data[i]
```

The data memory response-valid is per-core:

```text
data_mem_resp_valid[i]
```

The data memory response-data bus is packed:

```systemverilog
input logic [NUM_CORES-1:0][31:0] data_mem_resp_data
```

Each core receives:

```systemverilog
data_mem_resp_data[i]
```

## Packed data memory response bus

`data_mem_resp_data` is intentionally packed:

```systemverilog
input logic [NUM_CORES-1:0][31:0] data_mem_resp_data
```

This matches the packed response-data style used deeper in the memory path.

In cocotb, the testbench drives the whole packed bus as one integer:

```python
packed = 0
for c in range(NUM_CORES):
    packed |= (resp_data_per_core[c] & 0xFFFFFFFF) << (c * 32)

dut.data_mem_resp_data.value = packed
```

Do not drive it like this:

```python
dut.data_mem_resp_data[i].value = value
```

because the top-level response-data bus is packed.

## Read/write convention

The top-level data memory interface uses:

```text
1 = read
0 = write
```

So:

```text
data_mem_req_rw[i] = 1 -> core i requests a read
data_mem_req_rw[i] = 0 -> core i requests a write
```

The cocotb data memory model follows this convention:

```python
if rw == 0:
    memory[addr] = data
    resp_data_per_core[core_id] = 0
else:
    resp_data_per_core[core_id] = memory.get(addr, 0) & 0xFFFFFFFF
```

## `thread_keep_alive`

Each core produces a 32-bit `thread_keep_alive` signal.

At top level, all core keep-alive signals are XOR-reduced into one output:

```systemverilog
logic [31:0] _top_keep_xor [NUM_CORES:0];
assign _top_keep_xor[0] = 32'b0;

generate
    for (m = 0; m < NUM_CORES; m++) begin : top_keep_xor_gen
        assign _top_keep_xor[m+1] = _top_keep_xor[m] ^ core_keep_alive[m];
    end
endgenerate

assign thread_keep_alive = _top_keep_xor[NUM_CORES];
```

This signal is mainly for debug/observability and to prevent useful internal activity from becoming completely invisible at top level.

## Kernel launch sequence

The testbench launches a kernel by writing DCR registers.

```python
dut.dcr_write_en.value = 1

# num_blocks = 1
dut.dcr_addr.value = 0b00
dut.dcr_data.value = 1

# blockDim = 4
dut.dcr_addr.value = 0b01
dut.dcr_data.value = 4

# start pulse
dut.dcr_addr.value = 0b10
dut.dcr_data.value = 0
```

The normal sequence is:

```text
1. Write num_blocks.
2. Write blockDim.
3. Write start command.
4. DCR emits start pulse.
5. Dispatcher assigns blocks to cores.
6. Cores execute.
7. Cores assert block_done.
8. Dispatcher asserts kernel_done.
```

## Reset behavior

Top-level reset is distributed to:

```text
DCR
dispatcher
all core instances
```

Each submodule handles its own internal reset behavior.

The top-level testbench reset helper does:

```python
dut.rst.value = 1
dut.dcr_write_en.value = 0

for _ in range(3):
    await RisingEdge(dut.clk)

dut.rst.value = 0
```

## Testbench memory models

## Program memory model

The program memory model watches each core’s instruction request.

```python
async def program_memory_model(dut, instructions_ref):
    RET_INSTR = 0x48000000

    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        resp_valid = 0

        for i in range(NUM_CORES):
            if safe_bit(dut.prog_mem_req_valid, i) == 0:
                continue

            addr = safe_int(dut.core_gen[i].core_inst.fetch.req_addr, 0)

            dut.prog_mem_resp_data[i].value = instructions_ref[0].get(
                addr,
                RET_INSTR,
            )

            resp_valid |= (1 << i)

        dut.prog_mem_resp_valid.value = resp_valid
```

If an address is missing from the instruction dictionary, the testbench returns:

```text
RET = 0x48000000
```

This prevents undefined program-memory fetches from hanging forever.

## Data memory model

The data memory model watches each core’s internal memory-controller request:

```python
mc = dut.core_gen[core_id].core_inst.mc
```

It then reads:

```text
mc.mem_req_valid
mc.mem_req_addr
mc.mem_req_rw
mc.mem_req_data
```

and drives top-level response signals:

```text
data_mem_resp_valid
data_mem_resp_data
```

The response-data bus is packed, so the model packs all per-core response words into one integer.

## Current cocotb tests

Unit/integration test file:

```text
Src/Top_level_GPU/test_top_level_gpu.py
```

Current tests:

```text
test_gpu_axel_program
test_simt_relu
```

## `test_gpu_axel_program`

This is the larger AXEL program test.

It loads:

```text
phase4_forward.hex
phase5_weight_update.hex
weights.json
```

Configuration:

```text
FORWARD_HEX  = "../../assembler/builds/phase4_forward.hex"
BACKWARD_HEX = "../../assembler/builds/phase5_weight_update.hex"
WEIGHTS_FILE = "../../assembler/builds/weights.json"
N_EPOCHS     = 20
```

Initial Q8 weights:

```text
W = identity matrix
diagonal = 256
```

Input vector:

```text
X = [256, 512, 768, 1024]
```

Target vector:

```text
T = [512, 1024, 1536, 2048]
```

The test repeatedly runs:

```text
forward pass
backward/update pass
```

and saves updated weights into:

```text
assembler/builds/weights.json
```

This test verifies that the top-level GPU can:

```text
load instructions from generated hex files
launch kernels through DCR/dispatcher
execute across cores
perform data memory reads/writes
complete kernels
persist weights
```

## `test_simt_relu`

This is the key SIMT branch-divergence regression test.

Program:

```text
phase6_simt_relu.hex
```

Initial memory:

```text
mem[0] = 5
mem[1] = 0xFFFFFFFD  (-3)
mem[2] = 8
mem[3] = 0xFFFFFFFF  (-1)
```

Expected output:

```text
mem[4] = 5
mem[5] = 0
mem[6] = 8
mem[7] = 0
```

This proves:

```text
LDR loads correct per-thread data
CMP generates correct NZP flags
BR P causes divergence
SYNC reconverges/restores masks
STR writes correct per-thread output
kernel_done eventually asserts
```

This test was the main regression that exposed the old response-data packing bug.

## Inference test

The Makefile includes an inference target:

```makefile
infer:
	rm -f results.xml
	$(MAKE) results.xml COCOTB_TEST_MODULES=inference
```

The inference script is:

```text
Src/Top_level_GPU/inference.py
```

It loads:

```text
phase4_forward.hex
weights.json
```

Then it runs a forward pass using:

```text
X_INPUT = [256, 512, 768, 1024]
```

and prints:

```text
input Q8 values
input real values
output Q8 values
output real values
cycle count
```

The inference test depends on `weights.json` already existing. If it does not exist, it raises an error telling the user to run the training/top-level test first.

## Makefile

Top-level cocotb Makefile:

```makefile
TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(shell pwd)/top_level_gpu.sv \
                  $(shell pwd)/../warp_stack/warp_stack.sv \
                  $(shell pwd)/../memory_controller/mem_controller.sv \
                  $(shell pwd)/../device_control_register/dcr.sv \
                  $(shell pwd)/../dispatcher/dispatcher.sv \
                  $(shell pwd)/../core/core.sv \
                  $(shell pwd)/../scheduler/scheduler.sv \
                  $(shell pwd)/../fetcher/fetcher.sv \
                  $(shell pwd)/../decoder/decoder.sv \
                  $(shell pwd)/../alu/alu.sv \
                  $(shell pwd)/../lsu/lsu.sv \
                  $(shell pwd)/../pc/pc.sv \
                  $(shell pwd)/../registers/register_file.sv

TOPLEVEL = gpu
COCOTB_TEST_MODULES = test_top_level_gpu
SIM = icarus
export PYTHONPATH := $(shell pwd):$(PYTHONPATH)
include $(shell cocotb-config --makefiles)/Makefile.sim

infer:
	rm -f results.xml
	$(MAKE) results.xml COCOTB_TEST_MODULES=inference
```

## Running tests

From the top-level GPU directory:

```bash
cd ~/gpu-project/Src/Top_level_GPU
make
```

Run only the top-level GPU test module:

```bash
make COCOTB_TEST_FILTER='test_gpu_axel_program|test_simt_relu'
```

Run only SIMT ReLU:

```bash
make COCOTB_TEST_FILTER='test_simt_relu$'
```

Run inference:

```bash
make infer
```

From the repository root:

```bash
cd ~/gpu-project
make test
```

## Important fixed bug: packed data-memory response path

A previous failure caused `test_simt_relu` to write zeros:

```text
mem[4] = 0
mem[5] = 0
mem[6] = 0
mem[7] = 0
```

The expected result was:

```text
mem[4] = 5
mem[5] = 0
mem[6] = 8
mem[7] = 0
```

The root problem was in the memory response path:

```text
memory model returned correct data
mem_controller received correct mem_resp_data
LSU saw resp_valid
LSU resp_data stayed zero
```

The final fix aligned packed response-data buses:

```systemverilog
input logic [NUM_CORES-1:0][31:0] data_mem_resp_data
```

at top level, and packed response data inside the memory-controller/core path.

The cocotb memory model must continue driving the top-level packed bus as one full integer.

## Important bus-shape rules

## Program memory response data

`prog_mem_resp_data` is unpacked:

```systemverilog
input logic [31:0] prog_mem_resp_data [NUM_CORES-1:0]
```

Cocotb can drive per-core lanes:

```python
dut.prog_mem_resp_data[i].value = instr
```

## Data memory response data

`data_mem_resp_data` is packed:

```systemverilog
input logic [NUM_CORES-1:0][31:0] data_mem_resp_data
```

Cocotb must drive the full bus:

```python
dut.data_mem_resp_data.value = packed
```

## Block index output

`blockIdx_out` is packed inside the top level:

```systemverilog
logic [NUM_CORES-1:0][31:0] blockIdx_out;
```

Each core receives:

```systemverilog
.blockIdx(blockIdx_out[i])
```

## Timing assumptions

The top-level GPU assumes:

```text
- DCR writes occur synchronously through dcr_write_en/dcr_addr/dcr_data.
- num_blocks and blockDim are written before start.
- start is a one-cycle pulse from DCR.
- dispatcher assigns blocks to cores.
- each core asserts block_done after RET.
- program memory returns instruction data when prog_mem_resp_valid is high.
- data memory returns response data when data_mem_resp_valid is high.
- data_mem_resp_data is valid in the same cycle as data_mem_resp_valid.
```

## Known pitfalls

Do not drive packed `data_mem_resp_data` per index in cocotb.

Drive the whole packed bus as an integer.

Do not change `data_mem_resp_data` back to unpacked without updating:

```text
top_level_gpu.sv
test_top_level_gpu.py
inference.py
core/memory response wiring
```

Do not assume `prog_mem_resp_data` and `data_mem_resp_data` have the same shape.

Currently:

```text
prog_mem_resp_data -> unpacked
data_mem_resp_data -> packed
```

Do not launch a kernel before writing DCR configuration.

The expected order is:

```text
num_blocks
blockDim
start
```

Do not assume `kernel_done` automatically clears for a new launch.

The dispatcher currently clears `kernel_done` on reset. Repeated launches should reset first unless dispatcher behavior is changed.

Do not remove the fallback RET instruction in the program memory model.

It prevents invalid instruction fetches from becoming uncontrolled/hanging behavior during tests.

Do not debug SIMT branch logic before confirming the memory read path.

If `LDR` data is wrong, CMP/BR behavior becomes misleading.

## Verification coverage

| Test                    | File                                           | What it proves                                                                       |
| ----------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------ |
| `test_gpu_axel_program` | `test_top_level_gpu.py`                        | Full top-level AXEL program flow, forward/update kernels, memory model, DCR dispatch |
| `test_simt_relu`        | `test_top_level_gpu.py`                        | LDR, CMP, divergence, SYNC, STR, packed response-data path                           |
| `test_gpu_inference`    | `inference.py`                                 | Forward-only inference using saved weights                                           |
| `test_dispatcher_*`     | `Src/dispatcher/test_dispatcher.py`            | Block assignment and `kernel_done` behavior                                          |
| `test_core_basic`       | `Src/core/test_core.py`                        | Core can fetch/execute/RET                                                           |
| `test_mem_controller_*` | `Src/memory_controller/test_mem_controller.py` | Per-thread memory response routing                                                   |

## Recommended additional tests

| Test                                           | Purpose                                                           |
| ---------------------------------------------- | ----------------------------------------------------------------- |
| `test_two_blocks_single_core_reuse`            | Verify block reuse after a core finishes                          |
| `test_multiple_cores_memory_reads`             | Verify packed data responses across multiple cores simultaneously |
| `test_program_memory_missing_addr_returns_ret` | Verify fallback RET behavior                                      |
| `test_kernel_done_timeout`                     | Verify testbench catches hung kernels                             |
| `test_new_launch_requires_reset_or_clear`      | Define repeated-kernel behavior                                   |
| `test_data_mem_write_all_cores`                | Verify writes from all cores to data memory                       |
| `test_data_mem_read_all_cores`                 | Verify reads into all cores                                       |
| `test_thread_keep_alive_changes`               | Verify top-level keep-alive output observes core activity         |
| `test_blockDim_1_fpga_mode`                    | Verify single-thread/blockIdx-as-threadIdx behavior               |
| `test_num_blocks_gt_num_cores`                 | Verify top-level dispatch across multiple waves                   |

## Last known status

```text
Status: passing

Verified with:
  cd ~/gpu-project
  make test

Important fixed bug:
  Packed response-data path aligned for data_mem_resp_data / mem_controller / LSU readback.

Key regression:
  test_simt_relu passes with:
    mem[4] = 5
    mem[5] = 0
    mem[6] = 8
    mem[7] = 0
```

## Design summary

`gpu` is the top-level integration module for the Tiny GPU. It accepts host/testbench DCR writes, launches kernels through the dispatcher, instantiates multiple cores, connects per-core program and data memory interfaces, and reports `kernel_done`.

The most important implementation details are:

```text
DCR start launches dispatcher
dispatcher assigns blockIdx_out to cores
core_gen creates NUM_CORES core instances
prog_mem_resp_data is unpacked
data_mem_resp_data is packed
thread_keep_alive is XOR-reduced across cores
```

The most important verification rule is:

```text
keep the packed data memory response handling exactly aligned between RTL and cocotb
```
