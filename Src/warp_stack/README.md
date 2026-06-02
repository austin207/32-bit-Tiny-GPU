# Warp Stack

## Overview

`warp_stack` stores SIMT reconvergence information for divergent branch execution.

When a branch diverges, some active threads take the branch and some do not. The core executes one path first and saves the other path’s active mask on the warp stack. Later, when a `SYNC` instruction is reached, the saved mask is popped and restored so the other path or reconverged path can continue.

The stack stores one entry per divergence event:

```text
sync_pc
saved_mask
```

where:

```text
sync_pc     -> reconvergence PC
saved_mask  -> active-mask value to restore later
```

## RTL schematic

![Warp Stack RTL schematic](../../assets/Images-Components/Warp%20Stack-page-00001.jpg)

If the actual image file uses a different name, update the path above to match the file in `assets/Images-Components/`.

## Source files

```text
Src/warp_stack/warp_stack.sv
Src/warp_stack/test_warp_stack.py
```

## Position in the GPU

The warp stack is used inside `core.sv` during SIMT branch divergence and reconvergence.

```text
branch / divergence logic
        │
        │ push_sync_pc, push_saved_mask
        ▼
    warp_stack
        │
        │ top_sync_pc, top_saved_mask
        ▼
scheduler / active_mask restore path
```

In the core-level SIMT flow:

```text
BRNZP divergence detected
        │
        ▼
core pushes reconvergence info
        │
        ▼
scheduler activates taken_mask
        │
        ▼
taken path executes
        │
        ▼
SYNC instruction reached
        │
        ▼
core/scheduler pops saved mask
        │
        ▼
saved path / reconverged mask restored
```

## Module declaration

```systemverilog
module warp_stack #(
    parameter THREADS_PER_CORE = 4,
    parameter STACK_DEPTH = 4
) (
    input logic clk,
    input logic rst,

    input logic push,
    input logic [31:0] push_sync_pc,
    input logic [THREADS_PER_CORE-1:0] push_saved_mask,

    input logic pop,
    output logic [31:0] top_sync_pc,
    output logic [THREADS_PER_CORE-1:0] top_saved_mask,

    output logic stack_empty,
    output logic stack_full,
    output logic stack_overflow
);
```

## Parameters

| Parameter          | Default | Description                                               |
| ------------------ | ------: | --------------------------------------------------------- |
| `THREADS_PER_CORE` |     `4` | Number of SIMT thread lanes represented in the saved mask |
| `STACK_DEPTH`      |     `4` | Number of divergence entries the stack can store          |

## Port description

| Port              | Direction |              Width | Description                                           |
| ----------------- | --------- | -----------------: | ----------------------------------------------------- |
| `clk`             | input     |                  1 | Clock                                                 |
| `rst`             | input     |                  1 | Reset                                                 |
| `push`            | input     |                  1 | Pushes a new reconvergence entry if stack is not full |
| `push_sync_pc`    | input     |                 32 | Reconvergence PC to store                             |
| `push_saved_mask` | input     | `THREADS_PER_CORE` | Active mask to restore later                          |
| `pop`             | input     |                  1 | Pops the current top entry if stack is not empty      |
| `top_sync_pc`     | output    |                 32 | Reconvergence PC from the top stack entry             |
| `top_saved_mask`  | output    | `THREADS_PER_CORE` | Saved mask from the top stack entry                   |
| `stack_empty`     | output    |                  1 | High when stack pointer is zero                       |
| `stack_full`      | output    |                  1 | High when stack pointer equals `STACK_DEPTH`          |
| `stack_overflow`  | output    |                  1 | High when `push` is asserted while stack is full      |

## Internal storage

The current implementation stores each stack entry as a 36-bit packed value:

```systemverilog
logic [35:0] stack_mem [STACK_DEPTH-1:0];
```

The entry layout is:

```text
[35:4] -> sync_pc
[3:0]  -> saved_mask
```

So one stored entry is:

```systemverilog
{push_sync_pc, push_saved_mask}
```

The stack pointer is:

```systemverilog
logic [2:0] sp;
```

For the default `STACK_DEPTH = 4`, this is enough to represent values from `0` to `4`.

## Current parameterization limitation

Although `THREADS_PER_CORE` and `STACK_DEPTH` are parameters, the current implementation has hardcoded widths:

```systemverilog
logic [35:0] stack_mem [STACK_DEPTH-1:0];
logic [2:0] sp;

assign top_sync_pc = (sp > 0) ? stack_mem[sp-1][35:4] : 32'b0;
assign top_saved_mask = (sp > 0) ? stack_mem[sp-1][3:0] : '1;
```

This is correct for:

```text
THREADS_PER_CORE = 4
STACK_DEPTH = 4
```

If `THREADS_PER_CORE` changes, the stack entry width and mask slicing must also be updated.

A more parameterized future version should use:

```systemverilog
localparam ENTRY_W = 32 + THREADS_PER_CORE;
localparam SP_W = $clog2(STACK_DEPTH + 1);

logic [ENTRY_W-1:0] stack_mem [STACK_DEPTH-1:0];
logic [SP_W-1:0] sp;
```

and slice with `THREADS_PER_CORE`, not hardcoded `[3:0]`.

## Stack status signals

The status outputs are combinational:

```systemverilog
assign stack_empty = (sp == 0);
assign stack_full = (sp == STACK_DEPTH);
assign stack_overflow = push && stack_full;
```

Meaning:

```text
stack_empty    -> no entries available
stack_full     -> stack has reached maximum depth
stack_overflow -> push attempted while full
```

`stack_overflow` is not latched. It is high only while `push` is high and the stack is already full.

## Top entry read behavior

The top entry is exposed combinationally.

```systemverilog
assign top_sync_pc = (sp > 0) ? stack_mem[sp-1][35:4] : 32'b0;
assign top_saved_mask = (sp > 0) ? stack_mem[sp-1][3:0] : '1;
```

If the stack is not empty:

```text
top_sync_pc    = sync_pc from stack_mem[sp-1]
top_saved_mask = saved_mask from stack_mem[sp-1]
```

If the stack is empty:

```text
top_sync_pc    = 0
top_saved_mask = all ones
```

The all-ones default mask is useful because an empty stack means there is no saved divergent path, so the core can fall back to all threads active.

## Push behavior

A push stores a new entry at the current stack pointer and increments `sp`.

```systemverilog
if (push && !stack_full) begin
    stack_mem[sp] <= {push_sync_pc, push_saved_mask};
    sp <= sp + 1;
end
```

Example:

```text
Before push:
  sp = 0
  stack_empty = 1

Push:
  push_sync_pc = 0xDEADBEEF
  push_saved_mask = 4'b0101

After push:
  sp = 1
  top_sync_pc = 0xDEADBEEF
  top_saved_mask = 4'b0101
  stack_empty = 0
```

## Pop behavior

A pop decrements the stack pointer if the stack is not empty.

```systemverilog
if (pop && !stack_empty) begin
    sp <= sp - 1;
end
```

The stack memory contents are not cleared, but they are ignored because `sp` moves down.

Example:

```text
Before pop:
  sp = 1
  top entry valid

After pop:
  sp = 0
  stack_empty = 1
  top_sync_pc = 0
  top_saved_mask = all ones
```

## Overflow behavior

If the stack is full and `push` is asserted:

```text
stack_overflow = 1
```

The push is ignored because the push condition is:

```systemverilog
push && !stack_full
```

The current top entry remains unchanged.

This is tested by filling the stack with four entries, then attempting a fifth push.

## Simultaneous push and pop behavior

The current implementation has two independent `if` statements:

```systemverilog
if (push && !stack_full) begin
    stack_mem[sp] <= {push_sync_pc, push_saved_mask};
    sp <= sp + 1;
end 

if (pop && !stack_empty) begin
    sp <= sp - 1;
end
```

If `push` and `pop` are asserted in the same cycle, both blocks can execute. Since both assign `sp`, the later assignment wins in simulation.

Current design rule:

```text
Do not assert push and pop in the same cycle.
```

In the current core integration, this should not happen because:

```text
DIVERGE  -> push
SYNC_POP -> pop
```

are separate scheduler states.

If simultaneous push/pop support is needed later, this logic should be rewritten with explicit priority or net-zero stack-pointer behavior.

## Reset behavior

On reset:

```systemverilog
if (rst) begin
    sp <= 0;
end
```

This makes the stack empty.

The stack memory contents are not cleared, but they are ignored while `sp == 0`.

Reset is asynchronous because the sequential block uses:

```systemverilog
always_ff @( posedge clk or posedge rst )
```

## Current RTL implementation

```systemverilog
logic [35:0] stack_mem [STACK_DEPTH-1:0];
logic [2:0] sp;

assign stack_empty = (sp == 0);
assign stack_full = (sp == STACK_DEPTH);
assign stack_overflow = push && stack_full;

assign top_sync_pc = (sp > 0) ? stack_mem[sp-1][35:4] : 32'b0;
assign top_saved_mask = (sp > 0) ? stack_mem[sp-1][3:0] : '1;

always_ff @( posedge clk or posedge rst ) begin
    if (rst) begin
        sp <= 0;
    end else begin
        if (push && !stack_full) begin
            stack_mem[sp] <= {push_sync_pc, push_saved_mask};
            sp <= sp + 1;
        end 
        if (pop && !stack_empty) begin
            sp <= sp - 1;
        end
    end
end
```

## Interaction with core

Inside `core.sv`, the warp stack is used for branch divergence/reconvergence.

Typical connections:

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

The core generates:

```systemverilog
assign ws_push = (current_state == 4'b0111);
assign ws_pop  = (current_state == 4'b1000);
```

Where:

```text
4'b0111 = DIVERGE
4'b1000 = SYNC_POP
```

## Saved mask behavior

On divergence, the core saves the not-taken active path:

```systemverilog
.push_saved_mask(~taken_mask & active_mask)
```

Meaning:

```text
taken_mask              -> threads taking the branch
~taken_mask & active_mask -> active threads not taking the branch
```

Example:

```text
active_mask = 4'b1111
taken_mask  = 4'b0101

saved mask  = ~0101 & 1111
            = 1010
```

Then the scheduler activates `taken_mask` first.

At `SYNC_POP`, the scheduler restores:

```systemverilog
active_mask <= saved_mask;
```

where `saved_mask` comes from the top stack entry.

## Sync PC behavior

`push_sync_pc` stores the reconvergence PC.

Current stack output exposes:

```text
top_sync_pc
```

The current scheduler primarily uses `saved_mask` for active-mask restoration. `top_sync_pc` is available for reconvergence PC tracking and future control improvements.

If the PC reconvergence logic becomes more advanced later, this signal should be documented again with its exact role.

## SIMT ReLU example

For the SIMT ReLU program:

```text
PC0: LDR   R1, THREAD_IDX, 0
PC1: CMP   R1, R0
PC2: BR P, sync_offset=2, branch_offset=2
PC3: CONST R1, 0
PC4: SYNC
PC5: STR   R1, THREAD_IDX, 4
PC6: RET
```

With input:

```text
T0 =  5
T1 = -3
T2 =  8
T3 = -1
```

After `CMP` and `BR P`:

```text
taken_mask = 4'b0101
saved_mask = 4'b1010
```

The warp stack stores:

```text
sync_pc    = PC4
saved_mask = 4'b1010
```

The taken path executes first for T0 and T2. At `SYNC`, the saved mask is restored so T1 and T3 can execute the not-taken path / reconverge according to the current core scheduling behavior.

## Timing assumptions

The warp stack assumes:

```text
- push_sync_pc and push_saved_mask are valid when push is high.
- pop is asserted only when the scheduler/core wants to restore a saved path.
- push and pop are not asserted in the same cycle.
- stack_overflow is observed externally if overflow detection is needed.
- THREADS_PER_CORE remains 4 unless the hardcoded stack entry width is updated.
- STACK_DEPTH remains compatible with the fixed 3-bit sp unless sp is parameterized later.
```

## Verification

Unit test file:

```text
Src/warp_stack/test_warp_stack.py
```

## Current tests

| Test                     | What it checks                                                                                         |
| ------------------------ | ------------------------------------------------------------------------------------------------------ |
| `test_push`              | Push stores `sync_pc` and `saved_mask`, stack becomes non-empty                                        |
| `test_pop`               | Pop removes the top entry, stack becomes empty, pop-on-empty does not underflow                        |
| `test_full_and_overflow` | Filling the stack asserts `stack_full`; extra push asserts `stack_overflow` and does not overwrite top |

## `test_push`

Stimulus:

```text
push_sync_pc = 0xDEADBEEF
push_saved_mask = 4'b0101
push = 1
```

Expected:

```text
stack_empty = 0
top_sync_pc = 0xDEADBEEF
top_saved_mask = 4'b0101
```

## `test_pop`

Sequence:

```text
1. Push one entry.
2. Pop it.
3. Confirm stack_empty = 1.
4. Pop again while empty.
5. Confirm stack_empty remains 1.
```

This proves empty-pop does not underflow.

## `test_full_and_overflow`

Sequence:

```text
1. Push four entries into default depth-4 stack.
2. Confirm stack_full = 1.
3. Attempt fifth push.
4. Confirm stack_overflow = 1.
5. Confirm top entry remains the last valid entry.
```

Expected final top:

```text
top_sync_pc = 0x1003
```

not the overflow push value.

## Testbench behavior

The testbench reset helper initializes inputs:

```python
dut.rst.value = 1
dut.push.value = 0
dut.pop.value = 0
dut.push_sync_pc.value = 0
dut.push_saved_mask.value = 0
```

Then it waits for two rising edges, deasserts reset, and waits one nanosecond for outputs to settle.

## Recommended additional tests

| Test                                | Purpose                                                                            |
| ----------------------------------- | ---------------------------------------------------------------------------------- |
| `test_top_default_when_empty`       | Verify empty stack outputs `top_sync_pc = 0`, `top_saved_mask = all ones`          |
| `test_lifo_order`                   | Push multiple entries and pop them in reverse order                                |
| `test_overflow_not_latched`         | Confirm `stack_overflow` clears when `push` deasserts                              |
| `test_no_push_when_full`            | Verify stack contents are unchanged after overflow push                            |
| `test_no_pop_when_empty`            | Verify `sp` does not underflow on empty pop                                        |
| `test_reset_after_pushes`           | Verify reset makes stack empty after entries exist                                 |
| `test_push_pop_same_cycle_behavior` | Define or forbid simultaneous push/pop behavior                                    |
| `test_parameterized_depth`          | Verify behavior for non-default `STACK_DEPTH` after parameterizing `sp` width      |
| `test_parameterized_threads`        | Verify mask width for non-default `THREADS_PER_CORE` after fixing hardcoded slices |

## Known pitfalls

Do not assert `push` and `pop` in the same cycle.

Current RTL does not define clean simultaneous push/pop behavior because both blocks assign `sp`.

Do not change `THREADS_PER_CORE` without updating hardcoded stack entry width and mask slicing.

Current stack storage assumes:

```text
32-bit sync_pc + 4-bit saved_mask = 36 bits
```

Do not change `STACK_DEPTH` beyond what the fixed `sp` width can represent.

Current `sp` is:

```systemverilog
logic [2:0] sp;
```

This works for depth 4 but should be parameterized for general use.

Do not assume stack memory clears on reset.

Only `sp` resets. Old entries remain in memory but are ignored when `sp == 0`.

Do not ignore `stack_overflow`.

If divergence nesting exceeds `STACK_DEPTH`, new entries are not pushed. That can break reconvergence.

## Related integration tests

| Test                        | File                                      | What it proves                                     |
| --------------------------- | ----------------------------------------- | -------------------------------------------------- |
| `test_scheduler_divergence` | `Src/scheduler/test_scheduler.py`         | Scheduler enters DIVERGE and updates active mask   |
| `test_simt_relu`            | `Src/Top_level_GPU/test_top_level_gpu.py` | Divergence and SYNC behavior work in a real kernel |
| `test_core_basic`           | `Src/core/test_core.py`                   | Core can complete basic execution flow             |
| `test_gpu_axel_program`     | `Src/Top_level_GPU/test_top_level_gpu.py` | Full top-level program execution still completes   |

## Last known status

```text
Status: passing

Verified with:
  cd ~/gpu-project
  make test

Current unit coverage:
  push
  pop
  full / overflow
```

## Design summary

`warp_stack` is a small LIFO stack for SIMT reconvergence metadata. It stores a reconvergence PC and a saved active mask for divergent branch handling.

The most important behavior is:

```text
push -> store {sync_pc, saved_mask}
pop  -> restore previous top entry by decrementing sp
top_saved_mask defaults to all ones when empty
```

The most important current limitation is:

```text
the storage format is hardcoded for THREADS_PER_CORE = 4
```

So future parameter changes should first parameterize the entry width, mask slice, and stack-pointer width.
