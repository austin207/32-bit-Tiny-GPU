# Device Control Register

## Overview

`dcr` is the Device Control Register block for the Tiny GPU.

It stores host-configured kernel launch parameters and generates a one-cycle `start` pulse used to launch GPU execution through the dispatcher.

The DCR currently stores:

```text
num_blocks
blockDim
```

and generates:

```text
start
```

The module is sequential and updates on the rising edge of `clk`. It also supports asynchronous reset through `rst`.

## RTL schematic

![DCR RTL schematic](../../assets/Images-Components/DCR-page-00001.jpg)

## Source files

```text
Src/device_control_register/dcr.sv
Src/device_control_register/test_dcr.py
```

## Position in the GPU

The DCR sits at the control-entry side of the GPU. It receives writes from the host/testbench and provides launch configuration to the dispatcher.

```text
host / testbench
      │
      │ dcr_write_en, dcr_addr, dcr_data
      ▼
dcr
      │
      ├── num_blocks
      ├── blockDim
      └── start
            │
            ▼
      dispatcher
            │
            ▼
          cores
```

Inside `top_level_gpu.sv`, the DCR connects to the dispatcher like this:

```text
dcr.num_blocks -> dispatcher.num_blocks
dcr.blockDim   -> dispatcher.blockDim
dcr.start      -> dispatcher.dispatch_en
```

## Module declaration

```systemverilog
module dcr (
    input logic clk,
    input logic rst,

    input logic dcr_write_en,
    input logic [1:0] dcr_addr,
    input logic [31:0] dcr_data,

    output logic [31:0] num_blocks,
    output logic [31:0] blockDim,
    output logic start
);
```

## Port description

| Port           | Direction | Width | Description                                |
| -------------- | --------- | ----: | ------------------------------------------ |
| `clk`          | input     |     1 | Clock                                      |
| `rst`          | input     |     1 | Reset                                      |
| `dcr_write_en` | input     |     1 | Enables a DCR write                        |
| `dcr_addr`     | input     |     2 | Selects which DCR register/action to write |
| `dcr_data`     | input     |    32 | Data written into selected DCR register    |
| `num_blocks`   | output    |    32 | Number of blocks to launch                 |
| `blockDim`     | output    |    32 | Number of threads per block                |
| `start`        | output    |     1 | One-cycle kernel start pulse               |

## Register map

| Address | Name         | Type         | Description                         |
| ------: | ------------ | ------------ | ----------------------------------- |
| `2'b00` | `num_blocks` | register     | Stores number of blocks to dispatch |
| `2'b01` | `blockDim`   | register     | Stores thread count per block       |
| `2'b10` | `start`      | pulse/action | Generates a one-cycle launch pulse  |
| `2'b11` | reserved     | unused       | No current behavior                 |

## Write behavior

Writes only occur when:

```systemverilog
dcr_write_en == 1'b1
```

The selected action depends on `dcr_addr`:

```systemverilog
case (dcr_addr)
    2'b00: num_blocks <= dcr_data;
    2'b01: blockDim   <= dcr_data;
    2'b10: start      <= 1;
endcase
```

## Start pulse behavior

`start` is a pulse, not a sticky register.

Every non-reset cycle begins by clearing `start`:

```systemverilog
start <= 0;
```

Then, if the host/testbench writes to address `2'b10`, `start` is asserted for that clock cycle:

```systemverilog
if (dcr_write_en && dcr_addr == 2'b10) begin
    start <= 1;
end
```

This means:

```text
write to dcr_addr 2'b10 -> start = 1 for one cycle
next cycle              -> start = 0
```

The dispatcher uses this pulse to begin dispatching blocks.

## Reset behavior

On reset:

```text
num_blocks -> 0
blockDim   -> 0
start      -> 0
```

Reset is asynchronous in the current RTL because the sensitivity list is:

```systemverilog
always_ff @(posedge clk or posedge rst)
```

So asserting `rst` immediately resets the outputs, independent of the next clock edge.

## Current implementation

```systemverilog
always_ff @( posedge clk or posedge rst ) begin 
    if (rst) begin
        num_blocks <= 0;
        blockDim <= 0;
        start <= 0;
    end else begin
        start <= 0; 
        if (dcr_write_en) begin
            case (dcr_addr)
                2'b00: num_blocks <= dcr_data;
                2'b01: blockDim <= dcr_data;
                2'b10: start <= 1;
            endcase
        end
    end
end
```

## Operation sequence

A normal kernel launch sequence is:

```text
1. Write number of blocks
2. Write block dimension
3. Write start address to emit one-cycle start pulse
4. Dispatcher receives start pulse
5. Dispatcher begins assigning blocks to cores
```

Example sequence:

```text
dcr_addr = 2'b00, dcr_data = num_blocks, dcr_write_en = 1
dcr_addr = 2'b01, dcr_data = blockDim,   dcr_write_en = 1
dcr_addr = 2'b10, dcr_data = don't care, dcr_write_en = 1
```

## Example from top-level tests

The top-level cocotb tests typically configure DCR like this:

```python
# num_blocks = 1
dut.dcr_write_en.value = 1
dut.dcr_addr.value = 0b00
dut.dcr_data.value = 1

# blockDim = 4
dut.dcr_addr.value = 0b01
dut.dcr_data.value = 4

# start pulse
dut.dcr_addr.value = 0b10
dut.dcr_data.value = 0
```

After the start write, `dcr_write_en` is deasserted.

## Timing assumptions

The DCR assumes:

```text
- dcr_write_en, dcr_addr, and dcr_data are valid before the rising edge of clk.
- num_blocks and blockDim are written before start is triggered.
- start is consumed as a one-cycle pulse by the dispatcher.
- dcr_data is ignored for the start command.
- dcr_addr 2'b11 is currently unused.
```

## Verification

Unit test file:

```text
Src/device_control_register/test_dcr.py
```

## Current tests

| Test                    | What it checks                                                        |
| ----------------------- | --------------------------------------------------------------------- |
| `test_write_num_blocks` | Writing address `2'b00` updates `num_blocks`                          |
| `test_write_blockDim`   | Writing address `2'b01` updates `blockDim`                            |
| `test_start_pulse`      | Writing address `2'b10` asserts `start` for one cycle, then clears it |

## `test_write_num_blocks`

This test writes:

```text
dcr_addr = 2'b00
dcr_data = 8
```

Expected result:

```text
num_blocks = 8
```

## `test_write_blockDim`

This test writes:

```text
dcr_addr = 2'b01
dcr_data = 4
```

Expected result:

```text
blockDim = 4
```

## `test_start_pulse`

This test writes:

```text
dcr_addr = 2'b10
dcr_data = 0
```

Expected result:

```text
start = 1 for one cycle
start = 0 on the following cycle
```

## Recommended additional tests

The current tests cover the basic DCR behavior. Useful future tests:

| Test                                | Purpose                                                                                               |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `test_reset_clears_registers`       | Confirm reset clears `num_blocks`, `blockDim`, and `start`                                            |
| `test_no_write_when_write_en_low`   | Confirm DCR ignores address/data when `dcr_write_en = 0`                                              |
| `test_reserved_addr_no_effect`      | Confirm `dcr_addr = 2'b11` does not change any output                                                 |
| `test_start_does_not_modify_config` | Confirm start write does not alter `num_blocks` or `blockDim`                                         |
| `test_back_to_back_start_writes`    | Confirm repeated start writes produce repeated pulses                                                 |
| `test_write_order`                  | Confirm block configuration remains correct when `num_blocks` and `blockDim` are written before start |

## Known pitfalls

Do not make `start` sticky.

`start` must stay a one-cycle pulse. If it remains high, the dispatcher may repeatedly restart dispatch or treat the same launch as multiple launches.

Do not trigger `start` before writing `num_blocks` and `blockDim`.

If `start` is written before configuration registers are valid, the dispatcher may launch with zero blocks or zero block dimension.

Do not use `dcr_data` for the start command.

Currently, address `2'b10` is an action write. The data value is ignored.

Do not assign behavior to `2'b11` without updating this README, top-level tests, and any host-side launch code.

## Related integration tests

| Test                         | File                                      | What it proves                                       |
| ---------------------------- | ----------------------------------------- | ---------------------------------------------------- |
| `test_gpu_axel_program`      | `Src/Top_level_GPU/test_top_level_gpu.py` | DCR can configure and launch full top-level program  |
| `test_simt_relu`             | `Src/Top_level_GPU/test_top_level_gpu.py` | DCR can launch the SIMT ReLU kernel                  |
| `test_dispatcher_basic_flow` | `Src/dispatcher/test_dispatcher.py`       | Dispatcher responds to launch/control flow correctly |

## Last known status

```text
Status: passing

Verified with:
  cd ~/gpu-project
  make test

Current unit coverage:
  write num_blocks
  write blockDim
  one-cycle start pulse
```

## Design summary

`dcr` is a small launch-configuration register block. It stores the number of blocks and block dimension, then emits a one-cycle `start` pulse when the host/testbench writes to the start address.

The most important rule is:

```text
num_blocks and blockDim are persistent registers
start is a one-cycle pulse
```

This behavior must remain stable because the dispatcher depends on `start` as a launch event, not as a level-held enable.
