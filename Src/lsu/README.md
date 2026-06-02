# LSU

## Overview

`lsu` is the Load/Store Unit used by each GPU thread lane.

It converts a decoded memory operation from the core into a request for the core-level memory controller. For loads, it waits for memory response data and exposes that data back to the core writeback path. For stores, it forwards write data to memory and waits for an acknowledgement.

The LSU is a small two-state sequential FSM:

```text
IDLE -> WAITING -> IDLE
```

It handles one memory transaction at a time.

## RTL schematic

![LSU RTL schematic](../../assets/Images-Components/LSU-page-00001.jpg)

## Source files

```text
Src/lsu/lsu.sv
Src/lsu/test_lsu.py
```

## Position in the GPU

Each thread lane inside `core.sv` has its own LSU instance.

```text
thread register file
        │
        │ address/data operands
        ▼
      lsu
        │
        │ req_valid, req_addr, read_write_switch, write_data
        ▼
mem_controller
        │
        │ resp_valid, resp_data
        ▼
      lsu
        │
        └── mem_read_data -> register writeback path
```

In the full core memory path:

```text
register file / immediate
        │
        ▼
address generation in core.sv
        │
        ▼
per-thread LSU
        │
        ▼
mem_controller
        │
        ▼
top-level data memory interface
```

## Module declaration

```systemverilog
module lsu (
    input logic clk,
    input logic rst,

    input logic core_en,
    output logic done,
    input logic [31:0] mem_data_address,

    output logic req_valid,
    output logic [31:0] req_addr,
    output logic [31:0] write_data,
    input logic resp_valid,
    input logic [31:0] resp_data,

    input logic mem_write_en,
    input logic [31:0] mem_write_data,
    input logic mem_read_en,
    output logic [31:0] mem_read_data,

    output logic read_write_switch
);
```

## Port description

| Port                | Direction | Width | Description                                                     |
| ------------------- | --------- | ----: | --------------------------------------------------------------- |
| `clk`               | input     |     1 | Clock                                                           |
| `rst`               | input     |     1 | Reset                                                           |
| `core_en`           | input     |     1 | Enables this LSU transaction for the active thread              |
| `done`              | output    |     1 | One-cycle pulse when the memory transaction completes           |
| `mem_data_address`  | input     |    32 | Effective memory address from core address-generation logic     |
| `req_valid`         | output    |     1 | Request-valid pulse to memory controller                        |
| `req_addr`          | output    |    32 | Request address sent to memory controller                       |
| `write_data`        | output    |    32 | Store data sent to memory controller                            |
| `resp_valid`        | input     |     1 | Response-valid from memory controller                           |
| `resp_data`         | input     |    32 | Read response data from memory controller                       |
| `mem_write_en`      | input     |     1 | Decoder/control signal for store instruction                    |
| `mem_write_data`    | input     |    32 | Data to be written on store                                     |
| `mem_read_en`       | input     |     1 | Decoder/control signal for load instruction                     |
| `mem_read_data`     | output    |    32 | Latched load data for register writeback                        |
| `read_write_switch` | output    |     1 | Request type sent to memory controller. `1 = read`, `0 = write` |

## Read/write convention

The LSU uses the same convention as the memory controller:

```text
1 = read
0 = write
```

So:

```text
read_write_switch = 1 -> read request
read_write_switch = 0 -> write request
```

For reads:

```text
mem_read_en = 1
req_valid pulses
req_addr = mem_data_address
read_write_switch = 1
wait for resp_valid
mem_read_data = resp_data
done pulses
```

For writes:

```text
mem_write_en = 1
req_valid pulses
req_addr = mem_data_address
write_data = mem_write_data
read_write_switch = 0
wait for resp_valid acknowledgement
done pulses
```

## FSM states

| State     | Encoding | Meaning                                                                         |
| --------- | -------: | ------------------------------------------------------------------------------- |
| `IDLE`    |   `1'b0` | No memory operation is in flight. Waits for `core_en` plus a read/write enable. |
| `WAITING` |   `1'b1` | A request has been issued. Waits for `resp_valid`.                              |

## Internal signals

| Signal    | Description                                                                                     |
| --------- | ----------------------------------------------------------------------------------------------- |
| `state`   | Current LSU FSM state                                                                           |
| `is_read` | Latched transaction type. `1 = current transaction is read`, `0 = current transaction is write` |

## Operation

## 1. Reset

On reset, the LSU clears its request, response, and state outputs:

```systemverilog
req_valid     <= 0;
req_addr      <= 32'b0;
mem_read_data <= 32'b0;
done          <= 0;
is_read       <= 0;
state         <= IDLE;
```

Reset is asynchronous because the sequential block uses:

```systemverilog
always_ff @(posedge clk or posedge rst)
```

## 2. Starting a read

When the LSU is in `IDLE`, `core_en` is high, and `mem_read_en` is asserted:

```systemverilog
is_read           <= 1;
req_addr          <= mem_data_address;
req_valid         <= 1;
read_write_switch <= 1;
state             <= WAITING;
```

The LSU emits a one-cycle request to the memory controller.

## 3. Starting a write

When the LSU is in `IDLE`, `core_en` is high, and `mem_write_en` is asserted:

```systemverilog
is_read           <= 0;
req_addr          <= mem_data_address;
req_valid         <= 1;
read_write_switch <= 0;
write_data        <= mem_write_data;
state             <= WAITING;
```

The LSU emits a one-cycle write request and forwards the write data.

## 4. Waiting for response

In `WAITING`, the LSU waits for:

```text
resp_valid = 1
```

If the transaction is a read:

```systemverilog
mem_read_data <= resp_data;
done          <= 1;
state         <= IDLE;
```

If the transaction is a write:

```systemverilog
done  <= 1;
state <= IDLE;
```

For writes, `resp_valid` acts as a memory acknowledgement.

## Current RTL implementation

```systemverilog
logic is_read;

typedef enum logic { 
    IDLE = 1'b0,
    WAITING = 1'b1
} state_t;

state_t state;

always_ff @( posedge clk or posedge rst ) begin
    if (rst) begin
        req_valid <= 0;
        req_addr <= 32'b0;
        mem_read_data <= 32'b0;
        done <= 0;
        is_read <= 0;
        state <= IDLE;
    end else begin
        req_valid <= 0;
        req_addr <= 32'b0;
        done <= 0;

        case (state)
            IDLE : begin
                if (core_en) begin
                    if (mem_read_en) begin
                        is_read <= 1;
                        req_addr <= mem_data_address;
                        req_valid <= 1;
                        read_write_switch <= 1;
                        state <= WAITING;
                    end else if (mem_write_en) begin
                        is_read <= 0;
                        req_addr <= mem_data_address;
                        req_valid <= 1;
                        read_write_switch <= 0;
                        write_data <= mem_write_data;  
                        state <= WAITING;
                    end
                end
            end

            WAITING : begin
                if (is_read) begin
                    if (resp_valid) begin
                        mem_read_data <= resp_data;
                        done <= 1;
                        state <= IDLE;
                    end 
                end else begin
                    if (resp_valid) begin
                        done <= 1;
                        state <= IDLE;                        
                    end
                end
            end

            default : begin
                state <= IDLE;
            end
        endcase
    end
end
```

## Timing behavior

The LSU uses pulse-style handshaking.

## Request timing

`req_valid` is asserted for one cycle when a transaction starts.

Example read request:

```text
cycle N:
  state = IDLE
  core_en = 1
  mem_read_en = 1
  mem_data_address = 42

cycle N+1:
  req_valid = 1
  req_addr = 42
  read_write_switch = 1
  state = WAITING
```

Example write request:

```text
cycle N:
  state = IDLE
  core_en = 1
  mem_write_en = 1
  mem_data_address = 42
  mem_write_data = 5678

cycle N+1:
  req_valid = 1
  req_addr = 42
  write_data = 5678
  read_write_switch = 0
  state = WAITING
```

## Response timing

`done` is asserted for one cycle when the memory controller responds.

Read response:

```text
cycle M:
  state = WAITING
  is_read = 1
  resp_valid = 1
  resp_data = 1234

cycle M+1:
  mem_read_data = 1234
  done = 1
  state = IDLE
```

Write response:

```text
cycle M:
  state = WAITING
  is_read = 0
  resp_valid = 1

cycle M+1:
  done = 1
  state = IDLE
```

## Interaction with memory controller

The LSU connects to `mem_controller` through per-thread request/response lanes.

In `core.sv`:

```systemverilog
lsu lsu_inst (
    .clk               (clk),
    .rst               (rst),
    .core_en           (lsu_en & active_mask[i]),
    .done              (lsu_done_raw[i]),
    .mem_data_address  (mem_addr[i]),

    .req_valid         (lsu_req_valid[i]),
    .req_addr          (lsu_req_addr[i]),
    .write_data        (lsu_req_data[i]),
    .resp_valid        (lsu_resp_valid[i]),
    .resp_data         (lsu_resp_data[i]),

    .mem_write_en      (mem_write_en),
    .mem_write_data    (reg_data3[i]),
    .mem_read_en       (mem_read_en),
    .mem_read_data     (lsu_read_data[i]),

    .read_write_switch (lsu_req_rw[i])
);
```

The memory controller expects `req_valid` to be a one-cycle pulse. It buffers request pulses internally using its `pending` buffer.

## Interaction with core writeback

For load instructions, the core writeback mux uses LSU read data:

```systemverilog
assign write_data[i] =
    mem_read_en        ? lsu_read_data[i] :
    (opcode == 6'h11)  ? {16'b0, imm}     :
                          alu_result[i];
```

So for `LDR`:

```text
lsu.mem_read_data -> core.lsu_read_data[i] -> core.write_data[i] -> register file w_data
```

The register write only commits when:

```systemverilog
write_back_en_sched & write_back_en_dec & active_mask[i]
```

## Interaction with active mask

The LSU itself does not know the active mask directly.

Instead, `core.sv` gates LSU enable:

```systemverilog
.core_en(lsu_en & active_mask[i])
```

This prevents inactive SIMT lanes from issuing memory requests.

## Address generation

The LSU receives the already-computed effective address through:

```systemverilog
input logic [31:0] mem_data_address
```

Address generation is done in `core.sv`:

```systemverilog
assign mem_addr[i] = reg_data1[i] + {{16{imm[15]}}, imm};
```

So the LSU does not calculate base-plus-offset. It only forwards the final address.

## Store data source

The LSU receives store data through:

```systemverilog
input logic [31:0] mem_write_data
```

In `core.sv`, this is connected to:

```systemverilog
.mem_write_data(reg_data3[i])
```

For store instructions, `reg_data3[i]` is selected from the register file’s third read port.

## Important fixed integration bug

The LSU was involved in the packed response-data bug fixed in the memory path.

The bad behavior during `test_simt_relu` was:

```text
mc_resp_data=5
mc_out_data0=5
lsu0_resp_v=1
lsu0_resp_data=0
lsu0_read_data=0
```

This showed that the LSU saw `resp_valid`, but `resp_data` was zero. The root cause was not inside the LSU. It was a packed/unpacked mismatch between:

```text
core.sv lsu_resp_data
mem_controller.sv resp_data
```

The fixed shape is:

```systemverilog
logic [THREADS_PER_CORE-1:0][31:0] lsu_resp_data;
```

in `core.sv`, matched with:

```systemverilog
output logic [THREADS_PER_CORE-1:0][31:0] resp_data
```

in `mem_controller.sv`.

After this fix, the LSU received the correct read data:

```text
lsu0_resp_v=1
lsu0_resp_data=5
lsu0_read_data=5
```

Then `LDR` writeback worked.

## Timing assumptions

The LSU assumes:

- `core_en` is asserted only when the scheduler wants to begin a memory transaction.
- `mem_read_en` and `mem_write_en` are stable when `core_en` is asserted.
- Only one of `mem_read_en` or `mem_write_en` should be high for a valid transaction.
- `mem_data_address` is valid when `core_en` is high.
- `mem_write_data` is valid when a write transaction starts.
- `resp_valid` means `resp_data` is valid in the same cycle for reads.
- `done` is consumed as a one-cycle completion pulse by the core/scheduler path.

## Reset behavior

On reset:

```text
state         -> IDLE
req_valid     -> 0
req_addr      -> 0
mem_read_data -> 0
done          -> 0
is_read       -> 0
```

Note: the current reset block does not explicitly reset `write_data` or `read_write_switch`.

They are assigned when a write/read transaction starts. If deterministic reset values are needed for waveform/debug clarity, these can be added later:

```systemverilog
write_data        <= 32'b0;
read_write_switch <= 1'b0;
```

## Verification

Unit test file:

```text
Src/lsu/test_lsu.py
```

## Current tests

| Test                     | What it checks                                                        |
| ------------------------ | --------------------------------------------------------------------- |
| `test_read`              | Read request, response capture into `mem_read_data`, and `done` pulse |
| `test_write`             | Write request, `write_data` forwarding, and `done` pulse on ack       |
| `test_reset_during_read` | Reset during an outstanding read clears read data and done            |

## `test_read`

Stimulus:

```text
core_en = 1
mem_read_en = 1
mem_data_address = 42
resp_valid = 1
resp_data = 1234
```

Expected behavior:

```text
req_valid = 1
req_addr = 42
read_write_switch = 1
mem_read_data = 1234
done = 1
```

## `test_write`

Stimulus:

```text
core_en = 1
mem_write_en = 1
mem_data_address = 42
mem_write_data = 5678
resp_valid = 1
```

Expected behavior:

```text
req_valid = 1
req_addr = 42
read_write_switch = 0
write_data = 5678
done = 1
```

## `test_reset_during_read`

Stimulus:

```text
start read transaction
assert rst before response
```

Expected behavior:

```text
mem_read_data = 0
done = 0
```

## Testbench behavior

The LSU testbench starts a clock:

```python
cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
```

Then it uses:

```python
await RisingEdge(dut.clk)
await Timer(1, unit="ns")
```

The `Timer(1 ns)` after the clock edge lets registered outputs settle in the simulator before assertions are checked.

## Recommended additional tests

| Test                               | Purpose                                               |
| ---------------------------------- | ----------------------------------------------------- |
| `test_req_valid_one_cycle_pulse`   | Verify `req_valid` does not remain high while waiting |
| `test_done_one_cycle_pulse`        | Verify `done` clears after one cycle                  |
| `test_read_write_switch_read`      | Verify read request drives `read_write_switch = 1`    |
| `test_read_write_switch_write`     | Verify write request drives `read_write_switch = 0`   |
| `test_req_addr_read`               | Verify read request forwards `mem_data_address`       |
| `test_req_addr_write`              | Verify write request forwards `mem_data_address`      |
| `test_no_request_without_core_en`  | Verify no request is generated if `core_en = 0`       |
| `test_waits_for_resp_valid`        | Verify `done` remains low until response              |
| `test_write_data_stable_until_ack` | Verify store data remains available until response    |
| `test_both_read_and_write_en`      | Define and verify behavior if both enables are high   |
| `test_reset_clears_state`          | Verify reset clears state and all important outputs   |

## Known pitfalls

Do not assume `req_valid` is level-held until response.

The LSU emits a one-cycle request pulse. The memory controller must capture it.

Do not treat `done` as sticky.

`done` pulses for one cycle when `resp_valid` arrives.

Do not start another transaction while the LSU is in `WAITING`.

The current LSU supports one outstanding transaction.

Do not enable inactive lanes.

The core must gate LSU enable with `active_mask[i]`.

Do not debug LSU read-data failure before checking the full memory path.

If `resp_valid = 1` but `resp_data = 0`, the issue may be upstream in the memory controller or packed response bus, not necessarily inside the LSU.

## Related integration tests

| Test                    | File                                           | What it proves                                                                   |
| ----------------------- | ---------------------------------------------- | -------------------------------------------------------------------------------- |
| `test_core_basic`       | `Src/core/test_core.py`                        | Core can complete a basic program                                                |
| `test_simt_relu`        | `Src/Top_level_GPU/test_top_level_gpu.py`      | LDR read data reaches R1, branch divergence works, and STR writes correct output |
| `test_gpu_axel_program` | `Src/Top_level_GPU/test_top_level_gpu.py`      | Top-level data memory request/response path works across a larger program        |
| `test_single_read`      | `Src/memory_controller/test_mem_controller.py` | Memory controller can route read responses back to LSU lanes                     |
| `test_round_robin`      | `Src/memory_controller/test_mem_controller.py` | Multiple LSU request lanes are serialized correctly                              |

## Last known status

```text
Status: passing

Verified with:
  cd ~/gpu-project
  make test

Current unit coverage:
  read
  write
  reset during read
```

## Design summary

`lsu` is a per-thread load/store transaction FSM. It receives an already-computed memory address, emits one-cycle requests to the memory controller, waits for response/acknowledgement, captures read data for load instructions, and pulses `done` to tell the scheduler that the memory transaction is complete.

The most important behavior is:

```text
req_valid is a one-cycle request pulse
done is a one-cycle completion pulse
read_write_switch uses 1 = read, 0 = write
mem_read_data updates only when a read response arrives
```
