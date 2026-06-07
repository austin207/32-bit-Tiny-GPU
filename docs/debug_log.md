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

## LDR base register constraint in multi-thread SIMT mode

### Observed constraint

In multi-thread SIMT mode (blockDim > 1), using a general-purpose register
(R0-R28) as the base address in an LDR instruction produces incorrect memory
addresses. The effective address behaves as if THREAD_IDX was used instead.

Example that fails:

```c
axel_const(&gpu, R6, 4);           // R6 = 4
axel_ldr  (&gpu, R2, R6, 0);       // expected: mem[4], actual: mem[THREAD_IDX]
```

Example that works reliably:

```c
axel_ldr(&gpu, R2, THREAD_IDX, 4); // mem[THREAD_IDX + 4]  -- always correct
```

### Scope

Single-thread kernels (blockDim=1) are not affected. All three of R29
(THREAD_IDX), R30 (BLOCK_IDX), and R31 (BLOCK_DIM) work correctly as LDR
base registers in all configurations.

### Root cause status

Unresolved. The register file read ports, decoder field extraction, and core
wiring all appear correct in static analysis. The fault does not manifest in
single-thread mode and was not reproduced in isolation. The stale lsu_done_latch
bug (above) was fixed first, but the GP-register LDR constraint persists
after that fix. Needs further investigation with waveform capture on a minimal
reproducer (two consecutive LDRs, second using a CONST-written base).

### Workaround

Structure data memory so all parallel loads use THREAD_IDX-relative addressing.
For broadcast data (same value all threads need), replicate it N times so
thread i loads via `THREAD_IDX + offset`:

```c
// x replicated at mem[4..7] so all threads load via THREAD_IDX + 4
axel_set_data(&gpu, 4, x_packed);
axel_set_data(&gpu, 5, x_packed);
axel_set_data(&gpu, 6, x_packed);
axel_set_data(&gpu, 7, x_packed);

axel_ldr(&gpu, R2, THREAD_IDX, 4);  // mem[THREAD_IDX + 4] = x for all threads
```

This wastes N-1 data words but is reliable across all tested configurations.

### ISA constraint to enforce in assembler and documentation

```text
In multi-thread SIMT kernels (blockDim > 1):
  LDR/STR base register MUST be R29 (THREAD_IDX), R30 (BLOCK_IDX), or R31 (BLOCK_DIM).
  Using R0-R28 as LDR/STR base addresses is not supported in this configuration.
```

### Files involved

```text
Src/core/core.sv             (likely location of fault)
Src/registers/register_file.sv
assembler/examples/phase8_mlp_inference.c  (workaround applied here)
Src/Top_level_GPU/test_top_level_gpu.py
```