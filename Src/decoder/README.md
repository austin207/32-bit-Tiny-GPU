# Decoder

## Overview

`decoder` is the instruction decode block for the Tiny GPU.

It receives one 32-bit instruction and extracts all instruction fields used by the rest of the core. It also generates control signals that tell the scheduler, PC, LSU, and register writeback path what kind of instruction is currently active.

The decoder is purely combinational. It has no clock, no reset, and no internal state.

## RTL schematic

![Decoder RTL schematic](../../assets/Images-Components/Decoder-page-00001.jpg)

## Source files

```text
Src/decoder/decoder.sv
Src/decoder/test_decoder.py
```

## Position in the GPU

The decoder sits after the fetcher/instruction latch and before the scheduler/datapath control logic.

```text
program memory
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
      ├── instruction fields -> register file / PC / LSU
      └── control signals    -> scheduler / PC / writeback / memory path
```

Inside `core.sv`, the decoder consumes the latched instruction:

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

## Module declaration

```systemverilog
module decoder (
    input  logic [31:0] instruction,

    output logic [5:0]  opcode,
    output logic [4:0]  rd_addr,
    output logic [4:0]  rs1_addr,
    output logic [4:0]  rs2_addr,
    output logic [4:0]  rs3_addr,
    output logic [15:0] imm,
    output logic [2:0]  nzp_mask,
    output logic [10:0] sync_offset,
    output logic [11:0] branch_offset,
    output logic sync_en,

    output logic ret,
    output logic write_back_en,
    output logic mem_read_en,
    output logic mem_write_en,
    output logic branch_en,
    output logic nzp_en
);
```

## Port description

| Port            | Direction | Width | Description                                               |
| --------------- | --------- | ----: | --------------------------------------------------------- |
| `instruction`   | input     |    32 | Raw encoded instruction                                   |
| `opcode`        | output    |     6 | Instruction opcode field                                  |
| `rd_addr`       | output    |     5 | Destination register address                              |
| `rs1_addr`      | output    |     5 | Source register 1 address                                 |
| `rs2_addr`      | output    |     5 | Source register 2 address                                 |
| `rs3_addr`      | output    |     5 | Source register 3 address, mainly used by FMA/store paths |
| `imm`           | output    |    16 | Immediate field                                           |
| `nzp_mask`      | output    |     3 | Branch mask for BRNZP                                     |
| `sync_offset`   | output    |    11 | Reconvergence/SYNC offset used by SIMT branch handling    |
| `branch_offset` | output    |    12 | PC branch offset                                          |
| `sync_en`       | output    |     1 | Asserted for SYNC instruction                             |
| `ret`           | output    |     1 | Asserted for RET instruction                              |
| `write_back_en` | output    |     1 | Asserted when instruction writes a register               |
| `mem_read_en`   | output    |     1 | Asserted for LOAD/LDR                                     |
| `mem_write_en`  | output    |     1 | Asserted for STORE/STR                                    |
| `branch_en`     | output    |     1 | Asserted for BR/BRNZP                                     |
| `nzp_en`        | output    |     1 | Asserted for CMP to update NZP flags                      |

## Instruction field extraction

The decoder extracts raw fields directly from the 32-bit instruction.

```systemverilog
assign opcode        = instruction[31:26];
assign rd_addr       = instruction[25:21];
assign rs1_addr      = instruction[20:16];
assign rs2_addr      = instruction[15:11];
assign rs3_addr      = instruction[10:6];
assign imm           = instruction[15:0];
assign nzp_mask      = instruction[25:23];
assign sync_offset   = instruction[22:12];
assign branch_offset = instruction[11:0];
```

## Generic R-type field layout

Most ALU-style instructions use this format:

```text
[31:26] opcode
[25:21] rd
[20:16] rs1
[15:11] rs2
[10:6]  rs3
[5:0]   unused / zero
```

Used by:

```text
ADD
SUB
MUL
DIV
MOD
SHL
SHR
AND
OR
XOR
NOT
FMA
IMUL
SAR
CMP field extraction
```

## Generic I-type field layout

Load, store, and constant instructions use immediate-style fields.

```text
[31:26] opcode
[25:21] rd
[20:16] rs1/base
[15:0]  imm
```

Used by:

```text
LDR
STR
CONST
```

For LDR and STR:

```text
effective address = register[rs1] + sign_extend(imm)
```

The actual sign extension is done in `core.sv`, not in the decoder.

## Branch field layout

BRNZP uses a branch-specific field layout:

```text
[31:26] opcode
[25:23] nzp_mask
[22:12] sync_offset
[11:0]  branch_offset
```

The decoder exposes:

```text
nzp_mask
sync_offset
branch_offset
```

These fields are used by the PC and SIMT divergence/reconvergence logic.

## Control signal defaults

At the start of the `always_comb` block, every control output is cleared:

```systemverilog
ret           = 1'b0;
write_back_en = 1'b0;
mem_read_en   = 1'b0;
mem_write_en  = 1'b0;
branch_en     = 1'b0;
nzp_en        = 1'b0;
sync_en       = 1'b0;
```

This is important because unsupported opcodes should not accidentally trigger memory requests, writeback, branches, RET, CMP, or SYNC.

## Opcode decode table

|  Opcode | Instruction class | Control outputs                        |
| ------: | ----------------- | -------------------------------------- |
| `6'h00` | NOP               | All control signals remain `0`         |
| `6'h01` | ADD               | `write_back_en = 1`                    |
| `6'h02` | SUB               | `write_back_en = 1`                    |
| `6'h03` | MUL               | `write_back_en = 1`                    |
| `6'h04` | DIV               | `write_back_en = 1`                    |
| `6'h05` | MOD               | `write_back_en = 1`                    |
| `6'h06` | SHL               | `write_back_en = 1`                    |
| `6'h07` | SHR               | `write_back_en = 1`                    |
| `6'h08` | AND               | `write_back_en = 1`                    |
| `6'h09` | OR                | `write_back_en = 1`                    |
| `6'h0A` | XOR               | `write_back_en = 1`                    |
| `6'h0B` | NOT               | `write_back_en = 1`                    |
| `6'h0C` | FMA               | `write_back_en = 1`                    |
| `6'h0D` | CMP               | `nzp_en = 1`                           |
| `6'h0E` | BR / BRNZP        | `branch_en = 1`                        |
| `6'h0F` | LOAD / LDR        | `mem_read_en = 1`, `write_back_en = 1` |
| `6'h10` | STORE / STR       | `mem_write_en = 1`                     |
| `6'h11` | CONST             | `write_back_en = 1`                    |
| `6'h12` | RET               | `ret = 1`                              |
| `6'h13` | IMUL              | `write_back_en = 1`                    |
| `6'h14` | SAR               | `write_back_en = 1`                    |
| `6'h15` | SYNC              | `sync_en = 1`                          |
| default | Unsupported       | All control signals remain `0`         |

## Current control decode implementation

```systemverilog
always_comb begin
    ret           = 1'b0;
    write_back_en = 1'b0;
    mem_read_en   = 1'b0;
    mem_write_en  = 1'b0;
    branch_en     = 1'b0;
    nzp_en        = 1'b0;
    sync_en       = 1'b0;

    case (opcode)
        6'h00: begin
            // NOP
        end

        6'h01, 6'h02, 6'h03, 6'h04,
        6'h05, 6'h06, 6'h07, 6'h08,
        6'h09, 6'h0A, 6'h0B, 6'h0C,
        6'h13, 6'h14: begin
            write_back_en = 1'b1;
        end

        6'h0D: begin
            nzp_en = 1'b1;
        end

        6'h0E: begin
            branch_en = 1'b1;
        end

        6'h0F: begin
            mem_read_en   = 1'b1;
            write_back_en = 1'b1;
        end

        6'h10: begin
            mem_write_en = 1'b1;
        end

        6'h11: begin
            write_back_en = 1'b1;
        end

        6'h12: begin
            ret = 1'b1;
        end

        6'h15: begin
            sync_en = 1'b1;
        end

        default: begin
            // Invalid/unsupported opcode: all controls stay low
        end
    endcase
end
```

## Interaction with the core

## Register writeback

`write_back_en` from the decoder is not used alone. Inside `core.sv`, register write enable is:

```systemverilog
.w_en(write_back_en_sched & write_back_en_dec & active_mask[i])
```

This means a register write happens only when:

```text
scheduler is in writeback/update timing
decoder says the instruction writes a register
thread lane is active
```

This prevents non-writeback instructions like BR, SYNC, STR, and RET from accidentally writing registers.

## Memory operations

For `LDR`:

```text
mem_read_en   = 1
write_back_en = 1
```

The scheduler enters the memory request/wait path. The loaded data is written back to `rd_addr`.

For `STR`:

```text
mem_write_en = 1
write_back_en = 0
```

The scheduler enters the memory request/wait path, but no register writeback occurs.

## CMP and NZP

For `CMP`:

```text
nzp_en = 1
write_back_en = 0
```

The ALU generates the NZP flag, and the PC stores it. CMP does not write a general-purpose register.

## Branch

For `BRNZP`:

```text
branch_en = 1
write_back_en = 0
```

The PC compares the stored NZP flag with `nzp_mask`.

In SIMT branch handling, the core also uses `branch_en`, `nzp_mask`, and per-thread stored NZP flags to compute:

```text
taken_mask
divergence_detected
```

## SYNC

For `SYNC`:

```text
sync_en = 1
```

The scheduler enters the SYNC/reconvergence path. SYNC does not write a register and does not request memory.

## RET

For `RET`:

```text
ret = 1
```

The scheduler asserts `block_done` and returns the core to IDLE.

## Timing assumptions

The decoder is purely combinational.

Assumptions:

- `instruction` is stable before downstream control logic samples decoder outputs.
- In `core.sv`, this is handled by the instruction latch.
- Field outputs update whenever `instruction` changes.
- Control outputs update whenever `opcode` changes.
- No output is registered inside the decoder.

## Important fixed core-level bug related to decoder stability

The decoder originally depended directly on the fetcher instruction output. That was risky because instruction data could change before a multi-cycle instruction completed.

The core now latches the fetched instruction:

```systemverilog
always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        instruction <= 32'b0;
    end else if (done) begin
        instruction <= instruction_raw;
    end
end
```

The decoder uses the stable latched instruction, not the raw fetcher output.

This is especially important for memory instructions such as `LDR`, which pass through:

```text
DECODE -> REQUEST -> WAIT -> EXECUTE -> UPDATE
```

## Verification

Unit test file:

```text
Src/decoder/test_decoder.py
```

The uploaded decoder tests verify field extraction and control signals for these instruction classes: ADD, BRNZP, LDR, RET, and SYNC.

## Current unit tests

| Test                     | Instruction | What it checks                                                           |
| ------------------------ | ----------- | ------------------------------------------------------------------------ |
| `test_add_instruction`   | ADD         | Opcode, `rd`, `rs1`, `rs2`, and ALU writeback enable                     |
| `test_BRNZP_instruction` | BRNZP       | Opcode, `nzp_mask`, `sync_offset`, `branch_offset`, and branch enable    |
| `test_LDR_instruction`   | LDR         | Opcode, `rd`, `rs1`, immediate, memory-read enable, and writeback enable |
| `test_RET_instruction`   | RET         | Opcode and `ret` enable                                                  |
| `test_SYNC_instruction`  | SYNC        | Opcode, `sync_en`, and no unrelated enables                              |

## Testbench style

The decoder is combinational, so the testbench does not start a clock.

Each test:

1. Builds a 32-bit instruction word.
2. Drives `dut.instruction`.
3. Waits 1 ns for combinational propagation.
4. Checks decoded fields and control signals.

Example:

```python
instruction = (opcode << 26) | (rd << 21) | (rs1 << 16) | (rs2 << 11)
dut.instruction.value = instruction
await Timer(1, unit="ns")
assert dut.opcode.value == opcode
```

## Known test issue

In `test_BRNZP_instruction`, this assertion message is misleading:

```python
assert dut.sync_en.value == 0, f"Expected sync enable to be 1 got {dut.sync_en.value}"
```

The assertion checks the correct value:

```text
sync_en == 0
```

because BRNZP is not SYNC.

Only the error message is wrong. It should say:

```python
assert dut.sync_en.value == 0, f"Expected sync enable to be 0 got {dut.sync_en.value}"
```

## Recommended additional tests

The current decoder tests are useful but incomplete. Add tests for:

| Test                      | Purpose                                                  |
| ------------------------- | -------------------------------------------------------- |
| `test_NOP_instruction`    | All control outputs stay low                             |
| `test_STR_instruction`    | `mem_write_en = 1`, `write_back_en = 0`                  |
| `test_CONST_instruction`  | `write_back_en = 1`, immediate field correct             |
| `test_CMP_instruction`    | `nzp_en = 1`, no writeback                               |
| `test_IMUL_instruction`   | `write_back_en = 1`                                      |
| `test_SAR_instruction`    | `write_back_en = 1`                                      |
| `test_invalid_opcode`     | Unsupported opcode leaves all controls low               |
| `test_rs3_field`          | Verify FMA/store third-source field extraction           |
| `test_branch_max_offsets` | Verify `sync_offset` and `branch_offset` boundary values |

## Known pitfalls

Do not make CMP write a register. CMP only updates NZP.

Do not make BRNZP write a register. BRNZP only controls PC/active-mask behavior.

Do not make STR write a register. STR only requests memory write.

Do not make SYNC write a register. SYNC only controls reconvergence.

Do not decode raw fetcher output directly in the core. Use the latched instruction.

Keep opcode values aligned with:

```text
assembler/include/gpu_asm.h
```

If the assembler opcode definitions change, this decoder must change too.

## Last known status

```text
Status: passing

Verified with:
  cd ~/gpu-project
  make test

Current unit coverage:
  ADD
  BRNZP
  LDR
  RET
  SYNC
```

## Design summary

`decoder` is a stateless combinational instruction decoder. It extracts register fields, immediate fields, branch masks, branch offsets, and SYNC offsets from the 32-bit instruction word. It also generates control signals for register writeback, memory read/write, CMP/NZP update, branch, SYNC, and RET.

The most important design rule is that decoder control signals are only valid when the input instruction is stable. Inside the core, stability is guaranteed by the instruction latch.
