# Scheduler

## Overview

`scheduler` is the core control FSM for the Tiny GPU.

It controls the instruction lifecycle inside one core by sequencing fetch, decode, memory request, memory wait, execute, writeback/update, divergence handling, and SYNC reconvergence.

The scheduler does not execute instructions directly. Instead, it emits enable pulses and state/control outputs used by the fetcher, LSU, ALU/writeback path, PC, warp stack, and core block-completion logic.

The scheduler is sequential logic and updates on the rising edge of `clk`.

## RTL schematic

![Scheduler RTL schematic](../../assets/Images-Components/Scheduler-page-00001.jpg)

If the image file in `assets/Images-Components/` has a different exact name, update the path above to match it.

## Source files

```text
Src/scheduler/scheduler.sv
Src/scheduler/test_scheduler.py
```

## Position in the GPU

The scheduler sits in the control path of each core.

```text
decoder control signals
fetcher done
LSU done
branch/divergence signals
SYNC/RET signals
        │
        ▼
    scheduler
        │
        ├── fetcher_en
        ├── lsu_en
        ├── execute_en
        ├── write_back_en
        ├── pc_en
        ├── active_mask
        └── block_done
```

Inside the core:

```text
fetcher
decoder
scheduler
per-thread ALU/register/PC/LSU lanes
warp_stack
memory_controller
```

The scheduler decides when those modules are allowed to operate.

## Module declaration

```systemverilog
module scheduler #(
    parameter NUM_CORES = 1,
    parameter THREADS_PER_CORE = 4,
    parameter TOTAL_THREADS = NUM_CORES * THREADS_PER_CORE
)(
    input logic clk,
    input logic rst,

    input logic core_start,
    input logic fetcher_done,
    input logic [TOTAL_THREADS-1:0] lsu_done,
    input logic mem_read_en,
    input logic mem_write_en,
    input logic ret,
    input logic divergence_detected,
    input logic [THREADS_PER_CORE-1:0] taken_mask,
    input logic sync_en,
    input logic [THREADS_PER_CORE-1:0] saved_mask,

    output logic fetcher_en,
    output logic lsu_en,
    output logic execute_en,
    output logic write_back_en,
    output logic [3:0] current_state,
    output logic [THREADS_PER_CORE-1:0] active_mask,
    output logic block_done,
    output logic pc_en
);
```

## Parameters

| Parameter          |                        Default | Description                                                   |
| ------------------ | -----------------------------: | ------------------------------------------------------------- |
| `NUM_CORES`        |                            `1` | Number of cores represented in the scheduler parameterization |
| `THREADS_PER_CORE` |                            `4` | Number of SIMT lanes inside one core                          |
| `TOTAL_THREADS`    | `NUM_CORES * THREADS_PER_CORE` | Width of `lsu_done` input                                     |

In the current core integration, the scheduler is used per core, so `NUM_CORES = 1` and `TOTAL_THREADS = THREADS_PER_CORE`.

## Port description

| Port                  | Direction |              Width | Description                                          |
| --------------------- | --------- | -----------------: | ---------------------------------------------------- |
| `clk`                 | input     |                  1 | Clock                                                |
| `rst`                 | input     |                  1 | Reset                                                |
| `core_start`          | input     |                  1 | Start signal from dispatcher/core launch path        |
| `fetcher_done`        | input     |                  1 | Indicates fetcher captured an instruction            |
| `lsu_done`            | input     |    `TOTAL_THREADS` | Per-thread LSU completion bits                       |
| `mem_read_en`         | input     |                  1 | Decoder says current instruction is a load           |
| `mem_write_en`        | input     |                  1 | Decoder says current instruction is a store          |
| `ret`                 | input     |                  1 | Decoder says current instruction is RET              |
| `divergence_detected` | input     |                  1 | Core branch logic detected partial branch divergence |
| `taken_mask`          | input     | `THREADS_PER_CORE` | Mask of active threads that took the branch          |
| `sync_en`             | input     |                  1 | Decoder says current instruction is SYNC             |
| `saved_mask`          | input     | `THREADS_PER_CORE` | Mask restored from warp stack during SYNC_POP        |
| `fetcher_en`          | output    |                  1 | Enables instruction fetch                            |
| `lsu_en`              | output    |                  1 | Enables per-thread LSU transaction launch            |
| `execute_en`          | output    |                  1 | Enables execute phase                                |
| `write_back_en`       | output    |                  1 | Scheduler writeback/update pulse                     |
| `current_state`       | output    |                  4 | Current FSM state encoding                           |
| `active_mask`         | output    | `THREADS_PER_CORE` | Current active SIMT lane mask                        |
| `block_done`          | output    |                  1 | Pulsed when RET completes the current block          |
| `pc_en`               | output    |                  1 | Enables per-thread PC update                         |

## FSM states

| State      |  Encoding | Purpose                                                        |
| ---------- | --------: | -------------------------------------------------------------- |
| `IDLE`     | `4'b0000` | Wait for `core_start`                                          |
| `FETCH`    | `4'b0001` | Enable fetcher and wait for instruction fetch completion       |
| `DECODE`   | `4'b0010` | Decide whether instruction needs memory path or direct execute |
| `REQUEST`  | `4'b0011` | Pulse `lsu_en` to launch LSU requests                          |
| `WAIT`     | `4'b0100` | Wait until all active LSU lanes are done                       |
| `EXECUTE`  | `4'b0101` | Pulse `execute_en`                                             |
| `UPDATE`   | `4'b0110` | Pulse writeback/PC update/block completion control             |
| `DIVERGE`  | `4'b0111` | Apply taken branch mask after divergence                       |
| `SYNC_POP` | `4'b1000` | Restore saved active mask during reconvergence                 |

The current state is exposed through:

```systemverilog
assign current_state = state;
```

This is useful for cocotb tests and debugging.

## Reset behavior

On reset:

```text
state         -> IDLE
fetcher_en    -> 0
lsu_en        -> 0
execute_en    -> 0
write_back_en -> 0
block_done    -> 0
pc_en         -> 0
active_mask   -> all ones
```

RTL:

```systemverilog
if (rst) begin
    state <= IDLE;

    fetcher_en <= 0;
    lsu_en <= 0;
    execute_en <= 0;
    write_back_en <= 0;
    block_done <= 0;
    pc_en <= 0;
    active_mask <= '1;
end
```

Reset is asynchronous because the sequential block uses:

```systemverilog
always_ff @( posedge clk or posedge rst )
```

## Default output behavior

On every non-reset clock cycle, the pulse-style outputs are cleared first:

```systemverilog
fetcher_en <= 0;
lsu_en <= 0;
execute_en <= 0;
write_back_en <= 0;
block_done <= 0;
pc_en <= 0;
```

Then the current FSM state may assert one or more outputs for that cycle.

This means the following outputs are one-cycle pulse-style controls:

```text
lsu_en
execute_en
write_back_en
block_done
pc_en
```

`fetcher_en` is asserted during `FETCH`, so it can remain high while the scheduler waits for `fetcher_done`.

## Normal non-memory instruction flow

For an ALU/CONST/CMP/BR/SYNC/RET-style instruction that does not require memory request/wait, the normal path is:

```text
IDLE
  -> FETCH
  -> DECODE
  -> EXECUTE
  -> UPDATE
  -> FETCH / IDLE / DIVERGE / SYNC_POP
```

Sequence:

```text
core_start asserted
fetcher_en asserted
fetcher_done arrives
decoder control decides non-memory path
execute_en pulses
write_back_en pulses in UPDATE
pc_en pulses unless RET
next instruction fetch begins
```

## Memory instruction flow

For `LDR` or `STR`, the decoder asserts:

```text
mem_read_en = 1
```

or:

```text
mem_write_en = 1
```

The scheduler path becomes:

```text
IDLE
  -> FETCH
  -> DECODE
  -> REQUEST
  -> WAIT
  -> EXECUTE
  -> UPDATE
  -> FETCH / IDLE / DIVERGE / SYNC_POP
```

In `REQUEST`:

```systemverilog
lsu_en <= 1;
state <= WAIT;
```

In `WAIT`, the scheduler waits until all LSU lanes are done:

```systemverilog
logic all_done;
assign all_done = &lsu_done;
```

When `all_done` is true:

```systemverilog
state <= EXECUTE;
```

In core integration, inactive lanes are treated as done by the core before connecting into the scheduler:

```systemverilog
assign lsu_done = lsu_done_latch | ~active_mask;
```

So the scheduler can simply reduce all `lsu_done` bits.

## RET behavior

In `UPDATE`, RET has highest priority:

```systemverilog
if (ret) begin
    block_done <= 1;
    state <= IDLE;
end
```

For RET:

```text
block_done pulses
state returns to IDLE
pc_en is not asserted
```

The core/dispatcher uses `block_done` to mark the assigned block as complete.

## Divergence behavior

If `divergence_detected` is high during `UPDATE`, the scheduler enters `DIVERGE`:

```systemverilog
else if (divergence_detected) begin
    state <= DIVERGE;
    pc_en <= 1;
end
```

In this UPDATE cycle:

```text
pc_en = 1
write_back_en = 1
state transitions to DIVERGE
```

Then in `DIVERGE`:

```systemverilog
active_mask <= taken_mask;
state <= FETCH;
```

This means the taken branch path becomes the active path.

The not-taken active mask is saved by the core/warp-stack logic outside the scheduler.

## SYNC behavior

If `sync_en` is high during `UPDATE`, and RET/divergence did not take priority, the scheduler enters `SYNC_POP`:

```systemverilog
else if (sync_en) begin
    state <= SYNC_POP;
    pc_en <= 1;
end
```

Then in `SYNC_POP`:

```systemverilog
active_mask <= saved_mask;
state <= FETCH;
```

`saved_mask` comes from the warp stack in the core. If the warp stack is empty, the core may provide all ones.

This restores a previously saved inactive path or reconverges all threads depending on the core/warp stack state.

## Normal UPDATE behavior

If the instruction is not RET, not divergent, and not SYNC:

```systemverilog
else begin
    state <= FETCH;
    pc_en <= 1;
end
write_back_en <= 1;
```

This means:

```text
writeback/update pulse occurs
PC advances
next fetch begins
```

Important: `write_back_en` is asserted in UPDATE for all instructions, but actual register writeback in `core.sv` is also gated by decoder writeback enable:

```systemverilog
.w_en(write_back_en_sched & write_back_en_dec & active_mask[i])
```

So non-writeback instructions like BR, SYNC, STR, and RET do not write registers.

## Active mask behavior

`active_mask` controls which SIMT thread lanes are active.

On reset:

```text
active_mask = all ones
```

On new core start:

```systemverilog
active_mask <= '1;
```

On divergence:

```systemverilog
active_mask <= taken_mask;
```

On SYNC_POP:

```systemverilog
active_mask <= saved_mask;
```

The scheduler itself does not calculate branch decisions. It only receives the result from core logic:

```text
taken_mask
divergence_detected
saved_mask
```

## State transition summary

```text
IDLE:
  if core_start:
    fetcher_en = 1
    active_mask = all ones
    state = FETCH

FETCH:
  fetcher_en = 1
  if fetcher_done:
    state = DECODE

DECODE:
  if mem_read_en or mem_write_en:
    state = REQUEST
  else:
    state = EXECUTE

REQUEST:
  lsu_en = 1
  state = WAIT

WAIT:
  if all_done:
    state = EXECUTE

EXECUTE:
  execute_en = 1
  state = UPDATE

UPDATE:
  write_back_en = 1
  if ret:
    block_done = 1
    state = IDLE
  else if divergence_detected:
    pc_en = 1
    state = DIVERGE
  else if sync_en:
    pc_en = 1
    state = SYNC_POP
  else:
    pc_en = 1
    state = FETCH

DIVERGE:
  active_mask = taken_mask
  state = FETCH

SYNC_POP:
  active_mask = saved_mask
  state = FETCH
```

## Priority order in UPDATE

The UPDATE state uses this priority:

1. RET
2. divergence_detected
3. sync_en
4. normal PC advance / next fetch

This means if multiple control signals are asserted at the same time:

```text
RET wins over divergence and SYNC
divergence wins over SYNC
SYNC wins over normal update
```

Normally, the decoder/core should ensure conflicting instruction-type controls are not asserted together.

## Current RTL implementation

```systemverilog
always_ff @( posedge clk or posedge rst ) begin 
    if (rst) begin
        state <= IDLE;

        fetcher_en <= 0;
        lsu_en <= 0;
        execute_en <= 0;
        write_back_en <= 0;
        block_done <= 0;
        pc_en <= 0;
        active_mask <= '1;
    end else begin
        fetcher_en <= 0;
        lsu_en <= 0;
        execute_en <= 0;
        write_back_en <= 0;
        block_done <= 0;
        pc_en <= 0;

        case (state)
           IDLE: begin
                if (core_start) begin
                    fetcher_en <= 1;
                    active_mask <= '1;
                    state <= FETCH;
                end
            end

            FETCH: begin
                fetcher_en <= 1;
                if (fetcher_done) begin
                    fetcher_en <= 0;
                    state <= DECODE;
                end
            end

            DECODE: begin
                if (mem_read_en || mem_write_en) begin
                    state <= REQUEST;
                end else begin
                    state <= EXECUTE;
                end
            end

            REQUEST: begin
                lsu_en <= 1;
                state <= WAIT;
            end

            WAIT: begin
                if (all_done) begin
                    state <= EXECUTE;
                end
            end

            EXECUTE: begin
                execute_en <= 1;
                state <= UPDATE;
            end

            UPDATE: begin
                if (ret) begin
                    block_done <= 1;
                    state <= IDLE;
                end else if (divergence_detected) begin
                    state <= DIVERGE;
                    pc_en <= 1;
                end else if (sync_en) begin
                    state <= SYNC_POP;
                    pc_en <= 1;
                end else begin
                    state <= FETCH;
                    pc_en <= 1;
                end
                write_back_en <= 1;
            end

            DIVERGE: begin
                active_mask <= taken_mask;
                state <= FETCH;
            end

            SYNC_POP: begin
                active_mask <= saved_mask;
                state <= FETCH;
            end

            default: ;
        endcase
    end
end
```

## Timing assumptions

The scheduler assumes:

- core_start is asserted when a core should begin a block.
- fetcher_done pulses when instruction fetch completes.
- decoder outputs are stable while the scheduler is deciding DECODE/UPDATE behavior.
- lsu_done bits eventually become all ones for memory operations.
- divergence_detected and taken_mask are valid in UPDATE.
- sync_en is valid in UPDATE for SYNC instructions.
- saved_mask is valid when entering SYNC_POP.
- ret is valid in UPDATE for RET instructions.

## Interaction with instruction latch

The scheduler relies on stable decoder control signals across several cycles.

For this reason, `core.sv` latches the fetched instruction when `fetcher_done` occurs. The decoder reads the latched instruction, not a raw fetcher output.

This matters especially for memory instructions:

```text
DECODE -> REQUEST -> WAIT -> EXECUTE -> UPDATE
```

Without instruction latching, `mem_read_en`, `write_back_en`, or `ret` could become unstable before the instruction completes.

## Interaction with register writeback

The scheduler emits `write_back_en` during UPDATE.

However, register writeback must also be gated by decoder writeback enable:

```systemverilog
write_back_en_sched & write_back_en_dec & active_mask[i]
```

This prevents accidental writes from instructions that do not write registers.

Important examples:

```text
CMP updates NZP, not a register
BR updates PC, not a register
STR writes memory, not a register
SYNC restores masks, not a register
RET completes block, not a register
```

## Interaction with PC

The scheduler emits `pc_en` during UPDATE for:

```text
normal instruction advance
branch/divergence advance
SYNC advance
```

It does not emit `pc_en` for RET.

In `core.sv`, `pc_en` is gated per thread:

```systemverilog
.pc_en(pc_en & active_mask[i])
```

Inactive lanes do not advance their PCs.

## Interaction with LSU

For memory instructions, the scheduler emits:

```systemverilog
lsu_en <= 1;
```

in REQUEST.

The per-thread LSU instances receive:

```systemverilog
.core_en(lsu_en & active_mask[i])
```

Only active lanes issue memory transactions.

The scheduler waits in WAIT until:

```systemverilog
all_done = &lsu_done;
```

## Interaction with warp stack

The scheduler does not push or pop the warp stack directly. Instead, `core.sv` derives warp-stack control from `current_state`:

```systemverilog
assign ws_push = (current_state == 4'b0111);
assign ws_pop  = (current_state == 4'b1000);
```

So:

```text
DIVERGE  -> warp stack push
SYNC_POP -> warp stack pop
```

The scheduler changes `active_mask` using either:

```text
taken_mask
saved_mask
```

## Unit test

Unit test file:

```text
Src/scheduler/test_scheduler.py
```

The uploaded scheduler test file currently covers:

```text
test_scheduler_basic_flow
test_scheduler_memory_flow
test_scheduler_ret_instruction
test_scheduler_divergence
```

## `test_scheduler_basic_flow`

Checks the non-memory instruction path:

```text
core_start
FETCH
fetcher_done
DECODE
EXECUTE
UPDATE
FETCH
```

Expected outputs:

```text
execute_en = 1 in EXECUTE
write_back_en = 1 in UPDATE
state returns to FETCH
```

## `test_scheduler_memory_flow`

Checks the memory instruction path:

```text
core_start
FETCH
fetcher_done
DECODE with mem_read_en = 1
REQUEST
WAIT
lsu_done = 4'b1111
EXECUTE
```

Expected output:

```text
execute_en = 1 in EXECUTE
```

## `test_scheduler_ret_instruction`

Checks RET behavior.

Expected behavior:

```text
RET reaches UPDATE
block_done = 1
scheduler returns to IDLE
```

## `test_scheduler_divergence`

Checks divergence behavior.

Stimulus:

```text
divergence_detected = 1
taken_mask = 4'b1010
```

Expected behavior:

```text
scheduler enters DIVERGE
write_back_en = 1 during UPDATE-to-DIVERGE transition
pc_en = 1 during divergence path
after DIVERGE:
    active_mask = 4'b1010
    state = FETCH
```

## Current verification status

Current tests cover:

| Test                             | Main behavior checked                        |
| -------------------------------- | -------------------------------------------- |
| `test_scheduler_basic_flow`      | Basic non-memory pipeline flow               |
| `test_scheduler_memory_flow`     | REQUEST/WAIT path for memory instruction     |
| `test_scheduler_ret_instruction` | RET block completion                         |
| `test_scheduler_divergence`      | Divergence transition and active-mask update |

## Recommended additional tests

| Test                                        | Purpose                                                              |
| ------------------------------------------- | -------------------------------------------------------------------- |
| `test_reset_outputs`                        | Verify reset clears outputs and sets active mask to all ones         |
| `test_fetcher_waits_until_done`             | Verify scheduler remains in FETCH until `fetcher_done`               |
| `test_lsu_waits_until_all_done`             | Verify scheduler remains in WAIT until all active LSU lanes complete |
| `test_store_memory_flow`                    | Verify `mem_write_en` also enters REQUEST/WAIT                       |
| `test_sync_pop`                             | Verify `sync_en` enters SYNC_POP and restores `saved_mask`           |
| `test_update_priority_ret_over_divergence`  | Verify RET wins over divergence                                      |
| `test_update_priority_divergence_over_sync` | Verify divergence wins over SYNC                                     |
| `test_no_core_start_stays_idle`             | Verify scheduler remains IDLE without `core_start`                   |
| `test_block_done_one_cycle_pulse`           | Verify `block_done` clears after one cycle                           |
| `test_write_back_one_cycle_pulse`           | Verify `write_back_en` is one-cycle in UPDATE                        |
| `test_pc_en_not_asserted_for_ret`           | Verify RET does not advance PC                                       |

## Known pitfalls

Do not use scheduler `write_back_en` alone for register writes.

It must be combined with decoder `write_back_en` and `active_mask`.

Do not expect `core_start` to run forever.

The scheduler only uses it to leave IDLE. Once the core is running, state transitions are controlled by fetcher/decoder/LSU/branch signals.

Do not forget inactive lanes during memory waits.

The scheduler waits for all `lsu_done` bits, so core logic must mark inactive lanes as done.

Do not assume SYNC and divergence are the same.

DIVERGE activates `taken_mask`. SYNC_POP restores `saved_mask`.

Do not let decoder/control signals become unstable across multicycle instructions.

The core instruction latch exists to prevent this.

Do not assume `write_back_en` means a register definitely writes.

In UPDATE for RET/divergence/SYNC, `write_back_en` can still pulse, but the decoder gate prevents invalid register writes.

## Related integration tests

| Test                    | File                                      | What it proves                                                       |
| ----------------------- | ----------------------------------------- | -------------------------------------------------------------------- |
| `test_core_basic`       | `Src/core/test_core.py`                   | Scheduler can drive core through fetch/execute/RET                   |
| `test_simt_relu`        | `Src/Top_level_GPU/test_top_level_gpu.py` | Scheduler handles memory load, CMP, divergence, SYNC, store, and RET |
| `test_gpu_axel_program` | `Src/Top_level_GPU/test_top_level_gpu.py` | Scheduler supports longer top-level AXEL program execution           |
| `test_lsu`              | `Src/lsu/test_lsu.py`                     | LSU done pulses used by scheduler memory flow are valid              |
| `test_fetcher`          | `Src/fetcher/test_fetcher.py`             | Fetcher done pulse used by scheduler FETCH state is valid            |

## Last known status

```text
Status: passing

Verified with:
  cd ~/gpu-project
  make test

Current unit coverage:
  basic non-memory flow
  memory flow
  RET instruction
  divergence path
```

## Design summary

`scheduler` is the core-level instruction sequencing FSM. It controls fetch, memory request/wait, execute, update/writeback, block completion, divergence handling, and SYNC mask restoration.

The most important behavior is:

```text
normal instruction:
  FETCH -> DECODE -> EXECUTE -> UPDATE -> FETCH

memory instruction:
  FETCH -> DECODE -> REQUEST -> WAIT -> EXECUTE -> UPDATE -> FETCH

RET:
  UPDATE -> block_done -> IDLE

divergence:
  UPDATE -> DIVERGE -> active_mask = taken_mask -> FETCH

SYNC:
  UPDATE -> SYNC_POP -> active_mask = saved_mask -> FETCH
```

The most important integration rule is:

```text
scheduler write_back_en must be combined with decoder write_back_en and active_mask before writing registers
```
