---

## Back-to-back LDR stale LSU latch bug

### Context

Phase 8 added the first multi-instruction kernel that issues two consecutive
LDR instructions:

```text
Instruction 0: LDR R1, THREAD_IDX, 0   load W_row_i
Instruction 1: LDR R2, THREAD_IDX, 4   load x
Instruction 2: DOT4 R3, R1, R2
...
```

### Symptom

```text
y[0] = 95   expected 20
y[1] = 95   expected 48
y[2] = 127  expected 25
y[3] = 127  expected 8
```

These values exactly matched `CLAMP(SAR(DOT4(W_row_i, W_row_i), 8))`, not
`CLAMP(SAR(DOT4(W_row_i, x), 8))`. Both operands to DOT4 were W_row_i,
meaning R2 = R1 = W_row_i instead of R2 = x.

Cocotb debug confirmed correct memory addresses for both LDR instructions.
Both loads accessed the correct physical addresses. The memory model returned
the correct data. The fault was in register writeback, not memory access.

### Root cause

The `lsu_done_latch` in `Src/core/core.sv` was cleared only when `lsu_en`
was asserted (when the scheduler launches a new memory request). For
back-to-back LDRs, this is too late.

Timeline:

```text
Cycle N:    LDR R1 completes. lsu_done_latch = all 1s.
Cycle N+k:  Scheduler fetches LDR R2. lsu_en fires. lsu_done_latch cleared.
Cycle N+k+1: Scheduler enters WAIT.
             BUT: lsu_done_latch is checked before lsu_en clears it,
             so all_done = 1 on the very first cycle in WAIT.
             Scheduler exits WAIT immediately with stale lsu_read_data.
```

The second LDR left the WAIT state before the memory response arrived,
using lsu_read_data still holding W_row_i from the first LDR.

### Fix

In `Src/core/core.sv`, the latch clear logic was changed to detect
a newly fetched LDR or STR instruction and clear stale completion bits
before the scheduler reaches WAIT:

```systemverilog
always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        lsu_done_latch <= '0;
    end else begin
        if (done && ((instruction_raw[31:26] == 6'h0F) ||
                     (instruction_raw[31:26] == 6'h10))) begin
            // New LDR/STR detected at fetch: clear stale bits immediately.
            lsu_done_latch <= '0;
        end else if (lsu_en) begin
            // Memory request launch: also clear defensively.
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

The key is `done && instruction_raw[31:26] == LDR/STR opcode`. When the
fetcher signals done and the incoming instruction is a memory op, the latch
is cleared one full scheduler state ahead of when lsu_en fires.

### Files changed

```text
Src/core/core.sv
```

### Verification

```text
Phase 8 Q8 MLP inference: PASS
  mem[8]  = 20
  mem[9]  = 48
  mem[10] = 25
  mem[11] = 8

kernel_cycles = 103
Full suite: all tests passing
```

### Debug instrumentation used

A temporary `[COREDBG]` block was added to `test_mlp_inference` to read
`reg_data1`, `reg_data2`, and ALU output directly before DOT4 execution.
Before the fix it showed `reg_data2 = W_row_i`. After the fix it showed
`reg_data2 = 0x117f2a55` (x).

The debug block was removed before the final commit.

### Lesson

For multi-cycle pipeline stages, clearing latched state on the NEXT instruction
fetch is not always safe. The stale state must be cleared at the EARLIEST
possible detection point — in this case, when the fetcher reports a new
LDR/STR opcode, not when the scheduler fires lsu_en.

---

## LDR base register constraint — RESOLVED (confirmed stale)

### Original claim

Earlier documentation stated that in multi-thread SIMT mode (blockDim > 1),
LDR/STR base registers must be R29/R30/R31. Using R0-R28 as base was
described as producing incorrect addresses.

### Resolution

The constraint was a misdiagnosis. The symptoms were caused entirely by the
stale lsu_done_latch bug documented above. After that fix, general-purpose
register bases work correctly in all configurations.

Verified by test_ldr_regbase_broadcast in test_top_level_gpu.py:

```text
Config  : 1 block, 4 threads (blockDim = 4)
Kernel  : CONST R6=4 | LDR R1, R6, 0 | STR R1, THREAD_IDX, 8 | RET
Pre-load: mem[4] = 0x12345678

Result:
  thread 0 | mem[8]  = 0x12345678  PASS
  thread 1 | mem[9]  = 0x12345678  PASS
  thread 2 | mem[10] = 0x12345678  PASS
  thread 3 | mem[11] = 0x12345678  PASS

kernel_cycles = 55
```

All 4 threads loaded from the same address via R6 base. Round-robin
memory controller serialized the 4 requests correctly. lsu_done_latch
accumulated all 4 completions before scheduler exited WAIT.

### Files updated

```text
assembler/examples/phase8_mlp_inference.c   (stale constraint comment removed)
docs/debug_log.md                           (this entry)
Src/Top_level_GPU/test_top_level_gpu.py     (two new tests added)
assembler/examples/phase9_ldr_regbase_single.c
assembler/examples/phase9_ldr_regbase_broadcast.c
```

### ISA constraint status

No LDR/STR base register restriction exists. R0-R31 all valid as base
in single-thread and multi-thread SIMT configurations.