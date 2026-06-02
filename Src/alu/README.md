# ALU

## Overview

`alu` is the combinational arithmetic and logic unit used by each GPU thread lane.

It receives up to three 32-bit operands, an operation selector, and produces either a 32-bit result or a 3-bit NZP comparison flag. The ALU is instantiated once per thread inside the core datapath.

The ALU has no clock and no internal state. Its output changes combinationally when the operands or operation selector change.

## RTL schematic

![ALU RTL schematic](../../assets/Images-Components/ALU-page-00001.jpg)

## Source files

```text
Src/alu/alu.sv
Src/alu/test_alu.py
```

## Position in the GPU

```text
register file read ports
        │
        │ operand1, operand2, operand3
        ▼
      alu
        │
        ├── result    -> register writeback path
        │
        └── nzp_flag  -> PC / branch decision path
```

In the core datapath, each thread has its own ALU instance:

```text
thread_gen[i].alu_inst
```

The ALU output is used by:

```text
- arithmetic instructions
- logical instructions
- FMA
- signed multiply
- arithmetic shift right
- CMP / branch flag generation
```

## Module declaration

```systemverilog
(* syn_dont_touch = 1 *) module alu (
    input logic [31:0] operand1,
    input logic [31:0] operand2,
    input logic [31:0] operand3,
    input logic [5:0] op_select,
    output logic [31:0] result,
    output logic [2:0] nzp_flag
);
```

## Port description

| Port        | Direction | Width | Description                                                 |
| ----------- | --------- | ----: | ----------------------------------------------------------- |
| `operand1`  | input     |    32 | First ALU operand                                           |
| `operand2`  | input     |    32 | Second ALU operand                                          |
| `operand3`  | input     |    32 | Third operand, mainly used by FMA                           |
| `op_select` | input     |     6 | ALU operation selector / opcode                             |
| `result`    | output    |    32 | ALU result                                                  |
| `nzp_flag`  | output    |     3 | Negative/Zero/Positive comparison flag used by branch logic |

## Combinational behavior

The ALU is implemented using one `always_comb` block.

Default outputs are assigned at the start of the block:

```systemverilog
result   = 32'b0;
nzp_flag = 3'b000;
```

This prevents stale values from being held when an unsupported opcode is selected.

The `case (op_select)` statement selects the operation.

## Supported operations

|  Opcode | Operation | Description                                                            |
| ------: | --------- | ---------------------------------------------------------------------- |
| `6'h01` | `ADD`     | `operand1 + operand2`                                                  |
| `6'h02` | `SUB`     | `operand1 - operand2`                                                  |
| `6'h03` | `MUL`     | Unsigned/default multiplication: `operand1 * operand2`                 |
| `6'h04` | `DIV`     | Unsigned/default division: `operand1 / operand2`                       |
| `6'h05` | `MOD`     | Unsigned/default modulo: `operand1 % operand2`                         |
| `6'h06` | `SHL`     | Logical left shift: `operand1 << operand2`                             |
| `6'h07` | `SHR`     | Logical right shift: `operand1 >> operand2`                            |
| `6'h08` | `AND`     | Bitwise AND                                                            |
| `6'h09` | `OR`      | Bitwise OR                                                             |
| `6'h0A` | `XOR`     | Bitwise XOR                                                            |
| `6'h0B` | `NOT`     | Bitwise NOT of `operand1`                                              |
| `6'h0C` | `FMA`     | Fused multiply-add style operation: `(operand1 * operand2) + operand3` |
| `6'h0D` | `CMP`     | Signed comparison. Updates `nzp_flag`                                  |
| `6'h13` | `IMUL`    | Signed multiplication                                                  |
| `6'h14` | `SAR`     | Signed arithmetic right shift                                          |

## Opcode mapping

The ALU opcodes match the assembler opcode definitions in:

```text
assembler/include/gpu_asm.h
```

Relevant definitions:

```c
#define OP_ADD   0x01
#define OP_SUB   0x02
#define OP_MUL   0x03
#define OP_DIV   0x04
#define OP_MOD   0x05
#define OP_SHL   0x06
#define OP_SHR   0x07
#define OP_AND   0x08
#define OP_OR    0x09
#define OP_XOR   0x0A
#define OP_NOT   0x0B
#define OP_FMA   0x0C
#define OP_CMP   0x0D
#define OP_IMUL  0x13
#define OP_SAR   0x14
```

## NZP flag behavior

`nzp_flag` is only meaningful for the `CMP` operation.

For all other operations, `nzp_flag` remains:

```text
3'b000
```

The CMP operation compares `operand1` and `operand2` as signed 32-bit values:

```systemverilog
nzp_flag =
    ($signed(operand1) - $signed(operand2)) == 0 ? 3'b010 :
    ($signed(operand1) - $signed(operand2)) > 0  ? 3'b001 :
                                                   3'b100;
```

The flag encoding is:

| Flag | Bit pattern | Meaning                 |
| ---- | ----------: | ----------------------- |
| `P`  |    `3'b001` | Positive / greater-than |
| `Z`  |    `3'b010` | Zero / equal            |
| `N`  |    `3'b100` | Negative / less-than    |

This matches the assembler branch-mask constants:

```c
#define AXEL_N   0b100
#define AXEL_Z   0b010
#define AXEL_P   0b001
#define AXEL_NZ  0b110
#define AXEL_NP  0b101
#define AXEL_ZP  0b011
#define AXEL_ALL 0b111
```

## Branch interaction

The ALU itself does not branch. It only generates `nzp_flag` during `CMP`.

The branch path is:

```text
CMP instruction
    │
    ▼
ALU generates nzp_flag
    │
    ▼
PC stores nzp_flag
    │
    ▼
BRnzp checks nzp_mask against stored NZP
```

For example, in SIMT ReLU:

```text
CMP R1, R0
BR P, sync_offset=2, branch_offset=2
```

Positive threads generate:

```text
nzp_flag = 3'b001
```

Then `BR P` can take the positive branch.

## Signed and unsigned behavior

The ALU has both unsigned/default and signed variants.

| Operation | Signed?                 | Notes                                        |
| --------- | ----------------------- | -------------------------------------------- |
| `MUL`     | No explicit signed cast | Uses default 32-bit multiplication           |
| `IMUL`    | Yes                     | Uses `$signed(operand1) * $signed(operand2)` |
| `SHR`     | Logical                 | Zero-filling right shift                     |
| `SAR`     | Arithmetic              | Sign-extending right shift                   |
| `CMP`     | Signed                  | Uses `$signed(...)` comparison logic         |
| `DIV`     | No explicit signed cast | Default division                             |
| `MOD`     | No explicit signed cast | Default modulo                               |
| `FMA`     | No explicit signed cast | `(operand1 * operand2) + operand3`           |

## Current implementation

```systemverilog
always_comb begin
    result = 32'b0; 
    nzp_flag = 3'b000;

    case (op_select)
       6'h01 : result = operand1 + operand2;
       6'h02 : result = operand1 - operand2;
       6'h03 : result = operand1 * operand2;
       6'h04 : result = operand1 / operand2;
       6'h05 : result = operand1 % operand2;
       6'h06 : result = operand1 << operand2;
       6'h07 : result = operand1 >> operand2;
       6'h08 : result = operand1 & operand2;
       6'h09 : result = operand1 | operand2;
       6'h0A : result = operand1 ^ operand2;
       6'h0B : result = ~operand1;
       6'h0C : result = (operand1 * operand2) + operand3;

       6'h0D : begin
           result = 0;
           nzp_flag =
               ($signed(operand1) - $signed(operand2)) == 0 ? 3'b010 :
               ($signed(operand1) - $signed(operand2)) > 0  ? 3'b001 :
                                                              3'b100;
       end

       6'h13 : result = $signed(operand1) * $signed(operand2);
       6'h14 : result = $signed(operand1) >>> operand2;

       default: ;
    endcase
end
```

## Timing assumptions

The ALU is purely combinational.

Assumptions:

```text
- Inputs are stable before the result is sampled.
- There is no internal register or pipeline stage.
- `result` and `nzp_flag` are valid after combinational propagation delay.
- The scheduler/core controls when ALU outputs are used for writeback or NZP update.
```

In cocotb tests, a short timer delay is used after changing inputs:

```python
await Timer(1, unit="ns")
```

This gives the simulator time to propagate the combinational output.

## Verification

Unit test file:

```text
Src/alu/test_alu.py
```

## Current tests

| Test               | Operation | What it checks                            |
| ------------------ | --------- | ----------------------------------------- |
| `test_ADD`         | `ADD`     | `5 + 3 = 8`                               |
| `test_SUB`         | `SUB`     | `10 - 4 = 6`                              |
| `test_CMP_equal`   | `CMP`     | Equal comparison sets `Z = 3'b010`        |
| `test_CMP_greater` | `CMP`     | Greater-than comparison sets `P = 3'b001` |
| `test_CMP_less`    | `CMP`     | Less-than comparison sets `N = 3'b100`    |
| `test_NOT`         | `NOT`     | `~0x00000000 = 0xFFFFFFFF`                |

## Current testbench behavior

The ALU is combinational, so the testbench does not start a clock.

Each test:

```text
1. Clears operands and opcode.
2. Applies new operands.
3. Selects the opcode.
4. Waits 1 ns.
5. Checks `result` or `nzp_flag`.
```

Example:

```python
dut.operand1.value = 5
dut.operand2.value = 3
dut.op_select.value = 0x01
await Timer(1, unit="ns")
assert dut.result.value == 8
```

## Recommended additional tests

Current tests only cover a subset of the ALU. The following tests should be added later:

| Test                       | Purpose                                             |
| -------------------------- | --------------------------------------------------- |
| `test_MUL`                 | Verify unsigned/default multiply                    |
| `test_IMUL_negative`       | Verify signed multiplication with negative operands |
| `test_FMA`                 | Verify `(operand1 * operand2) + operand3`           |
| `test_AND_OR_XOR`          | Verify bitwise logic                                |
| `test_SHL`                 | Verify left shift                                   |
| `test_SHR`                 | Verify logical right shift                          |
| `test_SAR_negative`        | Verify signed arithmetic right shift preserves sign |
| `test_DIV`                 | Verify division                                     |
| `test_MOD`                 | Verify modulo                                       |
| `test_default_opcode`      | Verify unsupported opcode outputs zero              |
| `test_cmp_negative_values` | Verify signed CMP with two's-complement operands    |

## Known pitfalls

### Division by zero is not guarded

The current ALU implementation does not protect against:

```systemverilog
operand2 == 0
```

for `DIV` or `MOD`.

Tests and programs should avoid divide-by-zero unless explicit behavior is later added.

### `MUL` and `IMUL` are different

`MUL` uses:

```systemverilog
operand1 * operand2
```

`IMUL` uses:

```systemverilog
$signed(operand1) * $signed(operand2)
```

Use `IMUL` when signed multiplication is required.

### `SHR` and `SAR` are different

`SHR` uses logical right shift:

```systemverilog
operand1 >> operand2
```

`SAR` uses arithmetic right shift:

```systemverilog
$signed(operand1) >>> operand2
```

Use `SAR` for signed fixed-point values.

### `nzp_flag` is only valid for CMP

Do not use `nzp_flag` after arithmetic/logical operations. It is only intentionally set by opcode `6'h0D`.

### CMP uses signed subtraction

The CMP operation is based on signed subtraction:

```systemverilog
$signed(operand1) - $signed(operand2)
```

For normal values, this is fine. Extreme signed overflow cases are not currently tested.

A safer future implementation could use direct signed comparisons:

```systemverilog
if ($signed(operand1) == $signed(operand2))
    nzp_flag = 3'b010;
else if ($signed(operand1) > $signed(operand2))
    nzp_flag = 3'b001;
else
    nzp_flag = 3'b100;
```

This avoids relying on the sign of a potentially overflowing subtraction.

## Related integration tests

| Test                        | File                                      | What it proves                                                  |
| --------------------------- | ----------------------------------------- | --------------------------------------------------------------- |
| `test_core_basic`           | `Src/core/test_core.py`                   | ALU result participates correctly in core execution             |
| `test_scheduler_basic_flow` | `Src/scheduler/test_scheduler.py`         | Scheduler enables execute/update timing around ALU operations   |
| `test_simt_relu`            | `Src/Top_level_GPU/test_top_level_gpu.py` | CMP generates correct NZP flags for SIMT branch divergence      |
| `test_gpu_axel_program`     | `Src/Top_level_GPU/test_top_level_gpu.py` | ALU/FMA/SAR/IMUL operations support forward/update program flow |

## Last known status

```text
Status: passing

Verified with:
  cd ~/gpu-project
  make test

Current unit coverage:
  ADD
  SUB
  CMP equal
  CMP greater
  CMP less
  NOT
```

## Design summary

`alu` is a stateless combinational execution unit. It performs arithmetic, logic, shift, multiply, FMA, signed multiply, signed arithmetic shift, and signed comparison operations.

Its most important branch-related output is `nzp_flag`, which uses this encoding:

```text
N = 3'b100
Z = 3'b010
P = 3'b001
```

This encoding must remain aligned with the assembler constants and the PC branch-mask logic.
