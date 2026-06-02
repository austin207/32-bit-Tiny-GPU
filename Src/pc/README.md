# PC

## Overview

`pc` is the per-thread program counter and NZP flag storage block.

Each thread lane inside a core has its own PC instance. The PC tracks the current instruction address for that thread, stores the most recent NZP comparison flag, increments normally, and applies branch offsets when a branch condition is satisfied.

The PC is sequential logic. It updates on the rising edge of `clk` and supports asynchronous reset through `rst`.

## RTL schematic

![PC RTL schematic](../../assets/Images-Components/PC-page-00001.jpg)

## Source files

```text
Src/pc/pc.sv
Src/pc/test_pc.py
```

## Position in the GPU

The PC sits inside each thread lane of the core.

```text
ALU CMP result
      │
      │ nzp_flag
      ▼
     pc
      │
      ├── pc_out  -> active_pc selection -> fetcher
      └── nzp_out -> branch/divergence decision logic
```

Inside `core.sv`, each thread lane has its own `pc_inst`:

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

## Module declaration

```systemverilog
(* syn_dont_touch = 1 *) module pc (
    input logic clk,
    input logic rst,
    input logic block_rst,
    input logic pc_en,
    input logic branch_en,
    input logic [11:0] branch_offset,
    input logic nzp_en,
    input logic [2:0] nzp_flag,
    input logic [2:0] nzp_mask,
    output logic [31:0] pc_out,
    output logic [2:0] nzp_out
);
```

## Port description

| Port            | Direction | Width | Description                                     |
| --------------- | --------- | ----: | ----------------------------------------------- |
| `clk`           | input     |     1 | Clock                                           |
| `rst`           | input     |     1 | Global reset                                    |
| `block_rst`     | input     |     1 | Per-block PC reset used when a new block starts |
| `pc_en`         | input     |     1 | Enables PC update                               |
| `branch_en`     | input     |     1 | Indicates current instruction is a branch       |
| `branch_offset` | input     |    12 | Offset added to PC when branch is taken         |
| `nzp_en`        | input     |     1 | Enables storing a new NZP flag                  |
| `nzp_flag`      | input     |     3 | New NZP flag from ALU CMP                       |
| `nzp_mask`      | input     |     3 | Branch mask from BRNZP instruction              |
| `pc_out`        | output    |    32 | Current program counter value                   |
| `nzp_out`       | output    |     3 | Stored NZP flag                                 |

## NZP flag encoding

The PC stores NZP flags produced by the ALU CMP instruction.

The project uses this encoding:

```text
N = 3'b100
Z = 3'b010
P = 3'b001
```

This matches the assembler constants:

```c
#define AXEL_N   0b100
#define AXEL_Z   0b010
#define AXEL_P   0b001
#define AXEL_NZ  0b110
#define AXEL_NP  0b101
#define AXEL_ZP  0b011
#define AXEL_ALL 0b111
```

## Internal state

| Signal    | Description                                 |
| --------- | ------------------------------------------- |
| `pc_out`  | Current instruction address for this thread |
| `nzp_reg` | Stored NZP flag from the most recent CMP    |
| `nzp_out` | Continuous assignment exposing `nzp_reg`    |

The internal NZP register is:

```systemverilog
logic [2:0] nzp_reg;
```

The output is assigned directly:

```systemverilog
assign nzp_out = nzp_reg;
```

## Reset behavior

The PC has two reset paths.

## Global reset

When `rst` is asserted:

```systemverilog
pc_out  <= 32'b0;
nzp_reg <= 3'b000;
```

This clears both the program counter and stored NZP flag.

Reset is asynchronous because the sequential block uses:

```systemverilog
always_ff @(posedge clk or posedge rst)
```

## Block reset

When `block_rst` is asserted:

```systemverilog
pc_out  <= 32'b0;
nzp_reg <= 3'b000;
```

`block_rst` is used when a core starts a new block. It prevents a core from starting block `N+1` at the old PC left behind by block `N`.

In `core.sv`, it is generated as:

```systemverilog
assign pc_block_rst = (current_state == 4'b0000) && core_start;
```

This means:

```text
scheduler is IDLE and core_start is asserted -> reset thread PCs to 0
```

## PC update behavior

When not in reset, the PC can perform two independent actions:

1. Store NZP flag when nzp_en is high.
2. Update PC when pc_en is high.

Current implementation:

```systemverilog
if (nzp_en)
    nzp_reg <= nzp_flag;

if (pc_en) begin
    if (branch_en && (nzp_reg & nzp_mask) != 0)
        pc_out <= pc_out + branch_offset;
    else
        pc_out <= pc_out + 1;
end
```

## Normal increment

If `pc_en = 1` and the branch condition is not taken:

```systemverilog
pc_out <= pc_out + 1;
```

Example:

```text
pc_out = 0
pc_en = 1
branch_en = 0

next pc_out = 1
```

## Branch behavior

A branch is taken only when:

```systemverilog
branch_en && (nzp_reg & nzp_mask) != 0
```

If taken:

```systemverilog
pc_out <= pc_out + branch_offset;
```

If not taken:

```systemverilog
pc_out <= pc_out + 1;
```

## Branch examples

### Positive branch taken

Stored NZP:

```text
nzp_reg = 3'b001
```

Branch mask:

```text
nzp_mask = 3'b001
```

Condition:

```text
nzp_reg & nzp_mask = 3'b001
```

Branch is taken.

### Negative branch not taken

Stored NZP:

```text
nzp_reg = 3'b001
```

Branch mask:

```text
nzp_mask = 3'b100
```

Condition:

```text
nzp_reg & nzp_mask = 3'b000
```

Branch is not taken, so PC increments by one.

## CMP and branch timing

CMP and BR are separate instructions.

CMP stores NZP:

```text
CMP instruction
    -> ALU generates nzp_flag
    -> pc.nzp_en = 1
    -> pc stores nzp_reg
```

BR uses previously stored NZP:

```text
BRNZP instruction
    -> branch_en = 1
    -> nzp_mask from instruction
    -> pc checks nzp_reg & nzp_mask
```

Important: the branch decision uses the already-stored `nzp_reg`, not the new `nzp_flag` being written in the same cycle.

## Current RTL implementation

```systemverilog
logic [2:0] nzp_reg;

always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        pc_out  <= 32'b0;
        nzp_reg <= 3'b000;
    end else if (block_rst) begin
        pc_out  <= 32'b0;
        nzp_reg <= 3'b000;
    end else begin
        if (nzp_en)
            nzp_reg <= nzp_flag;

        if (pc_en) begin
            if (branch_en && (nzp_reg & nzp_mask) != 0)
                pc_out <= pc_out + branch_offset;
            else
                pc_out <= pc_out + 1;
        end
    end
end

assign nzp_out = nzp_reg;
```

## Interaction with active mask

The PC does not directly receive `active_mask`.

Instead, the core gates `pc_en` before connecting it:

```systemverilog
.pc_en(pc_en & active_mask[i])
```

So inactive SIMT lanes do not advance their PC.

This is essential for divergence handling because taken and not-taken paths must execute under different active masks.

## Interaction with fetcher

Each thread has its own `pc_out`.

The core chooses one active thread’s PC as `active_pc`:

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

The fetcher uses:

```systemverilog
.pc_value(active_pc)
```

This means the core fetches one instruction stream for the currently active set of threads.

## Interaction with SIMT divergence

During branch instructions, the PC contributes to divergence behavior in two ways:

1. Each thread uses its stored nzp_reg to decide whether it takes the branch.
2. Each active thread updates its own pc_out based on the branch decision.

The core separately computes `taken_mask` using `nzp_stored[i]`:

```systemverilog
taken_mask[i] =
    branch_en &&
    active_mask[i] &&
    ((nzp_stored[i] & nzp_mask) != 3'b000);
```

If only some active threads take the branch, the core enters divergence handling and uses the warp stack to save the non-active path.

## SIMT ReLU example

The SIMT ReLU program uses CMP and BR:

```text
PC0: LDR   R1, THREAD_IDX, 0
PC1: CMP   R1, R0
PC2: BR P, sync_offset=2, branch_offset=2
PC3: CONST R1, 0
PC4: SYNC
PC5: STR   R1, THREAD_IDX, 4
PC6: RET
```

After CMP:

```text
T0: R1 =  5 -> nzp_reg = 3'b001
T1: R1 = -3 -> nzp_reg = 3'b100
T2: R1 =  8 -> nzp_reg = 3'b001
T3: R1 = -1 -> nzp_reg = 3'b100
```

For `BR P`:

```text
nzp_mask = 3'b001
```

Taken threads:

```text
T0 and T2
```

Not-taken threads:

```text
T1 and T3
```

This produces divergence:

```text
taken_mask = 4'b0101
```

## Timing assumptions

The PC assumes:

- `pc_en` is asserted only when the scheduler wants the PC to update.
- `branch_en`, `branch_offset`, and `nzp_mask` are stable when `pc_en` is asserted.
- `nzp_flag` is stable when `nzp_en` is asserted.
- CMP and BR are separate instructions.
- Branch logic uses the stored NZP flag from a previous CMP.
- `block_rst` is asserted at the start of a new block before normal instruction fetch continues.

## Unit test

Unit test file:

```text
Src/pc/test_pc.py
```

## Current tests

| Test                    | What it checks                                                   |
| ----------------------- | ---------------------------------------------------------------- |
| `test_reset`            | Reset clears PC to zero                                          |
| `test_increment`        | PC increments when `pc_en` is asserted                           |
| `test_nzp_store`        | NZP flag stores without changing PC, then branch uses stored NZP |
| `test_branch_taken`     | Branch offset is applied when NZP mask matches                   |
| `test_branch_not_taken` | PC increments normally when NZP mask does not match              |

## `test_reset`

Checks:

```text
rst = 1 -> pc_out = 0
```

## `test_increment`

Stimulus:

```text
pc_en = 1
branch_en = 0
```

Expected sequence:

```text
pc_out = 1
pc_out = 2
pc_out = 3
```

## `test_nzp_store`

Checks that NZP can be stored without updating PC.

Sequence:

1. Increment PC to 1.
2. Set nzp_en = 1 and nzp_flag = 3'b001.
3. Keep pc_en = 0.
4. Confirm PC remains 1.
5. Branch on P with offset 5.
6. Confirm PC becomes 6.

## `test_branch_taken`

Stores positive NZP:

```text
nzp_flag = 3'b001
```

Then branches with:

```text
nzp_mask = 3'b001
branch_offset = 5
```

Expected:

```text
pc_out = 1 + 5 = 6
```

## `test_branch_not_taken`

Stores positive NZP:

```text
nzp_flag = 3'b001
```

Then branches with negative mask:

```text
nzp_mask = 3'b100
branch_offset = 5
```

Since the mask does not match, expected result is normal increment:

```text
pc_out = 1 + 1 = 2
```

## Current testbench behavior

The testbench initializes inputs using:

```python
async def init_inputs(dut):
    dut.pc_en.value = 0
    dut.branch_en.value = 0
    dut.branch_offset.value = 0
    dut.nzp_en.value = 0
    dut.nzp_flag.value = 0
    dut.nzp_mask.value = 0
```

Then reset is applied:

```python
dut.rst.value = 1
await Timer(1, unit="ns")
await RisingEdge(dut.clk)
await Timer(1, unit="ns")
assert dut.pc_out.value == 0
dut.rst.value = 0
```

Each test drives signals, waits for a rising edge, waits one nanosecond for settled outputs, and then asserts expected PC behavior.

## Recommended additional tests

| Test                                      | Purpose                                                                |
| ----------------------------------------- | ---------------------------------------------------------------------- |
| `test_block_rst`                          | Verify `block_rst` clears `pc_out` and `nzp_out` without global reset  |
| `test_block_rst_priority_over_pc_en`      | Verify block reset wins over increment/branch                          |
| `test_rst_priority_over_block_rst`        | Verify global reset has highest priority                               |
| `test_nzp_out_updates`                    | Verify `nzp_out` exposes stored `nzp_reg`                              |
| `test_branch_all_mask`                    | Verify `nzp_mask = 3'b111` branches for any stored NZP                 |
| `test_branch_zero_mask`                   | Verify `nzp_mask = 3'b000` never branches                              |
| `test_branch_offset_zero`                 | Verify branch with offset zero holds PC when taken                     |
| `test_multiple_branch_offsets`            | Verify different offset values                                         |
| `test_no_pc_update_without_pc_en`         | Verify PC remains unchanged when `pc_en = 0`                           |
| `test_nzp_store_and_pc_update_same_cycle` | Define behavior when `nzp_en` and branch `pc_en` are asserted together |

## Known pitfalls

Do not forget that branch uses stored `nzp_reg`, not the incoming `nzp_flag`.

CMP and BR should be separate instructions.

Do not allow inactive SIMT lanes to update PC.

The core must gate `pc_en` with `active_mask[i]`.

Do not remove `block_rst`.

Without `block_rst`, a core reused for a later block could continue fetching from the previous block’s final PC.

Do not assume `branch_offset` is signed.

The current PC adds the 12-bit `branch_offset` directly to `pc_out`. Negative branches are not represented by this logic unless the ISA/PC implementation is later extended.

Do not assume `nzp_out` changes combinationally from `nzp_flag`.

`nzp_out` reflects the stored register value after a clocked update.

## Related integration tests

| Test                        | File                                      | What it proves                                           |
| --------------------------- | ----------------------------------------- | -------------------------------------------------------- |
| `test_core_basic`           | `Src/core/test_core.py`                   | PC/fetch/RET path completes a basic program              |
| `test_simt_relu`            | `Src/Top_level_GPU/test_top_level_gpu.py` | CMP/BR/SYNC behavior works across divergent thread lanes |
| `test_scheduler_divergence` | `Src/scheduler/test_scheduler.py`         | Scheduler reacts correctly to divergence detection       |
| `test_gpu_axel_program`     | `Src/Top_level_GPU/test_top_level_gpu.py` | PC supports longer top-level instruction flow            |

## Last known status

```text
Status: passing

Verified with:
  cd ~/gpu-project
  make test

Current unit coverage:
  reset
  increment
  NZP store
  branch taken
  branch not taken
```

## Design summary

`pc` is the per-thread program counter and NZP flag register. It resets to PC `0`, stores NZP flags from CMP, increments normally, branches when the stored NZP flag matches the branch mask, and resets per block using `block_rst`.

The most important behavior is:

```text
branch decision = branch_en && ((stored_nzp & nzp_mask) != 0)
```

and the most important integration rule is:

```text
core must gate pc_en with active_mask[i]
```
