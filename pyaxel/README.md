# PyAXEL Runtime

Python host-side runtime for the 32-bit Tiny GPU.

Loads `.axelbin` kernel binaries and runs them via cocotb RTL simulation
of the SystemVerilog GPU. Results are read back from simulated data memory
after `kernel_done` asserts.

---

## Usage

```python
import pyaxel

gpu = pyaxel.GPU()
gpu.load("assembler/builds/bin/phase6_simt_relu.axelbin")
gpu.run()

result = gpu.read_mem(4, 4)   # read 4 words starting at address 4
print(result)                  # [5, 0, 8, 0]
```

---

## API

### `GPU(num_cores=4, threads_per_core=4, project_root=None)`

Create a GPU runtime instance. Parameters must match the RTL configuration.

### `gpu.load(path)`

Load a `.axelbin` kernel binary. The binary carries `num_blocks`, `blockDim`,
instructions, and initial data memory. Returns `self` for chaining.

### `gpu.write_mem(addr, values)`

Override data memory before `run()`. Overrides are applied on top of the
binary's embedded data segment, so you can run the same kernel with
different inputs without recompiling.

```python
gpu.load("kernel.axelbin")
gpu.write_mem(0, [10, -5, 3, -2])   # override input values
gpu.run()
```

### `gpu.run(timeout_cycles=10000, verbose=False)`

Run the kernel via cocotb RTL simulation. Blocks until completion.
Set `verbose=True` to see full cocotb output. Returns `self` for chaining.

### `gpu.read_mem(addr, count=1)`

Read data memory words as signed 32-bit integers after `run()`.
Returns a single `int` if `count=1`, or a `list` if `count>1`.

### `gpu.read_mem_raw(addr, count=1)`

Read data memory words as unsigned 32-bit integers.

### `gpu.dump_mem(start=0, count=32)`

Print a region of data memory in hex and decimal.

### `gpu.cycles`

Cycle count from the last `run()`, or `None` if not yet run.

### `gpu.info()`

Print full kernel binary info — header fields, instruction listing,
data segment contents.

---

## How it works

```
gpu.run()
  │
  ├── writes kernel path + result path to temp files
  ├── sets COCOTB_TEST_FILTER=test_pyaxel_runner
  ├── spawns: make (in Src/Top_level_GPU/)
  │     │
  │     └── cocotb runs test_pyaxel_runner
  │           ├── loads .axelbin
  │           ├── drives DCR from binary header
  │           ├── runs simulation until kernel_done
  │           └── writes data_mem to result JSON
  │
  └── reads result JSON → populates self._result
```

The testbench hook (`test_pyaxel_runner`) lives in
`Src/Top_level_GPU/test_top_level_gpu.py` alongside the standard tests.
It is only invoked when `COCOTB_TEST_FILTER=test_pyaxel_runner` is set —
it does not run during normal `make test`.

---

## Example — SIMT ReLU

```python
import pyaxel

gpu = pyaxel.GPU()
gpu.load("assembler/builds/bin/phase6_simt_relu.axelbin")
gpu.run()

outputs = gpu.read_mem(4, 4)
print(f"ReLU outputs: {outputs}")
# ReLU outputs: [5, 0, 8, 0]

print(f"Completed in {gpu.cycles} cycles")
```

---

## Example — override inputs

```python
import pyaxel

gpu = pyaxel.GPU()
gpu.load("assembler/builds/bin/phase6_simt_relu.axelbin")
gpu.write_mem(0, [3, -7, 0, 12])   # new inputs
gpu.run()

outputs = gpu.read_mem(4, 4)
print(outputs)   # [3, 0, 0, 12]
```

---

## Requirements

- Python 3.8+
- cocotb environment active (`source ~/cocotb-env/bin/activate`)
- Icarus Verilog installed
- `.axelbin` file built via `make` in `assembler/`