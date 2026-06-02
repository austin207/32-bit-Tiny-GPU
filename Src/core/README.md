# Core

## Overview

`core` is the main SIMT execution block of the Tiny GPU.

A core receives a block assignment from the dispatcher, fetches instructions from program memory, decodes them, schedules pipeline stages, executes instructions across multiple per-thread lanes, handles memory operations through the LSU/memory-controller path, supports branch divergence/reconvergence, and reports when the assigned block is complete.

Each core contains:

```text
fetcher
decoder
scheduler
warp_stack
THREADS_PER_CORE × { ALU, LSU, register file, PC }
memory_controller
thread_keep_alive reduction logic
```

## RTL schematic

![Core RTL schematic](../../assets/Images-Components/Core-page-00001.jpg)

## Source files

```text
Src/core/core.sv
Src/core/test_core.py
Src/core/Makefile
```

Related modules:

```text
Src/fetcher/fetcher.sv
Src/decoder/decoder.sv
Src/scheduler/scheduler.sv
Src/warp_stack/warp_stack.sv
Src/alu/alu.sv
Src/lsu/lsu.sv
Src/pc/pc.sv
Src/registers/register_file.sv
Src/memory_controller/mem_controller.sv
```

## Position in the GPU

The core sits between the top-level GPU/dispatcher and the internal execution datapath.

```text
dispatcher
    │
    │ core_start, blockIdx, blockDim
    ▼
core
    │
    ├── program memory request interface
    │
    ├── data memory request interface
    │
    ├── thread_keep_alive
    │
    └── block_done
```

Inside the full top-level:

```text
DCR
 │
 ▼
dispatcher
 │
 ▼
core_gen[i].core_inst
 │
 ├── fetcher -> program memory
 ├── per-thread ALU/register/PC/LSU datapath
 ├── memory_controller -> data memory
 └── block_done -> dispatcher
```

## Module declaration

```systemverilog
module core #(
    parameter THREADS_PER_CORE = 4
) (
    input  logic clk,
    input  logic rst,
    input  logic core_start,
    input  logic [31:0] blockIdx,
    input  logic [31:0] blockDim,

    output logic block_done,
    output logic [31:0] thread_keep_alive,

    output logic        prog_mem_req_valid,
    output logic [31:0] prog_mem_req_addr,
    input  logic        prog_mem_resp_valid,
    input  logic [31:0] prog_mem_resp_data,

    output logic        data_mem_req_valid,
    output logic [31:0] data_mem_req_addr,
    output logic        data_mem_req_rw,
    output logic [31:0] data_mem_req_data,
    input  logic        data_mem_resp_valid,
    input  logic [31:0] data_mem_resp_data
);
```

## Parameter

| Parameter          | Default | Description                                 |
| ------------------ | ------: | ------------------------------------------- |
| `THREADS_PER_CORE` |     `4` | Number of SIMT thread lanes inside one core |

## Port description

| Port                  | Direction | Width | Description                                                        |
| --------------------- | --------- | ----: | ------------------------------------------------------------------ |
| `clk`                 | input     |     1 | Clock                                                              |
| `rst`                 | input     |     1 | Reset                                                              |
| `core_start`          | input     |     1 | Start pulse from dispatcher                                        |
| `blockIdx`            | input     |    32 | Block index assigned to this core                                  |
| `blockDim`            | input     |    32 | Number of threads per block                                        |
| `block_done`          | output    |     1 | Pulsed when this core completes its assigned block                 |
| `thread_keep_alive`   | output    |    32 | XOR-reduced observable/debug output from per-thread writeback data |
| `prog_mem_req_valid`  | output    |     1 | Program memory request-valid                                       |
| `prog_mem_req_addr`   | output    |    32 | Program memory request address / PC                                |
| `prog_mem_resp_valid` | input     |     1 | Program memory response-valid                                      |
| `prog_mem_resp_data`  | input     |    32 | Program memory instruction data                                    |
| `data_mem_req_valid`  | output    |     1 | Data memory request-valid                                          |
| `data_mem_req_addr`   | output    |    32 | Data memory address                                                |
| `data_mem_req_rw`     | output    |     1 | Data memory read/write select. `1 = read`, `0 = write`             |
| `data_mem_req_data`   | output    |    32 | Data memory write data                                             |
| `data_mem_resp_valid` | input     |     1 | Data memory response-valid                                         |
| `data_mem_resp_data`  | input     |    32 | Data memory response data                                          |

## Main datapath

At a high level, each instruction flows through this path:

```text
PC
 │
 ▼
fetcher
 │
 ▼
instruction latch
 │
 ▼
decoder
 │
 ▼
scheduler-controlled execution
 │
 ├── ALU path
 ├── LSU/memory path
 ├── register writeback path
 └── PC update / branch path
```

The scheduler controls when each phase is active:

```text
FETCH
DECODE
REQUEST
WAIT
EXECUTE
UPDATE
DIVERGE
SYNC_POP
```

## Internal module instances

## Fetcher

The fetcher requests the instruction at the currently active PC:

```systemverilog
fetcher fetch (
    .clk         (clk),
    .rst         (rst),
    .core_en     (fetcher_en),
    .pc_value    (active_pc),
    .instruction (instruction_raw),
    .done        (done),
    .req_valid   (prog_mem_req_valid),
    .req_addr    (prog_mem_req_addr),
    .resp_valid  (prog_mem_resp_valid),
    .resp_data   (prog_mem_resp_data)
);
```

The fetcher output is not decoded directly. It is first latched into `instruction`.

## Instruction latch

The core has an instruction latch:

```systemverilog
logic [31:0] instruction_raw;
logic [31:0] instruction;

always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        instruction <= 32'b0;
    end else if (done) begin
        instruction <= instruction_raw;
    end
end
```

This is important because the fetched instruction must stay stable across the full scheduler sequence:

```text
DECODE -> REQUEST -> WAIT -> EXECUTE -> UPDATE
```

Without this latch, decoder control signals can change before memory/writeback completes.

## Decoder

The decoder receives the latched instruction:

```systemverilog
decoder dec (
    .instruction   (instruction),
    .opcode        (opcode),
    .rd_addr       (rd_addr),
    .rs1_addr      (rs1_addr),
    .rs2_addr      (rs2_addr),
    .rs3_addr      (rs3_addr),
    .imm           (imm),
    .nzp_mask      (nzp_mask),
    .sync_offset   (sync_offset),
    .branch_offset (branch_offset),
    .sync_en       (sync_en),

    .ret           (ret),
    .write_back_en (write_back_en_dec),
    .mem_read_en   (mem_read_en),
    .mem_write_en  (mem_write_en),
    .branch_en     (branch_en),
    .nzp_en        (nzp_en)
);
```

The decoder provides both field extraction and instruction-control signals.

## Scheduler

The scheduler is the central control FSM for the core.

```systemverilog
scheduler #(
    .THREADS_PER_CORE(THREADS_PER_CORE)
) shed (
    .clk                 (clk),
    .rst                 (rst),
    .core_start          (core_start),
    .fetcher_done        (done),
    .lsu_done            (lsu_done),
    .mem_read_en         (mem_read_en),
    .mem_write_en        (mem_write_en),
    .ret                 (ret),
    .divergence_detected (divergence_detected),
    .taken_mask          (taken_mask),
    .sync_en             (sync_en),
    .saved_mask          (ws_stack_empty ? {THREADS_PER_CORE{1'b1}} : ws_top_saved_mask),

    .fetcher_en          (fetcher_en),
    .lsu_en              (lsu_en),
    .execute_en          (execute_en),
    .write_back_en       (write_back_en_sched),
    .current_state       (current_state),
    .active_mask         (active_mask),
    .block_done          (block_done),
    .pc_en               (pc_en)
);
```

The scheduler emits:

```text
fetcher_en
lsu_en
execute_en
write_back_en_sched
pc_en
active_mask
block_done
current_state
```

## Per-thread generate block

The core creates one thread lane per `THREADS_PER_CORE`.

```systemverilog
generate
    for (i = 0; i < THREADS_PER_CORE; i++) begin : thread_gen
        ...
    end
endgenerate
```

Each thread lane contains:

```text
ALU
LSU
register file
PC
```

This means the core executes the same decoded instruction across multiple thread lanes, controlled by `active_mask`.

## Per-thread ALU

Each thread has its own ALU:

```systemverilog
alu alu_inst (
    .operand1  (reg_data1[i]),
    .operand2  (reg_data2[i]),
    .operand3  (reg_data3[i]),
    .op_select (opcode),
    .result    (alu_result[i]),
    .nzp_flag  (nzp_result[i])
);
```

The ALU output goes to:

```text
write_data[i] for ALU writeback
nzp_result[i] for CMP/branch flag update
```

## Per-thread LSU

Each thread has its own LSU:

```systemverilog
lsu lsu_inst (
    .clk               (clk),
    .rst               (rst),
    .core_en           (lsu_en & active_mask[i]),
    .done              (lsu_done_raw[i]),
    .mem_data_address  (mem_addr[i]),

    .req_valid         (lsu_req_valid[i]),
    .req_addr          (lsu_req_addr[i]),
    .write_data        (lsu_req_data[i]),
    .resp_valid        (lsu_resp_valid[i]),
    .resp_data         (lsu_resp_data[i]),

    .mem_write_en      (mem_write_en),
    .mem_write_data    (reg_data3[i]),
    .mem_read_en       (mem_read_en),
    .mem_read_data     (lsu_read_data[i]),

    .read_write_switch (lsu_req_rw[i])
);
```

The LSU handles load/store request generation for one thread lane.

## Register file

Each thread has its own register file:

```systemverilog
registers reg_file (
    .clk       (clk),
    .rst       (rst),
    .r_addr1   (rs1_addr),
    .r_addr2   (rs2_addr),
    .r_addr3   (mem_write_en ? rd_addr : rs3_addr),
    .w_addr    (rd_addr),
    .w_data    (write_data[i]),
    .w_en      (write_back_en_sched & write_back_en_dec & active_mask[i]),

    .threadIdx (32'(i)),
    .blockIdx  (blockIdx),
    .blockDim  (blockDim),
    .r_data1   (reg_data1[i]),
    .r_data2   (reg_data2[i]),
    .r_data3   (reg_data3[i])
);
```

The write-enable condition is important:

```systemverilog
write_back_en_sched & write_back_en_dec & active_mask[i]
```

This prevents non-writeback instructions such as `BR`, `SYNC`, `STR`, and `RET` from accidentally writing registers during scheduler `UPDATE`.

## Per-thread PC

Each thread has its own PC:

```systemverilog
pc pc_inst (
    .clk           (clk),
    .rst           (rst),
    .block_rst     (pc_block_rst),
    .pc_en         (pc_en & active_mask[i]),
    .branch_en     (branch_en),
    .branch_offset (branch_offset),
    .nzp_en        (nzp_en),
    .nzp_flag      (nzp_result[i]),
    .nzp_mask      (nzp_mask),
    .pc_out        (pc_out[i]),
    .nzp_out       (nzp_stored[i])
);
```

The PC stores each thread’s NZP flag and applies branch offsets when branch conditions are met.

## Memory controller

The core contains one memory controller shared by all thread LSUs:

```systemverilog
mem_controller #(
    .THREADS_PER_CORE(THREADS_PER_CORE)
) mc (
    .clk            (clk),
    .rst            (rst),

    .req_valid      (lsu_req_valid),
    .req_addr       (lsu_req_addr),
    .req_rw         (lsu_req_rw),
    .req_data       (lsu_req_data),
    .resp_valid     (lsu_resp_valid),
    .resp_data      (lsu_resp_data),

    .mem_req_valid  (data_mem_req_valid),
    .mem_req_addr   (data_mem_req_addr),
    .mem_req_rw     (data_mem_req_rw),
    .mem_req_data   (data_mem_req_data),
    .mem_resp_valid (data_mem_resp_valid),
    .mem_resp_data  (data_mem_resp_data)
);
```

The controller serializes requests from all thread LSUs into one data-memory interface.

## Packed LSU response bus

The core uses a packed response bus between `mem_controller` and the thread LSUs:

```systemverilog
logic [THREADS_PER_CORE-1:0]        lsu_resp_valid;
logic [THREADS_PER_CORE-1:0][31:0]  lsu_resp_data;
```

This must match the memory controller port:

```systemverilog
output logic [THREADS_PER_CORE-1:0][31:0] resp_data
```

Do not change this back to an unpacked array.

The previous packed/unpacked mismatch caused:

```text
mc_resp_data=5
mc_out_data0=5
lsu0_resp_v=1
lsu0_resp_data=0
lsu0_read_data=0
```

That broke `LDR` writeback and made `R1` stay zero even though data memory returned the correct value.

## LSU done latch

The core accumulates per-thread LSU completion:

```systemverilog
always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        lsu_done_latch <= '0;
    end else begin
        if (lsu_en) begin
            lsu_done_latch <= '0;
        end else begin
            for (int i = 0; i < THREADS_PER_CORE; i++) begin
                if (lsu_done_raw[i]) begin
                    lsu_done_latch[i] <= 1'b1;
                end
            end
        end
    end
end
```

The scheduler sees:

```systemverilog
assign lsu_done = lsu_done_latch | ~active_mask;
```

Inactive threads are treated as already done.

This is needed because the memory controller serializes thread memory requests, so each thread may complete at a different cycle.

## Memory address generation

Each thread computes memory addresses as:

```systemverilog
assign mem_addr[i] = reg_data1[i] + {{16{imm[15]}}, imm};
```

This uses:

```text
base register = reg_data1[i]
offset        = sign-extended 16-bit immediate
```

For `LDR` and `STR`, this forms the effective memory address.

## Writeback data mux

Each thread selects writeback data using:

```systemverilog
assign write_data[i] =
    mem_read_en        ? lsu_read_data[i] :
    (opcode == 6'h11)  ? {16'b0, imm}     :
                          alu_result[i];
```

Meaning:

| Case                | Writeback source        |
| ------------------- | ----------------------- |
| Load instruction    | `lsu_read_data[i]`      |
| `CONST` instruction | Zero-extended immediate |
| ALU instruction     | `alu_result[i]`         |

Writeback is only committed when:

```systemverilog
write_back_en_sched & write_back_en_dec & active_mask[i]
```

## Active mask

`active_mask` controls which thread lanes participate in the current instruction.

If `active_mask[i] = 1`, thread `i` is active.

If `active_mask[i] = 0`, thread `i` is inactive and should not:

```text
execute LSU request
write back register data
advance PC
```

The core gates major per-thread actions with `active_mask[i]`:

```systemverilog
.core_en(lsu_en & active_mask[i])
.w_en(write_back_en_sched & write_back_en_dec & active_mask[i])
.pc_en(pc_en & active_mask[i])
```

## Active PC selection

The fetcher receives one `active_pc`:

```systemverilog
logic [31:0] active_pc;
```

It is selected from the currently active thread lanes:

```systemverilog
always_comb begin
    active_pc = pc_out[0];

    for (int i = THREADS_PER_CORE - 1; i >= 0; i--) begin
        if (active_mask[i]) begin
            active_pc = pc_out[i];
        end
    end
end
```

This assumes active threads in a warp are normally executing the same PC except during divergence/reconvergence handling.

## Branch and divergence detection

For a branch instruction, each thread decides whether it takes the branch based on its stored NZP flag:

```systemverilog
taken_mask[i] =
    branch_en &&
    active_mask[i] &&
    ((nzp_stored[i] & nzp_mask) != 3'b000);
```

Divergence is detected when:

```systemverilog
divergence_detected =
    branch_en &&
    (taken_mask != active_mask) &&
    (taken_mask != '0);
```

This means divergence occurs when:

```text
some active threads take the branch
some active threads do not take the branch
```

If no thread takes the branch, there is no divergence.

If all active threads take the branch, there is no divergence.

If only a subset takes the branch, the core enters the divergence path.

## Warp stack

The core uses `warp_stack` to store reconvergence information.

```systemverilog
warp_stack #(
    .THREADS_PER_CORE(THREADS_PER_CORE)
) ws (
    .clk             (clk),
    .rst             (rst),
    .push            (ws_push),
    .push_sync_pc    (sync_pc),
    .push_saved_mask (~taken_mask & active_mask),
    .pop             (ws_pop),
    .top_sync_pc     (ws_top_sync_pc),
    .top_saved_mask  (ws_top_saved_mask),
    .stack_empty     (ws_stack_empty),
    .stack_full      (ws_stack_full),
    .stack_overflow  (ws_stack_overflow)
);
```

Current push/pop controls:

```systemverilog
assign ws_push = (current_state == 4'b0111);
assign ws_pop  = (current_state == 4'b1000);
```

Where:

```text
4'b0111 = DIVERGE
4'b1000 = SYNC_POP
```

## Reconvergence / SYNC behavior

The branch instruction carries a `sync_offset`.

The core computes:

```systemverilog
assign sync_pc = active_pc + {21'b0, sync_offset};
```

On divergence:

```text
taken threads continue first
not-taken active threads are saved in the warp stack
sync_pc is saved as the reconvergence point
```

At `SYNC`, the scheduler enters `SYNC_POP`, restores the saved mask, and continues execution with the previously inactive path.

The saved mask passed to the scheduler is:

```systemverilog
.saved_mask(ws_stack_empty ? {THREADS_PER_CORE{1'b1}} : ws_top_saved_mask)
```

If the stack is empty, all threads become active.

## SIMT ReLU example

The SIMT ReLU program uses divergence:

```text
PC0: LDR   R1, THREAD_IDX, 0
PC1: CMP   R1, R0
PC2: BR P, sync_offset=2, branch_offset=2
PC3: CONST R1, 0
PC4: SYNC
PC5: STR   R1, THREAD_IDX, 4
PC6: RET
```

Input memory:

```text
mem[0] = 5
mem[1] = -3
mem[2] = 8
mem[3] = -1
```

Expected behavior:

```text
T0: positive -> branch taken -> keep 5
T1: negative -> not taken -> zero
T2: positive -> branch taken -> keep 8
T3: negative -> not taken -> zero
```

Expected output:

```text
mem[4] = 5
mem[5] = 0
mem[6] = 8
mem[7] = 0
```

This test proves:

```text
LDR read data reaches R1
CMP produces correct NZP flags
BR detects divergence
SYNC reconverges
STR writes the correct values
```

## `thread_keep_alive`

The core exposes a 32-bit debug/keep-alive signal:

```systemverilog
assign thread_keep_alive = _keep_xor[THREADS_PER_CORE];
```

It is the XOR reduction of all per-thread `write_data[i]` values:

```systemverilog
assign _keep_xor[0] = 32'b0;

generate
    for (k = 0; k < THREADS_PER_CORE; k++) begin : keep_xor_gen
        assign _keep_xor[k + 1] = _keep_xor[k] ^ write_data[k];
    end
endgenerate
```

This is mainly useful as an observable signal so synthesis/simulation does not completely hide internal activity.

## Reset behavior

On reset:

```text
instruction        -> 0
lsu_done_latch     -> 0
scheduler state    -> reset inside scheduler
PCs                -> reset inside pc modules
register files     -> reset inside register modules
LSUs               -> reset inside lsu modules
memory controller  -> reset inside mem_controller
warp stack         -> reset inside warp_stack
```

The core-level instruction latch and LSU done latch are explicitly reset in `core.sv`.

## Important fixed bugs

## 1. Instruction latch bug

Problem:

```text
Fetcher output could change before DECODE/REQUEST/WAIT/EXECUTE/UPDATE completed.
```

Fix:

```systemverilog
always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        instruction <= 32'b0;
    end else if (done) begin
        instruction <= instruction_raw;
    end
end
```

Decoder now uses the latched instruction.

## 2. Register writeback gating bug

Problem:

```text
Scheduler writeback enable alone was not enough.
Non-writeback instructions could accidentally write registers during UPDATE.
```

Fix:

```systemverilog
.w_en(write_back_en_sched & write_back_en_dec & active_mask[i])
```

Now both scheduler timing and decoder instruction type must agree.

## 3. Packed LSU response-data bug

Problem:

```text
mem_controller.resp_data was unpacked
core.lsu_resp_data was packed
LSU received resp_valid but resp_data stayed zero
```

Fix:

```systemverilog
logic [THREADS_PER_CORE-1:0][31:0] lsu_resp_data;
```

matched with `mem_controller`:

```systemverilog
output logic [THREADS_PER_CORE-1:0][31:0] resp_data
```

This fixed LDR writeback.

## Timing assumptions

The core assumes:

```text
- `core_start` pulses when dispatcher assigns a block.
- Program memory returns valid instruction data when `prog_mem_resp_valid` is asserted.
- Data memory returns valid read data when `data_mem_resp_valid` is asserted.
- LSU request-valid pulses are captured by `mem_controller`.
- Only active threads issue LSU requests, write registers, or advance PC.
- The decoder output remains stable because the fetched instruction is latched.
- The scheduler controls the legal timing for fetch, memory request, execute, update, divergence, and sync-pop.
```

## Unit test

Unit test file:

```text
Src/core/test_core.py
```

The current core unit test:

```text
test_core_basic
```

Program:

```text
PC0: ADD R1, R2, R3
PC1: RET
```

The test checks that the core can:

```text
reset
fetch an instruction
execute a basic instruction
fetch RET
assert block_done
```

## Core unit-test Makefile

```makefile
TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(shell pwd)/core.sv \
                  $(shell pwd)/../warp_stack/warp_stack.sv \
                  $(shell pwd)/../memory_controller/mem_controller.sv \
                  $(shell pwd)/../scheduler/scheduler.sv \
                  $(shell pwd)/../fetcher/fetcher.sv \
                  $(shell pwd)/../decoder/decoder.sv \
                  $(shell pwd)/../alu/alu.sv \
                  $(shell pwd)/../lsu/lsu.sv \
                  $(shell pwd)/../pc/pc.sv \
                  $(shell pwd)/../registers/register_file.sv

TOPLEVEL = core
COCOTB_TEST_MODULES = test_core
SIM = icarus
export PYTHONPATH := $(shell pwd):$(PYTHONPATH)
include $(shell cocotb-config --makefiles)/Makefile.sim
```

## Verification coverage

| Test                    | File                                      | What it checks                                   |
| ----------------------- | ----------------------------------------- | ------------------------------------------------ |
| `test_core_basic`       | `Src/core/test_core.py`                   | Basic fetch/execute/RET/block_done flow          |
| `test_simt_relu`        | `Src/Top_level_GPU/test_top_level_gpu.py` | LDR writeback, CMP, branch divergence, SYNC, STR |
| `test_gpu_axel_program` | `Src/Top_level_GPU/test_top_level_gpu.py` | Full AXEL top-level program flow                 |

## Recommended additional tests

The current core unit test is minimal. Add more core-level tests later:

| Test                              | Purpose                                                |
| --------------------------------- | ------------------------------------------------------ |
| `test_core_const_writeback`       | Verify `CONST` writes immediate into the register file |
| `test_core_ldr_writeback`         | Verify `LDR` read data reaches destination register    |
| `test_core_str`                   | Verify store data/address path                         |
| `test_core_branch_taken`          | Verify uniform branch taken                            |
| `test_core_branch_not_taken`      | Verify uniform branch not taken                        |
| `test_core_divergence`            | Verify active-mask split and warp-stack push           |
| `test_core_sync_pop`              | Verify saved mask restoration                          |
| `test_core_multi_thread_memory`   | Verify serialized memory responses across all threads  |
| `test_core_ret_block_done`        | Verify `RET` asserts `block_done` cleanly              |
| `test_core_active_mask_writeback` | Verify inactive threads do not write registers         |

## Known pitfalls

Do not remove the instruction latch.

Do not write registers using only `write_back_en_sched`.

Do not change `lsu_resp_data` to unpacked unless `mem_controller.resp_data` and tests are also changed.

Do not debug branch divergence before proving `LDR` writeback works.

Do not assume inactive threads are naturally harmless. LSU, PC, and register writeback must be gated by `active_mask`.

Do not assume the core unit test fully validates SIMT behavior. Most SIMT coverage currently comes from the top-level `test_simt_relu`.

## Last known status

```text
Status: passing

Verified with:
  cd ~/gpu-project
  make test

Important fixed bugs:
  instruction latch added
  register writeback gated with decoder write-enable
  packed LSU response-data path aligned with memory_controller
```

## Design summary

`core` is the main SIMT execution engine. It fetches and decodes one instruction stream, executes that instruction across multiple thread lanes, handles per-thread register files/PCs/ALUs/LSUs, serializes memory requests through `mem_controller`, and supports branch divergence through `active_mask`, `taken_mask`, and `warp_stack`.

The most important implementation details are:

```text
- fetched instructions are latched before decode
- register writeback requires both scheduler and decoder write-enable
- inactive threads are masked from LSU, PC, and register writeback
- LSU response data uses packed 2D buses
- divergence is detected from per-thread NZP branch decisions
```
