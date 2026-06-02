# Memory Controller

## Overview

`mem_controller` is the per-core data-memory arbiter for the Tiny GPU. Each core has multiple SIMT threads, and each thread has its own LSU request lane. The memory controller accepts those per-thread LSU requests, buffers one-cycle request pulses, selects one request at a time using round-robin arbitration, forwards the selected request to the shared data memory interface, and routes the memory response back to the correct thread.

This module is required because all threads inside a core can request memory, but the core exposes only one serialized memory request interface.

## RTL schematic

![Memory Controller RTL schematic](../../assets/Images-Components/Memory%20Controller-page-00001.jpg)

## Source files

```text
Src/memory_controller/mem_controller.sv
Src/memory_controller/test_mem_controller.py
```

## Position in the GPU

```text
thread_gen[i].lsu_inst
        │
        │ req_valid[i], req_addr[i], req_rw[i], req_data[i]
        ▼
mem_controller
        │
        │ mem_req_valid, mem_req_addr, mem_req_rw, mem_req_data
        ▼
core / top-level data memory interface
        │
        │ mem_resp_valid, mem_resp_data
        ▼
mem_controller
        │
        │ resp_valid[i], resp_data[i]
        ▼
thread_gen[i].lsu_inst
```

In the full top-level path:

```text
register file / ALU
      │
      ▼
LSU per thread
      │
      ▼
mem_controller per core
      │
      ▼
top_level_gpu data memory interface
      │
      ▼
cocotb memory model / external memory
```

## Module declaration

```systemverilog
module mem_controller #(
    parameter THREADS_PER_CORE = 4
)(
    input  logic clk,
    input  logic rst,

    input  logic [THREADS_PER_CORE-1:0]       req_valid,
    input  logic [31:0]                       req_addr  [THREADS_PER_CORE-1:0],
    input  logic [THREADS_PER_CORE-1:0]       req_rw,
    input  logic [31:0]                       req_data  [THREADS_PER_CORE-1:0],

    output logic [THREADS_PER_CORE-1:0]       resp_valid,
    output logic [THREADS_PER_CORE-1:0][31:0] resp_data,

    output logic        mem_req_valid,
    output logic [31:0] mem_req_addr,
    output logic        mem_req_rw,
    output logic [31:0] mem_req_data,
    input  logic        mem_resp_valid,
    input  logic [31:0] mem_resp_data
);
```

## Parameter

| Parameter          | Default | Description                                                |
| ------------------ | ------: | ---------------------------------------------------------- |
| `THREADS_PER_CORE` |     `4` | Number of thread/LSU lanes served by one memory controller |

## Port description

| Port             | Direction | Type / Width                             | Description                                 |
| ---------------- | --------- | ---------------------------------------- | ------------------------------------------- |
| `clk`            | input     | `logic`                                  | Clock                                       |
| `rst`            | input     | `logic`                                  | Reset                                       |
| `req_valid`      | input     | `[THREADS_PER_CORE-1:0]`                 | Per-thread LSU request-valid pulse          |
| `req_addr`       | input     | `[31:0] req_addr [THREADS_PER_CORE-1:0]` | Per-thread memory address                   |
| `req_rw`         | input     | `[THREADS_PER_CORE-1:0]`                 | Per-thread read/write selector              |
| `req_data`       | input     | `[31:0] req_data [THREADS_PER_CORE-1:0]` | Per-thread write data                       |
| `resp_valid`     | output    | `[THREADS_PER_CORE-1:0]`                 | Per-thread response-valid pulse             |
| `resp_data`      | output    | `[THREADS_PER_CORE-1:0][31:0]`           | Packed per-thread response-data bus         |
| `mem_req_valid`  | output    | `logic`                                  | Serialized request-valid to external memory |
| `mem_req_addr`   | output    | `[31:0]`                                 | Serialized memory address                   |
| `mem_req_rw`     | output    | `logic`                                  | Serialized read/write selector              |
| `mem_req_data`   | output    | `[31:0]`                                 | Serialized write data                       |
| `mem_resp_valid` | input     | `logic`                                  | External memory response-valid              |
| `mem_resp_data`  | input     | `[31:0]`                                 | External memory response data               |

## Read/write convention

The design uses this convention:

```text
1 = read
0 = write
```

So:

```text
req_rw[i]   = 1 -> thread i requests a read
req_rw[i]   = 0 -> thread i requests a write

mem_req_rw  = 1 -> external memory read
mem_req_rw  = 0 -> external memory write
```

For writes, the selected thread’s `req_data[i]` is forwarded through `mem_req_data`.

For reads, `mem_resp_data` is returned to the selected thread through `resp_data[in_flight]`.

## Internal state

## FSM states

| State  | Meaning                                                                                                            |
| ------ | ------------------------------------------------------------------------------------------------------------------ |
| `IDLE` | No external memory request is currently waiting for a response. The controller scans for pending or live requests. |
| `WAIT` | One request has been issued to memory. The controller waits for `mem_resp_valid`.                                  |

## Main internal signals

| Signal         | Description                                        |            |
| -------------- | -------------------------------------------------- | ---------- |
| `rr_ptr`       | Round-robin starting pointer                       |            |
| `in_flight`    | Thread index currently waiting for memory response |            |
| `pending`      | Latched request-valid bits                         |            |
| `pending_addr` | Buffered request addresses                         |            |
| `pending_rw`   | Buffered read/write bits                           |            |
| `pending_data` | Buffered write data                                |            |
| `scan_valid`   | Combined request source: `pending                  | req_valid` |
| `next_thread`  | Thread selected by round-robin scan                |            |
| `found`        | Indicates that at least one request exists         |            |
| `sel_addr`     | Selected memory address                            |            |
| `sel_rw`       | Selected read/write bit                            |            |
| `sel_data`     | Selected write data                                |            |

## Why request buffering is required

The LSU emits `req_valid[i]` as a one-cycle pulse. If the controller is already in `WAIT` when another thread pulses `req_valid`, that request would be lost without buffering.

The pending buffer captures each request pulse:

```systemverilog
if (req_valid[i]) begin
    pending[i]      <= 1'b1;
    pending_addr[i] <= req_addr[i];
    pending_rw[i]   <= req_rw[i];
    pending_data[i] <= req_data[i];
end
```

When the selected request receives a memory response, the served thread is cleared:

```systemverilog
if (state == WAIT && mem_resp_valid) begin
    pending[in_flight] <= 1'b0;
end
```

## Operation

## 1. Request capture

On every clock cycle, the controller checks all thread request lanes. If `req_valid[i]` is high, it latches the request into the pending buffer:

```text
pending[i]      = 1
pending_addr[i] = req_addr[i]
pending_rw[i]   = req_rw[i]
pending_data[i] = req_data[i]
```

This protects one-cycle LSU pulses from being lost.

## 2. Request scan

The controller forms:

```systemverilog
assign scan_valid = pending | req_valid;
```

This means it can select either a previously buffered request or a same-cycle live request.

## 3. Round-robin selection

The controller scans from `rr_ptr` and selects the first valid thread.

Example for `THREADS_PER_CORE = 4`:

```text
rr_ptr = 0 -> scan T0, T1, T2, T3
rr_ptr = 1 -> scan T1, T2, T3, T0
rr_ptr = 2 -> scan T2, T3, T0, T1
rr_ptr = 3 -> scan T3, T0, T1, T2
```

After a thread is served, the pointer advances:

```systemverilog
rr_ptr <= PTR_W'(in_flight + 1);
```

## 4. Payload mux

If the selected thread’s `req_valid` is still live in the same cycle, the controller uses the live request payload:

```systemverilog
if (req_valid[next_thread]) begin
    sel_addr = req_addr[next_thread];
    sel_rw   = req_rw[next_thread];
    sel_data = req_data[next_thread];
end
```

Otherwise, it uses the buffered request payload:

```systemverilog
else begin
    sel_addr = pending_addr[next_thread];
    sel_rw   = pending_rw[next_thread];
    sel_data = pending_data[next_thread];
end
```

## 5. External memory request

In `IDLE`, when a request is found:

```systemverilog
in_flight     <= next_thread;

mem_req_valid <= 1'b1;
mem_req_addr  <= sel_addr;
mem_req_rw    <= sel_rw;
mem_req_data  <= sel_data;

state         <= WAIT;
```

Only one external memory request is in flight at a time.

## 6. Memory response

In `WAIT`, when `mem_resp_valid` is high:

```systemverilog
resp_valid[in_flight] <= 1'b1;
resp_data[in_flight]  <= mem_resp_data;

rr_ptr                <= PTR_W'(in_flight + 1);
mem_req_valid         <= 1'b0;
state                 <= IDLE;
```

The selected thread receives a one-cycle `resp_valid` pulse. For reads, it also receives the returned memory data through `resp_data[in_flight]`.

## Packed response-data bus

`resp_data` is intentionally declared as a packed 2D bus:

```systemverilog
output logic [THREADS_PER_CORE-1:0][31:0] resp_data
```

This matches the packed internal LSU response bus in `core.sv`:

```systemverilog
logic [THREADS_PER_CORE-1:0][31:0] lsu_resp_data;
```

Thread `i` receives:

```systemverilog
resp_data[i]
```

This packed shape is important. Do not change it back to the old unpacked form:

```systemverilog
output logic [31:0] resp_data [THREADS_PER_CORE-1:0]
```

That old unpacked form caused an integration failure where `resp_valid` reached the LSU, but the corresponding `resp_data` lane stayed zero.

## Fixed bug: packed/unpacked response mismatch

A previous version used this unpacked response-data port:

```systemverilog
output logic [31:0] resp_data [THREADS_PER_CORE-1:0]
```

But `core.sv` used this packed internal response bus:

```systemverilog
logic [THREADS_PER_CORE-1:0][31:0] lsu_resp_data;
```

This mismatch caused the following behavior during `test_simt_relu`:

```text
mc_resp_data=5
mc_out_data0=5
lsu0_resp_v=1
lsu0_resp_data=0
lsu0_read_data=0
```

Meaning:

```text
memory response entered mem_controller correctly
mem_controller appeared to hold the correct output lane
LSU received resp_valid
LSU did not receive the correct resp_data
```

This broke `LDR` writeback. The ReLU test was reading correct memory values, but `R1` stayed zero in all threads.

The fix was:

```systemverilog
output logic [THREADS_PER_CORE-1:0][31:0] resp_data
```

After the fix, the response path became:

```text
mc_resp_data=5
lsu0_resp_v=1
lsu0_resp_data=5
lsu0_read_data=5
```

Then `R1` loaded correctly:

```text
R1s=[5, -3, 8, -1]
```

And `test_simt_relu` produced:

```text
mem[4] = 5
mem[5] = 0
mem[6] = 8
mem[7] = 0
```

## Cocotb testing notes

Because `resp_data` is packed, cocotb should not directly index it like this:

```python
dut.resp_data[0].value
```

Instead, read the full packed value and manually extract the 32-bit lane:

```python
THREADS_PER_CORE = 4
WORD_W = 32

def resp_word(dut, thread_id):
    packed = int(dut.resp_data.value)
    return (packed >> (thread_id * WORD_W)) & 0xFFFFFFFF
```

Use:

```python
got = resp_word(dut, 0)
got_t1 = resp_word(dut, 1)
```

This avoids packed-object indexing issues in cocotb and keeps the test aligned with the RTL bus shape.

## Timing assumptions

The controller assumes:

```text
- LSU req_valid[i] is a one-cycle pulse.
- req_addr[i], req_rw[i], and req_data[i] are valid when req_valid[i] is high.
- Only one external memory request is in flight at a time.
- mem_resp_valid means mem_resp_data is valid in the same cycle.
- resp_valid[in_flight] is a one-cycle pulse.
- The target LSU captures resp_data[in_flight] when resp_valid[in_flight] is high.
```

## Reset behavior

On reset:

```text
state         -> IDLE
rr_ptr        -> 0
in_flight     -> 0
mem_req_valid -> 0
mem_req_addr  -> 0
mem_req_rw    -> 0
mem_req_data  -> 0
resp_valid    -> 0
pending       -> 0
pending_rw    -> 0
pending_addr  -> 0
pending_data  -> 0
resp_data     -> 0
```

## Verification

Unit test file:

```text
Src/memory_controller/test_mem_controller.py
```

## `test_single_read`

Checks:

```text
T0 issues a read.
Controller forwards address 42 to memory.
Memory responds with 0xDEADBEEF.
resp_valid[0] pulses.
resp_data lane 0 contains 0xDEADBEEF.
```

## `test_single_write`

Checks:

```text
T1 issues a write.
Controller forwards address 10 and data 99.
Memory acknowledges.
resp_valid[1] pulses.
```

## `test_round_robin`

Checks:

```text
T0 and T1 request simultaneously.
T0 is served first because rr_ptr starts at 0.
rr_ptr advances.
T1 is served next.
Both response lanes contain the expected data.
```

## Related integration tests

| Test                    | File                                      | What it proves                                                                |
| ----------------------- | ----------------------------------------- | ----------------------------------------------------------------------------- |
| `test_core_basic`       | `Src/core/test_core.py`                   | Core-level memory path still works                                            |
| `test_simt_relu`        | `Src/Top_level_GPU/test_top_level_gpu.py` | LDR data reaches R1, branch divergence works, STR writes expected ReLU output |
| `test_gpu_axel_program` | `Src/Top_level_GPU/test_top_level_gpu.py` | Full top-level AXEL program completes                                         |

## Known pitfalls

Do not remove the request buffer:

```systemverilog
pending
pending_addr
pending_rw
pending_data
```

The LSUs produce one-cycle request pulses, so requests can be lost without buffering.

Do not change `resp_data` back to unpacked unless all connected modules and cocotb tests are updated carefully.

Do not use direct cocotb indexing on packed `resp_data`.

Do not assume `mem_req_valid` means a new request every cycle. The controller holds one request while waiting for `mem_resp_valid`.

Do not debug SIMT branch divergence before confirming the LDR path works. If `resp_data` is wrong, `R1` stays zero, `CMP` sees zero, and branch behavior becomes misleading.

## Last known status

```text
Status: passing

Verified with:
  cd ~/gpu-project
  make test

Important fixed bug:
  Packed/unpacked response-data mismatch between mem_controller and core LSU response path.
```

## Design summary

`mem_controller` is a serialized memory arbiter for one GPU core. It accepts one-cycle LSU request pulses from multiple threads, buffers them, selects requests using round-robin arbitration, forwards one request at a time to memory, and returns the response to the correct thread.

The most important implementation detail is that `resp_data` must remain packed:

```systemverilog
logic [THREADS_PER_CORE-1:0][31:0] resp_data
```

This keeps the response-data shape aligned with `core.sv` and avoids the previously fixed LSU read-data bug.
