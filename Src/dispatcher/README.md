# Dispatcher

## Overview

`dispatcher` assigns work blocks to available GPU cores.

It receives the kernel launch configuration from the Device Control Register (`dcr`), watches which cores are busy or done, assigns block indices to free cores, and asserts `kernel_done` when all blocks have been assigned and all active cores have completed.

The dispatcher currently assigns at most one new block per clock cycle.

## RTL schematic

![Dispatcher RTL schematic](../../assets/Images-Components/Dispatcher-page-00001.jpg)

## Source files

```text
Src/dispatcher/dispatcher.sv
Src/dispatcher/test_dispatcher.py
```

## Position in the GPU

The dispatcher sits between the DCR launch-control block and the GPU cores.

```text
DCR
 │
 │ num_blocks, blockDim, start/dispatch_en
 ▼
dispatcher
 │
 ├── core_start[i]
 ├── blockIdx_out[i]
 └── kernel_done
      │
      ▼
core_gen[i].core_inst
```

In the full top-level flow:

```text
host/testbench
      │
      ▼
DCR writes
      │
      ▼
dcr
      │
      ▼
dispatcher
      │
      ▼
cores
      │
      ▼
kernel_done
```

## Module declaration

```systemverilog
module dispatcher #(
    parameter NUM_CORES = 4,
    parameter THREADS_PER_CORE = 4
) (
    input logic clk,
    input logic rst,

    input logic [31:0] num_blocks,
    input logic [31:0] blockDim,
    input logic dispatch_en,
    input logic [NUM_CORES-1:0] block_done,

    output logic [NUM_CORES-1:0] core_start,
    output logic [NUM_CORES-1:0][31:0] blockIdx_out,
    output logic kernel_done
);
```

## Parameters

| Parameter          | Default | Description                                                                                                |
| ------------------ | ------: | ---------------------------------------------------------------------------------------------------------- |
| `NUM_CORES`        |     `4` | Number of cores that can receive blocks                                                                    |
| `THREADS_PER_CORE` |     `4` | Number of threads per core. Present for consistency, but not directly used in the current dispatcher logic |

## Port description

| Port           | Direction |                   Width | Description                                                                                              |
| -------------- | --------- | ----------------------: | -------------------------------------------------------------------------------------------------------- |
| `clk`          | input     |                       1 | Clock                                                                                                    |
| `rst`          | input     |                       1 | Reset                                                                                                    |
| `num_blocks`   | input     |                      32 | Total number of blocks in the launched kernel                                                            |
| `blockDim`     | input     |                      32 | Threads per block. Passed into the system configuration but not directly used by this dispatcher version |
| `dispatch_en`  | input     |                       1 | Launch/dispatch enable from DCR start pulse                                                              |
| `block_done`   | input     |             `NUM_CORES` | Per-core completion signal                                                                               |
| `core_start`   | output    |             `NUM_CORES` | Per-core active/start flag                                                                               |
| `blockIdx_out` | output    | `[NUM_CORES-1:0][31:0]` | Packed per-core block index assignment                                                                   |
| `kernel_done`  | output    |                       1 | Indicates all blocks have been assigned and completed                                                    |

## Main behavior

The dispatcher tracks:

```text
next_block    -> next block index to assign
active_blocks -> number of currently active blocks
core_start[i] -> whether core i is currently assigned/running
blockIdx_out[i] -> block index assigned to core i
kernel_done   -> full kernel completion flag
```

The dispatcher assigns blocks while:

```text
dispatch_en == 1
next_block < num_blocks
a free core exists
```

A core is considered free when:

```text
core_start[i] == 0
block_done[i] == 0
```

When a core finishes, it raises `block_done[i]`. The dispatcher clears `core_start[i]` and decrements the active block count.

## Internal state

| Signal          | Description                                                      |
| --------------- | ---------------------------------------------------------------- |
| `next_block`    | Next block index that should be assigned                         |
| `active_blocks` | Number of blocks currently assigned and not yet completed        |
| `assigned`      | Temporary flag used to limit dispatch to one new block per cycle |
| `done_count`    | Temporary count of cores completed in the current cycle          |
| `delta`         | Signed temporary update applied to `active_blocks`               |

## Reset behavior

On reset:

```text
next_block    -> 0
active_blocks -> 0
kernel_done   -> 0
core_start[i] -> 0 for every core
blockIdx_out[i] -> 0 for every core
```

Reset is asynchronous because the sensitivity list is:

```systemverilog
always_ff @(posedge clk or posedge rst)
```

## Dispatch sequence

A normal launch sequence is:

```text
1. DCR writes num_blocks.
2. DCR writes blockDim.
3. DCR emits start pulse.
4. Top-level connects start to dispatcher dispatch_en.
5. Dispatcher assigns block indices to available cores.
6. Cores execute assigned blocks.
7. Cores pulse block_done.
8. Dispatcher clears completed cores and assigns more blocks if needed.
9. Dispatcher asserts kernel_done when all blocks are complete.
```

## Block assignment behavior

When `dispatch_en` is high, the dispatcher scans cores from low index to high index:

```systemverilog
for (int i = 0; i < NUM_CORES; i++) begin
    if (!assigned && core_start[i] == 0 && block_done[i] == 0 && next_block < num_blocks) begin
        core_start[i] <= 1;
        blockIdx_out[i] <= next_block;
        next_block <= next_block + 1;
        delta = delta + 1;
        assigned = 1;
    end
end
```

Because `assigned` is set after the first assignment, this dispatcher assigns only one block per cycle.

Example for `NUM_CORES = 4` and `num_blocks = 4`:

```text
cycle 1 -> core 0 gets block 0
cycle 2 -> core 1 gets block 1
cycle 3 -> core 2 gets block 2
cycle 4 -> core 3 gets block 3
```

## `core_start` behavior

`core_start[i]` acts as both a start indication and an active/busy flag in this dispatcher version.

When a block is assigned:

```systemverilog
core_start[i] <= 1;
```

When that core reports completion:

```systemverilog
if (block_done[i]) begin
    core_start[i] <= 0;
end
```

So `core_start[i]` remains high while the core is considered active.

## Block completion behavior

The dispatcher checks every `block_done[i]` bit each clock cycle:

```systemverilog
for (int i = 0; i < NUM_CORES; i++) begin
    if (block_done[i]) begin
        core_start[i] <= 0;
        done_count = done_count + 1;
        delta = delta - 1;
    end
end
```

When a core completes:

```text
core_start[i] is cleared
active block count is decremented through delta
```

The current code has `done_count`, but it is not used outside this loop. It is informational/redundant in the current implementation.

## Active block tracking

The dispatcher uses a signed temporary `delta` to update `active_blocks`.

```systemverilog
active_blocks <= active_blocks + delta;
```

`delta` is adjusted during the cycle:

```text
+1 for each new assignment
-1 for each completed block
```

Since this dispatcher only assigns one new block per cycle, `delta` can be:

```text
+1  -> one block assigned, none completed
 0  -> no net change, or one completed and one assigned
-1  -> one block completed, none assigned
...
```

If multiple cores finish in the same cycle, `delta` can be less than `-1`.

## Kernel completion

`kernel_done` is asserted when:

```systemverilog
if (next_block == num_blocks && (active_blocks + delta) == 0 && num_blocks > 0) begin
    kernel_done <= 1;
end
```

This means:

```text
all blocks have been assigned
no blocks remain active
num_blocks is nonzero
```

`kernel_done` is sticky in the current implementation. Once set to `1`, it remains high until reset.

## Packed `blockIdx_out`

`blockIdx_out` is packed:

```systemverilog
output logic [NUM_CORES-1:0][31:0] blockIdx_out
```

Each core receives:

```systemverilog
blockIdx_out[i]
```

In cocotb, the testbench reads the full packed value and extracts the 32-bit lane manually:

```python
def get_block_idx(dut, core_id):
    packed = int(dut.blockIdx_out.value)
    return (packed >> (core_id * 32)) & 0xFFFFFFFF
```

This mirrors the packed response-data handling used elsewhere in the project.

## Current RTL implementation

```systemverilog
logic [31:0] next_block;
logic [31:0] active_blocks;
logic assigned;
logic [31:0] done_count;
logic signed [31:0] delta;

always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        next_block <= 0;
        active_blocks <= 0;
        kernel_done <= 0;
        for (int i = 0; i < NUM_CORES; i++) begin
            core_start[i] <= 0;
            blockIdx_out[i] <= 0;
        end
    end else begin
        done_count = 0;
        delta = 0;

        for (int i = 0; i < NUM_CORES; i++) begin
            if (block_done[i]) begin
                core_start[i] <= 0;
                done_count = done_count + 1;
                delta = delta - 1;
            end
        end
        
        if (dispatch_en) begin
            assigned = 0;
            for (int i = 0; i < NUM_CORES; i++) begin
                if (!assigned && core_start[i] == 0 && block_done[i] == 0 && next_block < num_blocks) begin
                    core_start[i] <= 1;
                    blockIdx_out[i] <= next_block;
                    next_block <= next_block + 1;
                    delta = delta + 1;
                    assigned = 1;
                end
            end
        end

        active_blocks <= active_blocks + delta;

        if (next_block == num_blocks && (active_blocks + delta) == 0 && num_blocks > 0) begin
            kernel_done <= 1;
        end
    end
end
```

## Timing assumptions

The dispatcher assumes:

```text
- num_blocks is configured before dispatch_en is asserted.
- blockDim is configured before dispatch_en is asserted.
- dispatch_en remains high while the dispatcher is allowed to assign blocks.
- block_done[i] is asserted by core i when its assigned block is complete.
- core_start[i] can remain high while a core is active.
- kernel_done is cleared only by reset.
```

## Important implementation notes

## One block per clock

This dispatcher intentionally assigns at most one new block each clock cycle because of the `assigned` temporary flag.

This behavior is visible in the tests:

```python
for _ in range(4):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
```

For four blocks and four cores, the test waits four cycles before expecting all cores to be started.

## Same-cycle completion and reassignment

If `block_done[i]` is high, that core is not reassigned in the same cycle because the dispatch condition checks:

```systemverilog
block_done[i] == 0
```

So a core that completes in one cycle can receive a new block only after `block_done[i]` is deasserted and another dispatch cycle occurs.

## `kernel_done` is sticky

The dispatcher does not clear `kernel_done` when a new launch starts. It is only cleared by reset.

If future design supports launching multiple kernels without reset, this behavior must be changed.

## `blockDim` is unused here

`blockDim` is an input to the dispatcher but is not used in the current RTL. It is passed through the broader top-level launch configuration and used by the core/register-file side, but this dispatcher only needs `num_blocks` and `block_done` to assign block indices.

## Unit test

Unit test file:

```text
Src/dispatcher/test_dispatcher.py
```

## Current tests

| Test                                  | What it checks                                                             |
| ------------------------------------- | -------------------------------------------------------------------------- |
| `test_single_block`                   | One block is assigned to core 0 and `kernel_done` asserts after completion |
| `test_multiple_blocks_multiple_cores` | Four blocks are assigned to four cores over four cycles                    |
| `test_more_blocks_than_cores`         | More blocks than cores are assigned as cores finish                        |

## `test_single_block`

Configuration:

```text
num_blocks = 1
dispatch_en = 1
```

Expected behavior:

```text
core 0 starts
blockIdx_out[0] = 0
core 0 completes
kernel_done = 1
```

## `test_multiple_blocks_multiple_cores`

Configuration:

```text
num_blocks = 4
dispatch_en = 1
NUM_CORES = 4
```

Expected behavior after four cycles:

```text
core_start = 4'b1111
blockIdx_out[0] = 0
blockIdx_out[1] = 1
blockIdx_out[2] = 2
blockIdx_out[3] = 3
```

After all cores report done:

```text
kernel_done = 1
```

## `test_more_blocks_than_cores`

Configuration:

```text
num_blocks = 6
dispatch_en = 1
NUM_CORES = 4
```

Expected behavior:

```text
first wave:
  core 0 -> block 0
  core 1 -> block 1
  core 2 -> block 2
  core 3 -> block 3

after core 0 completes:
  core 0 -> block 4

after core 1 completes:
  core 1 -> block 5

after all active cores complete:
  kernel_done = 1
```

## Verification notes

The tests use this helper for packed `blockIdx_out`:

```python
def get_block_idx(dut, core_id):
    packed = int(dut.blockIdx_out.value)
    return (packed >> (core_id * 32)) & 0xFFFFFFFF
```

This is required because `blockIdx_out` is packed.

## Recommended additional tests

| Test                                        | Purpose                                                                                            |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `test_reset_clears_dispatcher`              | Verify reset clears `next_block`, `active_blocks`, `core_start`, `blockIdx_out`, and `kernel_done` |
| `test_zero_blocks_no_done`                  | Verify `num_blocks = 0` does not assert `kernel_done` unexpectedly                                 |
| `test_dispatch_en_low_no_assignment`        | Verify no blocks are assigned when `dispatch_en = 0`                                               |
| `test_kernel_done_sticky`                   | Verify `kernel_done` remains high until reset                                                      |
| `test_no_same_cycle_reassign_on_block_done` | Verify a finishing core is not reassigned while `block_done[i]` is still high                      |
| `test_staggered_core_completion`            | Verify block reassignment when cores finish at different times                                     |
| `test_more_than_one_core_done_same_cycle`   | Verify `active_blocks` updates correctly when multiple cores finish in one cycle                   |
| `test_many_blocks`                          | Verify block indices continue correctly beyond one full core wave                                  |

## Known pitfalls

Do not assume `core_start` is only a one-cycle pulse. In this dispatcher, it stays high while the core is active.

Do not expect all free cores to receive blocks in one cycle. The dispatcher assigns only one block per clock.

Do not change `blockIdx_out` from packed to unpacked without updating cocotb tests and top-level wiring.

Do not forget that `kernel_done` is sticky until reset.

Do not launch a new kernel without reset unless the dispatcher is later modified to clear `kernel_done`, `next_block`, and `active_blocks` on a new launch.

Be careful with blocking temporaries inside the sequential block:

```systemverilog
done_count = 0;
delta = 0;
assigned = 0;
```

They are used as temporary calculations inside the clocked process. If the dispatcher logic becomes more complex, consider moving next-state calculations to a separate `always_comb` block and keeping only registered updates in `always_ff`.

## Related integration tests

| Test                    | File                                      | What it proves                                             |
| ----------------------- | ----------------------------------------- | ---------------------------------------------------------- |
| `test_gpu_axel_program` | `Src/Top_level_GPU/test_top_level_gpu.py` | DCR and dispatcher can launch a full top-level GPU program |
| `test_simt_relu`        | `Src/Top_level_GPU/test_top_level_gpu.py` | Dispatcher can launch the SIMT ReLU kernel                 |
| `test_core_basic`       | `Src/core/test_core.py`                   | A dispatched core can execute and report completion        |

## Last known status

```text
Status: passing

Verified with:
  cd ~/gpu-project
  make test

Current unit coverage:
  single block
  multiple blocks across multiple cores
  more blocks than cores
```

## Design summary

`dispatcher` is the kernel block-assignment controller. It receives `num_blocks` and `dispatch_en`, assigns block indices to available cores, tracks the number of active blocks, clears cores when `block_done` arrives, and asserts `kernel_done` after all blocks are assigned and completed.

The most important current behavior is:

```text
one new block assignment per clock
core_start remains high while the core is active
blockIdx_out is packed
kernel_done is sticky until reset
```
