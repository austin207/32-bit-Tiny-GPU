# Fetcher

## Overview

`fetcher` is the instruction-fetch unit used inside each GPU core.

It receives the current program counter value from the core, sends a request to program memory, waits for the instruction response, captures the returned instruction, and pulses `done` when the instruction has been fetched.

The fetcher is a small two-state sequential FSM:

```text
IDLE -> WAITING -> IDLE
```

It does not decode or execute instructions. Its only job is to turn a core fetch enable plus PC value into a program-memory request and return one 32-bit instruction.

## RTL schematic

![Fetcher RTL schematic](../../assets/Images-Components/Fetcher-page-00001.jpg)

## Source files

```text
Src/fetcher/fetcher.sv
Src/fetcher/test_fetcher.py
```

## Position in the GPU

The fetcher sits between the per-core PC selection logic and the program memory interface.

```text
active_pc / pc_value
        │
        ▼
fetcher
        │
        ├── req_valid, req_addr -> program memory
        │
        └── instruction, done   -> core instruction latch / scheduler
```

In the full core path:

```text
PC / active_pc
      │
      ▼
fetcher
      │
      ▼
instruction_raw
      │
      ▼
instruction latch in core.sv
      │
      ▼
decoder
```

## Module declaration

```systemverilog
module fetcher (
    input logic clk,
    input logic rst,

    input logic core_en,
    input logic [31:0] pc_value,
    output logic [31:0] instruction,
    output logic done,

    output logic req_valid,
    output logic [31:0] req_addr,
    input logic resp_valid,
    input logic [31:0] resp_data
);
```

## Port description

| Port          | Direction | Width | Description                                          |
| ------------- | --------- | ----: | ---------------------------------------------------- |
| `clk`         | input     |     1 | Clock                                                |
| `rst`         | input     |     1 | Reset                                                |
| `core_en`     | input     |     1 | Fetch enable from scheduler                          |
| `pc_value`    | input     |    32 | Program counter value / instruction address to fetch |
| `instruction` | output    |    32 | Fetched instruction returned from program memory     |
| `done`        | output    |     1 | One-cycle pulse indicating fetch completion          |
| `req_valid`   | output    |     1 | Program memory request-valid                         |
| `req_addr`    | output    |    32 | Program memory request address                       |
| `resp_valid`  | input     |     1 | Program memory response-valid                        |
| `resp_data`   | input     |    32 | Program memory response data / instruction word      |

## FSM states

| State     | Encoding | Meaning                                                           |
| --------- | -------: | ----------------------------------------------------------------- |
| `IDLE`    |   `1'b0` | No fetch is currently in progress. Waits for `core_en`.           |
| `WAITING` |   `1'b1` | A program memory request has been issued. Waits for `resp_valid`. |

## Operation

## 1. Reset

On reset, the fetcher returns to a clean idle state:

```systemverilog
state       <= IDLE;
instruction <= 32'b0;
req_valid   <= 0;
req_addr    <= 32'b0;
done        <= 0;
```

Reset is asynchronous because the sensitivity list is:

```systemverilog
always_ff @(posedge clk or posedge rst)
```

## 2. Request issue

When the fetcher is in `IDLE` and `core_en` is asserted:

```systemverilog
req_addr  <= pc_value;
req_valid <= 1;
done      <= 0;
state     <= WAITING;
```

This sends a one-cycle program-memory request for the current PC value.

Example:

```text
core_en  = 1
pc_value = 5

result:
req_valid = 1
req_addr  = 5
state     = WAITING
```

## 3. Waiting for memory

In `WAITING`, the fetcher waits until program memory asserts:

```text
resp_valid = 1
```

While waiting, `done` remains `0`.

## 4. Response capture

When `resp_valid` is asserted:

```systemverilog
instruction <= resp_data;
done        <= 1;
state       <= IDLE;
```

`done` pulses for one cycle to tell the scheduler/core that instruction fetch is complete.

## Current RTL implementation

```systemverilog
typedef enum logic { 
    IDLE = 1'b0,
    WAITING = 1'b1
 } state_t;

state_t state;

always_ff @( posedge clk or posedge rst ) begin
    if (rst) begin
        state <= IDLE;
        instruction <= 32'b0;
        req_valid <= 0;
        req_addr <= 32'b0;
        done <= 0;
    end else begin
        req_valid <= 0;
        done <= 0;

        case (state)
            IDLE : begin
                if (core_en) begin
                    req_addr <= pc_value;
                    req_valid <= 1;
                    done <= 0;
                    state <= WAITING;
                end
            end

            WAITING : begin
                if (resp_valid) begin
                    instruction <= resp_data;
                    done <= 1;
                    state <= IDLE;
                end 
            end

            default: ;
        endcase        
    end
end
```

## Timing behavior

The fetcher uses pulse-style handshaking.

### Request side

`req_valid` is asserted for one cycle when the fetch request is issued.

```text
cycle N:
  state     = IDLE
  core_en   = 1
  pc_value  = selected PC

cycle N+1:
  req_valid = 1
  req_addr  = pc_value
  state     = WAITING
```

### Response side

`done` is asserted for one cycle when `resp_valid` is observed.

```text
cycle M:
  state      = WAITING
  resp_valid = 1
  resp_data  = instruction word

cycle M+1:
  instruction = resp_data
  done        = 1
  state       = IDLE
```

## Interaction with core instruction latch

Inside `core.sv`, the fetcher output is connected to `instruction_raw`:

```systemverilog
fetcher fetch (
    .clk         (clk),
    .rst         (rst),
    .core_en     (fetcher_en),
    .pc_value    (active_pc),
    .instruction (instruction_raw),
    .done        (done),
    .req_valid   (prog_mem_req_valid),
    .req_addr    (prog_mem_req_addr),
    .resp_valid  (prog_mem_resp_valid),
    .resp_data   (prog_mem_resp_data)
);
```

The core then latches `instruction_raw` when `done` is high:

```systemverilog
always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        instruction <= 32'b0;
    end else if (done) begin
        instruction <= instruction_raw;
    end
end
```

This is important because the fetched instruction must remain stable through the full instruction lifecycle:

```text
DECODE -> REQUEST -> WAIT -> EXECUTE -> UPDATE
```

The fetcher only owns the fetch transaction. The core instruction latch owns instruction stability after fetch completion.

## Program memory interface

The fetcher exposes a simple request/response interface:

```text
request:
  req_valid
  req_addr

response:
  resp_valid
  resp_data
```

The current fetcher assumes:

- req_addr is sampled by memory when req_valid is high.
- resp_data is valid when resp_valid is high.
- only one fetch request is outstanding at a time.

## Timing assumptions

The fetcher assumes:

- `core_en` is asserted by the scheduler when a fetch should begin.
- `pc_value` is valid when `core_en` is asserted.
- Program memory samples `req_addr` when `req_valid` is high.
- Program memory later returns `resp_valid` with the instruction on `resp_data`.
- `resp_data` is valid in the same cycle as `resp_valid`.
- The scheduler watches `done` to know fetch completion.

## Reset behavior

On reset:

```text
state       -> IDLE
instruction -> 0
req_valid   -> 0
req_addr    -> 0
done        -> 0
```

If reset occurs during a fetch, the outstanding transaction is abandoned from the fetcher’s point of view, and the fetcher returns to `IDLE`.

## Verification

Unit test file:

```text
Src/fetcher/test_fetcher.py
```

## Current tests

| Test                      | What it checks                                                              |
| ------------------------- | --------------------------------------------------------------------------- |
| `test_basic_fetch`        | A request is issued for `pc_value`, response is captured, and `done` pulses |
| `test_memory_mutlicycle`  | Fetcher waits across multiple cycles until `resp_valid` arrives             |
| `test_reset_during_fetch` | Reset during an outstanding fetch clears request/done/instruction state     |

## `test_basic_fetch`

This test performs a single fetch.

Stimulus:

```text
pc_value = 5
core_en  = 1
resp_valid = 1
resp_data  = 0xDEADBEEF
```

Expected behavior:

```text
req_valid   = 1
req_addr    = 5
instruction = 0xDEADBEEF
done        = 1
```

## `test_memory_mutlicycle`

This test verifies that fetch can wait for delayed program memory.

Stimulus:

```text
core_en = 1
pc_value = 5
resp_valid = 0 for several cycles
then resp_valid = 1
resp_data = 0xCAFEBABE
```

Expected behavior:

```text
done remains 0 while resp_valid is 0
instruction becomes 0xCAFEBABE when response arrives
done pulses when response arrives
```

Note: the test name currently contains a typo:

```text
test_memory_mutlicycle
```

It should probably be renamed later to:

```text
test_memory_multicycle
```

## `test_reset_during_fetch`

This test verifies reset behavior while a fetch is in progress.

Stimulus:

```text
core_en = 1
pc_value = 5
req_valid is asserted
rst is asserted before response arrives
```

Expected behavior after reset:

```text
req_valid   = 0
done        = 0
instruction = 0
```

## Recommended additional tests

| Test                               | Purpose                                                              |
| ---------------------------------- | -------------------------------------------------------------------- |
| `test_no_fetch_without_core_en`    | Verify no request is issued when `core_en = 0`                       |
| `test_req_valid_one_cycle_pulse`   | Verify `req_valid` does not stay high while waiting                  |
| `test_done_one_cycle_pulse`        | Verify `done` clears after one cycle                                 |
| `test_back_to_back_fetches`        | Verify fetcher can fetch another instruction after returning to IDLE |
| `test_pc_value_latched_on_request` | Verify changing `pc_value` while waiting does not change `req_addr`  |
| `test_response_ignored_in_idle`    | Verify stray `resp_valid` in IDLE does not corrupt instruction       |
| `test_reset_clears_state`          | Verify reset clears all outputs and returns to IDLE                  |

## Known pitfalls

Do not assume the fetcher holds `req_valid` until memory responds.

`req_valid` is a one-cycle request pulse. The program memory model should capture `req_addr` when `req_valid` is high.

Do not decode `instruction` directly without considering stability.

In the full core, the fetched instruction is latched on `done`. The decoder uses the core’s latched instruction, not a raw transient memory response.

Do not start a second fetch while the fetcher is in `WAITING`.

The current FSM handles one outstanding fetch at a time.

Do not assume `done` is sticky.

`done` is cleared every cycle by default and pulses only when a response is captured.

Do not ignore reset behavior during fetch.

Reset aborts the current fetch state and clears `instruction`, `req_valid`, `req_addr`, and `done`.

## Related integration tests

| Test                    | File                                      | What it proves                                                   |
| ----------------------- | ----------------------------------------- | ---------------------------------------------------------------- |
| `test_core_basic`       | `Src/core/test_core.py`                   | Core can fetch and execute a small program                       |
| `test_gpu_axel_program` | `Src/Top_level_GPU/test_top_level_gpu.py` | Top-level program memory fetch path works over many instructions |
| `test_simt_relu`        | `Src/Top_level_GPU/test_top_level_gpu.py` | Fetch path supports branch/SYNC/ReLU program execution           |

## Last known status

```text
Status: passing

Verified with:
  cd ~/gpu-project
  make test

Current unit coverage:
  basic fetch
  multicycle memory response
  reset during fetch
```

## Design summary

`fetcher` is a two-state sequential instruction-fetch FSM. It accepts a fetch enable and PC value, sends a one-cycle program-memory request, waits for `resp_valid`, captures the returned instruction, pulses `done`, and returns to `IDLE`.

The most important behavior is:

```text
req_valid is a one-cycle request pulse
done is a one-cycle completion pulse
instruction is updated only when resp_valid is received
```
