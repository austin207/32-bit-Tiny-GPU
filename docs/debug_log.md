# Tiny GPU Debug Log

## Overview

This document records the important debugging history, resolved issues, and design decisions for the Tiny GPU project.

It is meant to help future debugging by explaining:

```text
what failed
why it failed
how it was diagnosed
which files were changed
what the final fix was
what tests now prove the fix
```

## Current status

```text
Status: passing

Verified command:
  cd ~/gpu-project
  make test
```

Current passing areas:

```text
ALU
registers
PC
decoder
fetcher
LSU
memory_controller
scheduler
warp_stack
core
dispatcher
DCR
Top_level_GPU
```

Key top-level regression:

```text
test_simt_relu passes

Expected:
  mem[4] = 5
  mem[5] = 0
  mem[6] = 8
  mem[7] = 0
```

## Most important fixed issue

The biggest recent bug was in the memory response-data path.

Symptom:

```text
SIMT ReLU kernel completed, but output memory was wrong.

Expected:
  mem[4] = 5
  mem[5] = 0
  mem[6] = 8
  mem[7] = 0

Actual:
  mem[4] = 0
  mem[5] = 0
  mem[6] = 0
  mem[7] = 0
```

This meant the kernel was running to completion, but the loaded values were not reaching the thread registers correctly.

## Debug trace from failure

The important internal observation was:

```text
memory model had correct data
memory controller received correct response data
memory controller output lane had correct data
LSU response valid was high
LSU response data was still zero
LSU read data became zero
register writeback wrote zero
```

Representative signal meaning:

```text
mc_resp_data      = 5
mc_out_data0      = 5
lsu0_resp_v       = 1
lsu0_resp_data    = 0
lsu0_read_data    = 0
```

This proved the problem was not the external memory model and not the ALU/CMP/branch path.

The data was being lost between memory-controller output and LSU input.

## Root cause: packed/unpacked response-data mismatch

The root cause was a SystemVerilog bus-shape mismatch.

The core used one shape for LSU response data, while the memory controller exposed another shape.

Bad pattern:

```text
mem_controller response data and core lsu_resp_data did not have matching packed layout.
```

This caused cocotb/RTL hierarchy to show valid memory-controller data, but the LSU lane saw zero.

## Final fix: align packed response buses

The memory-controller response-data output was changed to packed 2D:

```systemverilog
output logic [THREADS_PER_CORE-1:0][31:0] resp_data
```

The core-side LSU response bus was aligned to the same shape:

```systemverilog
logic [THREADS_PER_CORE-1:0][31:0] lsu_resp_data;
```

The top-level data memory response bus was also kept packed:

```systemverilog
input logic [NUM_CORES-1:0][31:0] data_mem_resp_data
```

The cocotb data memory model was updated to drive the packed bus as one integer:

```python
packed = 0

for c in range(NUM_CORES):
    packed |= (resp_data_per_core[c] & 0xFFFFFFFF) << (c * 32)

dut.data_mem_resp_data.value = packed
```

## Files affected by packed response-data fix

Primary files:

```text
Src/memory_controller/mem_controller.sv
Src/memory_controller/test_mem_controller.py
Src/core/core.sv
Src/Top_level_GPU/top_level_gpu.sv
Src/Top_level_GPU/test_top_level_gpu.py
```

Also check:

```text
Src/Top_level_GPU/inference.py
```

because it must use the same packed top-level data-memory response convention.

## Verification after packed bus fix

After the packed response-data fix:

```text
test_simt_relu passed
memory controller tests passed
top-level tests passed
make test passed
```

Expected SIMT ReLU output:

```text
mem[4] = 5
mem[5] = 0
mem[6] = 8
mem[7] = 0
```

## Memory controller update

The memory controller is now a per-core request arbiter across thread LSU lanes.

Important current behavior:

```text
LSU req_valid is a one-cycle pulse.
The controller buffers pulses using pending bits.
The controller captures addr/rw/data with each request.
The controller serves requests one at a time.
The controller uses round-robin selection.
The controller returns resp_valid and resp_data to the correct thread lane.
```

Key fix:

```text
One-cycle LSU request pulses can arrive while the controller is busy.
Without a pending buffer, those pulses can be lost.
```

The controller now has:

```systemverilog
logic [THREADS_PER_CORE-1:0] pending;
logic [31:0]                 pending_addr [THREADS_PER_CORE-1:0];
logic [THREADS_PER_CORE-1:0] pending_rw;
logic [31:0]                 pending_data [THREADS_PER_CORE-1:0];
```

This stores request payload until the controller can serve the lane.

## Memory controller tests updated

The memory controller testbench was updated because `resp_data` is packed.

Cocotb helper:

```python
THREADS_PER_CORE = 4
WORD_W = 32

def resp_word(dut, thread_id):
    packed = int(dut.resp_data.value)
    return (packed >> (thread_id * WORD_W)) & 0xFFFFFFFF
```

This avoids incorrectly indexing packed HDL objects from cocotb.

## Instruction stability bug

Earlier design risk:

```text
Decoder could observe changing fetcher instruction output while a multicycle instruction was still executing.
```

This is dangerous for memory instructions:

```text
DECODE -> REQUEST -> WAIT -> EXECUTE -> UPDATE
```

If instruction bits change during WAIT, decoder control signals can become unstable.

## Instruction latch fix

The core now latches the fetched instruction when the fetcher reports done.

Core pattern:

```systemverilog
always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        instruction <= 32'b0;
    end else if (done) begin
        instruction <= instruction_raw;
    end
end
```

The decoder uses the stable latched instruction.

This protects:

```text
opcode
rd_addr
rs1_addr
rs2_addr
rs3_addr
imm
branch fields
decoder control signals
```

## Files affected by instruction latch

Primary file:

```text
Src/core/core.sv
```

Related modules relying on stability:

```text
Src/decoder/decoder.sv
Src/scheduler/scheduler.sv
Src/lsu/lsu.sv
Src/registers/register_file.sv
```

## Writeback gating fix

Important rule:

```text
scheduler write_back_en alone must not write registers.
```

The scheduler pulses `write_back_en` during UPDATE for instruction timing.

But not every instruction writes a register.

Examples that must not write registers:

```text
CMP
BRnzp
STR
SYNC
RET
NOP
```

The correct core write enable is:

```systemverilog
write_back_en_sched & write_back_en_dec & active_mask[i]
```

This means a register write happens only when:

```text
scheduler is in writeback/update timing
decoder says the instruction writes a register
thread lane is active
```

## Files affected by writeback gating

Primary file:

```text
Src/core/core.sv
```

Related files:

```text
Src/scheduler/scheduler.sv
Src/decoder/decoder.sv
Src/registers/register_file.sv
```

## Active-mask gating fix

In SIMT mode, inactive lanes must not update architectural state.

Inactive lanes must not:

```text
issue LSU requests
write registers
advance PC
```

Correct gating rules:

```text
LSU core_en  = lsu_en & active_mask[i]
register w_en = write_back_en_sched & write_back_en_dec & active_mask[i]
PC enable = pc_en & active_mask[i]
```

This allows the taken group and not-taken group to execute separately during branch divergence.

## Files affected by active-mask gating

Primary file:

```text
Src/core/core.sv
```

Related files:

```text
Src/scheduler/scheduler.sv
Src/pc/pc.sv
Src/lsu/lsu.sv
Src/registers/register_file.sv
```

## LSU inactive-lane done handling

The scheduler waits for all LSU done bits:

```systemverilog
all_done = &lsu_done;
```

Problem:

```text
Inactive lanes do not issue LSU requests, so they will not naturally pulse done.
```

Fix inside core:

```text
inactive lanes are treated as already done
```

Conceptual logic:

```systemverilog
lsu_done = lsu_done_latch | ~active_mask;
```

This prevents memory instructions from hanging during divergent execution.

## Branch divergence bug class

For SIMT branch divergence, branch decisions must use stored NZP flags, not raw ALU output.

Reason:

```text
BRnzp is not an ALU operation.
The ALU output for BRnzp is not the previous CMP result.
```

Correct branch decision uses each thread’s stored NZP register:

```text
taken_mask[i] =
    branch_en &&
    active_mask[i] &&
    ((nzp_stored[i] & nzp_mask) != 0)
```

## PC/NZP fix

The PC module stores NZP flags after CMP.

It exposes:

```text
nzp_out
```

so core divergence logic can read each thread’s stored condition flag.

Important behavior:

```text
CMP updates stored NZP.
BRnzp uses stored NZP.
```

Not raw ALU result.

## Files affected by branch/NZP path

Primary files:

```text
Src/pc/pc.sv
Src/core/core.sv
Src/alu/alu.sv
Src/decoder/decoder.sv
```

## Warp stack addition

The warp stack was added for SIMT divergence/reconvergence.

It stores:

```text
sync_pc
saved_mask
```

Current stack entry:

```text
{sync_pc[31:0], saved_mask[3:0]}
```

On divergence:

```text
taken_mask becomes active
not-taken mask is pushed to stack
sync_pc is pushed to stack
```

On SYNC:

```text
saved mask is restored
```

## Files related to warp stack

```text
Src/warp_stack/warp_stack.sv
Src/warp_stack/test_warp_stack.py
Src/core/core.sv
Src/scheduler/scheduler.sv
Src/Top_level_GPU/test_top_level_gpu.py
```

Architecture image note:

```text
assets/Architecture-images/gpu_architecture.png should be updated later to show warp_stack inside each core.
```

## SYNC instruction addition

SYNC was added as a compiler/assembler-visible reconvergence marker.

Opcode:

```text
0x15
```

Encoded instruction:

```text
0x54000000
```

Decoder behavior:

```text
sync_en = 1
```

Scheduler behavior:

```text
UPDATE -> SYNC_POP
active_mask <= saved_mask
```

Assembler API:

```c
axel_sync(&gpu);
```

## BRnzp encoding update

BRnzp now carries two offsets:

```text
sync_offset
branch_offset
```

B-type field split:

```text
[25:23] = nzp_mask
[22:12] = sync_offset
[11:0]  = branch_offset
```

Assembler encoder:

```c
encode_b(OP_BRnzp, nzp, sync_offset, branch_offset)
```

AXEL API:

```c
axel_brnzp(&gpu, AXEL_P, sync_offset, branch_offset);
```

## Phase 6 SIMT ReLU regression

Phase 6 was introduced to prove real branch divergence.

Program:

```text
PC0: LDR   R1, THREAD_IDX, 0
PC1: CMP   R1, R0
PC2: BR P, sync_offset=2, branch_offset=2
PC3: CONST R1, 0
PC4: SYNC
PC5: STR   R1, THREAD_IDX, 4
PC6: RET
```

Input:

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

This verifies:

```text
LDR
register writeback
CMP
stored NZP
BRnzp
taken_mask
divergence_detected
warp stack push
SYNC
saved mask restore
STR
kernel_done
```

## Debug probe that helped isolate the bug

A useful temporary WB probe was used around core internals:

```python
def g(sig, d=0):
    try:
        return int(sig.value)
    except Exception:
        return d

try:
    wbs = g(core.write_back_en_sched)
    wbd = g(core.write_back_en_dec)
    rf0 = core.thread_gen[0].reg_file
    w_en0  = g(rf0.w_en)
    w_addr = g(rf0.w_addr)
    w_data = g(rf0.w_data)
    lrd0   = g(core.lsu_read_data[0])
    wdat0  = g(core.write_data[0])
    mrd_en = g(core.mem_read_en)

    print(
        f"WB cyc={cycle:05d} state={state:02d} "
        f"wb_sched={wbs} wb_dec={wbd} mem_rd={mrd_en} "
        f"w_en0={w_en0} w_addr={w_addr} w_data={w_data} "
        f"lsu_rd0={lrd0} write_data0={wdat0}"
    )
except Exception as e:
    print(f"WB probe failed: {e}")
```

This confirmed whether load data reached writeback.

After the issue was fixed, debug print logic was removed from the final clean testbench.

## Testbench memory-model fix

The top-level data memory model must use the core memory-controller request signals.

Current model watches:

```python
mc = dut.core_gen[core_id].core_inst.mc
```

Then reads:

```text
mc.mem_req_valid
mc.mem_req_addr
mc.mem_req_rw
mc.mem_req_data
```

Then drives:

```text
dut.data_mem_resp_valid
dut.data_mem_resp_data
```

Important:

```text
data_mem_resp_data is packed
```

so the model packs responses for all cores into one integer.

## Files edited during recent debug session

Main RTL files:

```text
Src/core/core.sv
Src/memory_controller/mem_controller.sv
Src/Top_level_GPU/top_level_gpu.sv
```

Main testbench files:

```text
Src/Top_level_GPU/test_top_level_gpu.py
Src/memory_controller/test_mem_controller.py
```

Assembler / ISA files touched for SIMT support:

```text
assembler/include/gpu_asm.h
assembler/include/axel.h
assembler/src/gpu_asm.c
assembler/src/axel.c
assembler/examples/phase4_forward.c
assembler/examples/phase6_simt_relu.c
```

Existing supporting RTL files involved:

```text
Src/decoder/decoder.sv
Src/scheduler/scheduler.sv
Src/pc/pc.sv
Src/warp_stack/warp_stack.sv
Src/lsu/lsu.sv
Src/registers/register_file.sv
```

Documentation files now being built:

```text
README.md
docs/architecture.md
docs/isa.md
docs/memory_map.md
docs/debug_log.md
Src/*/README.md
```

## Final clean test result

After fixes, the important expected result is:

```text
test_simt_relu passed
```

Expected print:

```text
── SIMT ReLU Results ──
  mem[4] = 5  (T0: +5 -> kept)
  mem[5] = 0  (T1: -3 -> zeroed)
  mem[6] = 8  (T2: +8 -> kept)
  mem[7] = 0  (T3: -1 -> zeroed)
```

## Git commit suggestion

Suggested commit message:

```text
fix: align memory response buses and complete SIMT ReLU path

- Add buffered round-robin per-core memory controller
- Align mem_controller resp_data with packed LSU response bus
- Drive top-level packed data_mem_resp_data correctly in cocotb
- Preserve stable instruction decode using core instruction latch
- Gate register writeback with scheduler, decoder, and active mask
- Support SIMT BRnzp/SYNC divergence path in top-level regression
- Update memory-controller tests for packed response lanes
- Confirm phase6 SIMT ReLU writes expected outputs
```

## Known risks still worth tracking

## Warp stack parameterization

Current `warp_stack` is effectively hardcoded for:

```text
THREADS_PER_CORE = 4
STACK_DEPTH = 4
```

Even though parameters exist, internal entry width and slicing are currently fixed.

Future fix:

```systemverilog
localparam ENTRY_W = 32 + THREADS_PER_CORE;
localparam SP_W = $clog2(STACK_DEPTH + 1);
```

## Dispatcher repeated launches

`kernel_done` is sticky until reset.

Current safe flow:

```text
reset before each kernel launch
```

Future improvement:

```text
clear kernel_done / next_block / active_blocks on new launch
```

if repeated launches without reset are needed.

## Program memory fallback RET

Fallback RET avoids hangs but can hide invalid PC bugs.

Future tests should check exact PC/instruction behavior for branch programs.

## DIV/MOD synthesis cost

`DIV` and `MOD` exist in RTL/ISA but are expensive for FPGA/ASIC synthesis.

Use with caution in synthesis-target builds.

## Packed/unpacked bus discipline

The project now depends heavily on matching packed/unpacked shapes.

Before editing memory interfaces, check:

```text
top_level_gpu.sv
core.sv
mem_controller.sv
test_top_level_gpu.py
inference.py
```

## Lessons learned

## 1. Passing unit tests do not prove integration bus shape

The memory controller could pass standalone tests while still being wired incorrectly at integration level.

Integration tests are necessary for packed/unpacked SystemVerilog bus issues.

## 2. Follow the data, not the assumption

The useful debug path was:

```text
memory dictionary
external response bus
memory controller input
memory controller output lane
LSU response input
LSU read-data register
register writeback data
final memory store
```

That chain isolated the exact failing boundary.

## 3. SIMT bugs often look like memory bugs first

If LDR data is wrong, CMP and branch behavior become wrong.

Always verify load/writeback first before debugging divergence logic.

## 4. One-cycle pulses need buffering

LSU requests are one-cycle pulses.

If an arbiter can be busy, it must latch pending requests or pulses will be lost.

## 5. Scheduler writeback and decoder writeback are different

Scheduler writeback is timing.

Decoder writeback is instruction intent.

Both are required.

## 6. Inactive lanes must be frozen

Correct SIMT behavior requires inactive lanes to stop:

```text
memory requests
register writes
PC updates
```

Otherwise divergent paths corrupt each other.

## Summary

The main debugging arc moved the GPU from a mostly functional scalar/SIMD-style design into a working SIMT design.

The key final fixes were:

```text
stable instruction latch
stored NZP branch decisions
active-mask gating
warp stack reconvergence
pending-buffer memory controller
packed response-data alignment
packed cocotb memory response model
```

The most important regression is now:

```text
Phase 6 SIMT ReLU passes.
```

That proves the design can run a real divergent branch kernel and reconverge correctly enough to produce correct per-thread output.
