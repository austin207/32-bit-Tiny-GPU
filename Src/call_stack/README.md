# Call Stack

## Overview

`call_stack` stores return addresses for the `CALL` / `SRET` subroutine
mechanism added to axelcc (see `axelcc/src/emit.c`'s `emit_call`/`emit_sret`
and `axelcc/src/sema.c`'s func handling).

A `CALL` jumps to a function's entry point like an unconditional branch, but
first needs to remember where to come back to. `call_stack` holds that
return address. When the function body later hits `SRET` (subroutine
return, opcode `0x1D` -- deliberately distinct from kernel-exit `RET`,
opcode `0x12`), the core pops this stack and jumps back there.

The stack stores one entry per outstanding call:

```text
return_pc
```

where:

```text
return_pc -> the address of the instruction immediately after the CALL
```

This is a simpler cousin of [[warp_stack]] (or `Src/warp_stack/`): both are
small per-core LIFO stacks pushed/popped around control-flow events, but
`call_stack` stores only a return PC -- no saved active-mask, because a
`CALL` is always taken uniformly by every thread that reaches it (it never
causes divergence by itself; see "Position in the GPU" below).

## Source files

```text
Src/call_stack/call_stack.sv
Src/call_stack/tests/common.py
Src/call_stack/tests/test_call_stack_directed.py
Src/call_stack/tests/test_call_stack_random.py
```

## Position in the GPU

**Status: implemented, unit-tested standalone, and wired into `core.sv` /
`pc.sv` / `decoder.sv`.** Verified end-to-end on real RTL by
`Src/Top_level_GPU/tests/test_axelcc_func_basic.py`, which runs the compiled
`test_func_basic.axelc` binary (a `func add3(a,b,c)` called twice via
`CALL`/`SRET`) through the full GPU and checks its outputs bit-exact against
the hand-traced golden in `axelcc/tests/golden_test.py`.

```text
decoder (opcode 0x1C CALL / 0x1D SRET)
        │
        │ call_en, sret_en
        ▼
core.sv:
  call_return_pc = active_pc + 1
        │
        │ push = call_en & pc_en, push_return_pc = call_return_pc
        │ pop  = sret_en & pc_en
        ▼
    call_stack
        │
        │ top_return_pc
        ▼
  broadcast to every per-thread pc_inst as sret_target
```

Why this needs no new scheduler state (unlike `warp_stack`'s `DIVERGE` /
`SYNC_POP`): `pc_en` already pulses exactly once per instruction, during the
scheduler's `UPDATE` state, regardless of opcode. `call_en`/`sret_en` are
combinational off the currently-latched instruction the whole time it's
executing, so gating push/pop directly with `call_en & pc_en` / `sret_en &
pc_en` fires on precisely the right edge with no extra FSM states in
`scheduler.sv`.

Why one `call_stack` per core (not one per thread, and not one per warp
divergence path): this is a lockstep SIMT core -- one shared `instruction`
register, one shared decoder, fetched from one `active_pc` per core. Every
currently-active thread shares the identical PC value whenever any
instruction (including `CALL`) executes, so one shared return-address push
is correct and sufficient. This mirrors the same property `warp_stack`
already relies on for `sync_pc`.

Why `STACK_DEPTH = 2` is safe even though it's provably only ever used to
depth 1: `sema.c` rejects a `func` body that calls another `func` --
recursion/nesting is a compile-time error, not a runtime possibility. So a
correctly-compiled axelcc program never holds more than one entry on this
stack. The extra depth is pure headroom for a hardware safety net
(`stack_overflow` exists for exactly that scenario), not a requirement.

## Module declaration

```systemverilog
module call_stack #(
    parameter STACK_DEPTH = 2   // provably >=1 is enough -- see above
) (
    input  logic clk,
    input  logic rst,

    input  logic push,
    input  logic [31:0] push_return_pc,

    input  logic pop,
    output logic [31:0] top_return_pc,

    output logic stack_empty,
    output logic stack_full,
    output logic stack_overflow
);
```

## Parameters

| Parameter     | Default | Description                                  |
| ------------- | ------: | --------------------------------------------- |
| `STACK_DEPTH` |     `2` | Number of outstanding return addresses stored |

## Port description

| Port             | Direction |  Width | Description                                        |
| ---------------- | --------- | -----: | --------------------------------------------------- |
| `clk`            | input     |      1 | Clock                                               |
| `rst`            | input     |      1 | Reset                                               |
| `push`           | input     |      1 | Pushes a new return address if stack is not full    |
| `push_return_pc` | input     |     32 | Return address to store (CALL's next-PC)            |
| `pop`            | input     |      1 | Pops the current top entry if stack is not empty    |
| `top_return_pc`  | output    |     32 | Return address from the top stack entry             |
| `stack_empty`    | output    |      1 | High when stack pointer is zero                     |
| `stack_full`     | output    |      1 | High when stack pointer equals `STACK_DEPTH`        |
| `stack_overflow` | output    |      1 | High when `push` is asserted while stack is full    |

## Internal storage

```systemverilog
logic [31:0] stack_mem [STACK_DEPTH-1:0];
logic [$clog2(STACK_DEPTH+1)-1:0] sp;
```

Unlike `warp_stack`, the stack-pointer width is derived with `$clog2`
instead of hardcoded, so changing `STACK_DEPTH` does not require manually
resizing `sp`.

## Stack status signals

```systemverilog
assign stack_empty    = (sp == 0);
assign stack_full     = (sp == STACK_DEPTH);
assign stack_overflow = push && stack_full;
```

`stack_overflow` is not latched -- it is high only while `push` is high and
the stack is already full.

## Top entry read behavior

```systemverilog
assign top_return_pc = (sp > 0) ? stack_mem[sp-1] : 32'b0;
```

If the stack is empty, `top_return_pc` reads as `0`. This should never be
consumed by real hardware (an `SRET` should only ever execute after a
matching `CALL`), but it gives a deterministic, harmless value rather than
`X` if it ever is.

## Push behavior

```systemverilog
if (push && !stack_full) begin
    stack_mem[sp] <= push_return_pc;
    sp <= sp + 1;
end
```

Example:

```text
Before push:
  sp = 0, stack_empty = 1

Push:
  push_return_pc = 0x00000018

After push:
  sp = 1
  top_return_pc = 0x00000018
  stack_empty = 0
```

## Pop behavior

```systemverilog
if (pop && !stack_empty) begin
    sp <= sp - 1;
end
```

Stack memory contents are not cleared on pop, only ignored once `sp` moves
below them.

## Overflow behavior

If the stack is full and `push` is asserted, `stack_overflow = 1` and the
push is ignored (the write is gated by `!stack_full`). The current top
entry remains unchanged. Tested by filling the depth-2 stack, then
attempting a third push.

## Simultaneous push and pop behavior

Same shape as `warp_stack`: two independent `if` blocks both assign `sp`.
`decoder.sv`'s case statement is one-hot per opcode, so `call_en` and
`sret_en` can never both be `1` for the same instruction -- the real
integration never actually drives `push` and `pop` together. It is still
fully characterized here as a standalone-module robustness property, since a
future unrelated RTL change could otherwise silently create this condition
with no test to catch it.

The behavior is deterministic, not undefined: `push`'s `sp <= sp + 1` and
`pop`'s `sp <= sp - 1` are two non-blocking assignments to `sp` in the same
`always_ff`, evaluated in program order (`push` block first, `pop` block
second) from the same pre-edge `sp`. Since they target the same variable in
the same time step, the later one in program order -- `pop`'s -- is the one
that lands. `push`'s `stack_mem` write still happens (at the pre-edge `sp`
index), but becomes unreachable the instant `sp` shrinks, so it's never
observable; `sp` only ever grows by writing an index immediately before
reading it, so this "orphaned" write can never resurface as stale data.

The resulting rule: **pop wins whenever pop is legal (stack not empty);
push only takes effect when pop was illegal** (stack was empty, or `pop`
wasn't asserted at all). Concretely:

| Stack state | `push=1, pop=1` result                              |
| ----------- | ---------------------------------------------------- |
| empty       | pop is illegal -> push happens (net: push)            |
| partial     | pop is legal -> pop happens, push's write is orphaned |
| full        | pop is legal -> pop happens, `stack_overflow` stays 0 |

Verified by `test_simultaneous_push_pop_when_{partial,full,empty}_*`,
`test_orphaned_write_not_observable_after_simultaneous_pop`, and fuzzed
against a matching reference model (`model_step()` in `tests/common.py`) by
`test_random_simultaneous_push_pop_against_model`.

## Reset behavior

```systemverilog
if (rst) begin
    sp <= 0;
end
```

Asynchronous reset (`always_ff @(posedge clk or posedge rst)`), makes the
stack empty. Stack memory is not cleared, only ignored while `sp == 0`.

## Verification

Unit test files:

```text
Src/call_stack/tests/test_call_stack_directed.py
Src/call_stack/tests/test_call_stack_random.py
```

Run with:

```text
cd Src/call_stack
source ~/cocotb-env/bin/activate
make
```

## Current tests

| Test                                              | What it checks                                                          |
| -------------------------------------------------- | ------------------------------------------------------------------------ |
| `test_reset_defaults`                             | Reset produces an empty stack, `top_return_pc = 0`                       |
| `test_single_push_updates_top`                    | Push stores `push_return_pc`, stack becomes non-empty                    |
| `test_single_pop_returns_empty`                   | Pop after one push returns the stack to empty                           |
| `test_pop_empty_does_not_underflow`               | Pop on an already-empty stack is a no-op                                 |
| `test_call_return_pair`                           | The actual CALL/SRET usage shape: one push immediately followed by one pop |
| `test_lifo_order_two_entries`                     | Two pushes fill the default depth-2 stack; pops return LIFO order        |
| `test_full_after_depth_pushes`                    | Filling to `STACK_DEPTH` asserts `stack_full`                            |
| `test_overflow_combinational_when_push_full`      | Extra push while full asserts `stack_overflow`, does not overwrite top   |
| `test_overflow_clears_when_push_deasserted`       | `stack_overflow` clears combinationally once `push` deasserts            |
| `test_reset_after_pushes_clears_stack_pointer`    | Reset mid-sequence returns to empty regardless of prior pushes           |
| `test_push_after_empty_pop_works`                 | A no-op pop on empty doesn't corrupt subsequent pushes                   |
| `test_random_push_pop_sequence_against_model` (random) | 200-step randomized push/pop sequence checked against a Python LIFO model |
| `test_random_overflow_attempts_do_not_change_stack` (random) | Repeated overflow pushes never mutate stack contents            |
| `test_random_pop_empty_does_not_change_outputs` (random) | Repeated empty pops stay inert                                    |
| `test_random_reset_mid_sequence` (random)         | Reset at random points always clears the model-tracked stack             |
| `test_random_fill_and_drain_lifo` (random)        | 50 trials of fill-to-full then drain-to-empty, checked against the model |
| `test_simultaneous_push_pop_when_partial_pop_wins`               | Both asserted with one entry present: pop wins, stack empties            |
| `test_simultaneous_push_pop_when_full_pop_wins`                  | Both asserted while full: pop wins, `stack_overflow` stays 0             |
| `test_simultaneous_push_pop_when_empty_push_wins`                | Both asserted while empty: pop is illegal, push wins                     |
| `test_orphaned_write_not_observable_after_simultaneous_pop`      | Orphaned `stack_mem` write from a "pop wins" case never resurfaces       |
| `test_overflow_deasserts_immediately_when_pop_makes_room_while_push_held` | `stack_overflow` clears the instant a pop makes room, even with `push` still held |
| `test_push_return_pc_glitch_does_not_affect_stored_entry`        | Toggling `push_return_pc` while `push=0` never leaks into the stored entry |
| `test_async_reset_without_clock_edge`                            | `rst` takes effect without waiting for a `RisingEdge(clk)` (true async reset) |
| `test_full_boundary_repeated_blocked_pushes_preserve_top`        | Repeated blocked pushes while full leave the top entry untouched         |
| `test_reset_dominates_simultaneous_push_pop`                     | `rst` asserted alongside `push`+`pop` always wins                        |
| `test_random_simultaneous_push_pop_against_model` (random)       | 300-step fuzz of independent push/pop (incl. both together) against `model_step()`, plus pre-edge combinational overflow check every step |

All 26 tests pass under Icarus Verilog via cocotb.

## Known pitfalls

`push` and `pop` asserted in the same cycle is deterministic, not undefined
-- see "Simultaneous push and pop behavior" above for the exact rule
(pop wins whenever legal). Unreachable from real compiled axelcc programs,
but characterized and tested anyway since the RTL doesn't structurally
prevent it.

Do not assume stack memory clears on reset -- only `sp` resets.

`STACK_DEPTH` below `1` is nonsensical (`sp` width would be zero bits) and
below what a correctly-compiled axelcc program needs is a real regression;
`sema.c`'s no-nested-call rule is what makes depth `1` provably sufficient,
so don't remove that compiler-side restriction without revisiting this
module's depth.

## Design summary

`call_stack` is a small LIFO for subroutine return addresses. It stores one
32-bit PC per outstanding `CALL`.

The most important behavior is:

```text
push -> store return_pc (the address right after a CALL)
pop  -> restore it, so SRET can jump back there
```

It is fully wired into `core.sv` / `pc.sv` / `decoder.sv` and verified both
as a standalone module (26 directed + random tests, including full
simultaneous-push/pop characterization) and end-to-end on real RTL via a
compiled `CALL`/`SRET` program (`test_axelcc_func_basic.py`).
