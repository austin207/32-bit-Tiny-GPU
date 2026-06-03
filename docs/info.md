## How it works

This Tiny Tapeout project is a reduced hardware demonstration derived from the larger 32-bit Tiny GPU project.

The full project includes a custom 32-bit ISA, AXEL C assembler, cocotb verification, SIMT branch divergence, warp-stack reconvergence, round-robin memory arbitration, FPGA targeting, and a Sky130A OpenLane GDS flow.

The Tiny Tapeout version is intentionally reduced to fit the Tiny Tapeout tile area. It demonstrates the verified SIMT ReLU result pattern from the main GPU project:

- input: `[5, -3, 8, -1]`
- output: `[5, 0, 8, 0]`

The output pins encode completion status, result bits, heartbeat, debug, and running state.

## How to test

Hold reset low, then release reset.

Set `ui_in[0]` high to start the demo.

After the internal counter reaches the completion point:

- `uo_out[0]` goes high to indicate done
- `uo_out[1]` and `uo_out[3]` go high, representing the non-zero ReLU lanes
- `uo_out[5]` provides a heartbeat/debug counter bit
- `uo_out[7]` indicates running status before completion

Expected final output pattern:

```text
uo_out[4:1] = 0101
uo_out[0]   = 1
```

## External hardware

No external hardware is required.