"""
pyaxel/gpu.py — PyAXEL runtime, cocotb subprocess backend

Usage:
    import pyaxel

    gpu = pyaxel.GPU()
    gpu.load("assembler/builds/bin/phase6_simt_relu.axelbin")
    gpu.run()

    result = gpu.read_mem(4, 4)   # [5, 0, 8, 0]
    print(result)

The .axelbin binary carries num_blocks, blockDim, instructions, and initial
data memory. GPU.run() drives a cocotb simulation of the RTL and captures
the final data memory state after kernel_done asserts.
"""

import os
import sys
import json
import tempfile
import subprocess

# Add assembler/tools to path for axelbin loader
_TOOLS_PATH = os.path.join(os.path.dirname(__file__), '../assembler/tools')
if os.path.isdir(_TOOLS_PATH) and _TOOLS_PATH not in sys.path:
    sys.path.insert(0, _TOOLS_PATH)

from axelbin import load_axelbin, dump_axelbin


class GPU:
    """
    PyAXEL GPU runtime.

    Loads a .axelbin kernel binary and runs it via cocotb RTL simulation.
    Results are read back from the simulated data memory after completion.
    """

    def __init__(self, num_cores=4, threads_per_core=4, project_root=None):
        """
        Args:
            num_cores:         number of GPU cores (must match RTL config)
            threads_per_core:  threads per core (must match RTL config)
            project_root:      path to gpu-project root (auto-detected if None)
        """
        self.num_cores        = num_cores
        self.threads_per_core = threads_per_core

        if project_root is None:
            self.project_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), '..')
            )
        else:
            self.project_root = os.path.abspath(project_root)

        self._kernel           = None
        self._kernel_path      = None
        self._mem_overrides    = {}   # addr → unsigned 32-bit value
        self._result           = None
        self._last_cycles      = None

    # ── Kernel loading ────────────────────────────────────────────────────────

    def load(self, path):
        """
        Load a .axelbin kernel binary.

        Args:
            path: path to .axelbin file (absolute or relative to CWD)

        Returns:
            self (for chaining)
        """
        abs_path = os.path.abspath(path)
        self._kernel      = load_axelbin(abs_path)
        self._kernel_path = abs_path
        self._mem_overrides = {}
        self._result        = None
        self._last_cycles   = None

        print(f"pyaxel: loaded {os.path.basename(path)}")
        print(f"  num_blocks={self._kernel['num_blocks']}  "
              f"blockDim={self._kernel['blockDim']}  "
              f"instructions={self._kernel['text_words']}  "
              f"data_words={self._kernel['data_words']}")
        return self

    def write_mem(self, addr, values):
        """
        Override data memory words before run().

        Overrides are applied on top of any data segment embedded in the
        .axelbin, so you can run the same binary with different inputs
        without modifying the kernel source.

        Args:
            addr:   starting address
            values: int or list of int (signed or unsigned 32-bit)

        Returns:
            self (for chaining)
        """
        if isinstance(values, int):
            values = [values]
        for i, v in enumerate(values):
            self._mem_overrides[addr + i] = v & 0xFFFFFFFF
        return self

    # ── Simulation ────────────────────────────────────────────────────────────

    def run(self, timeout_cycles=10000, verbose=False):
        """
        Run the kernel via cocotb RTL simulation.

        Spawns a cocotb subprocess running test_pyaxel_runner in
        Src/Top_level_GPU/. Blocks until the simulation completes.
        Final data memory state is captured and stored for read_mem().

        Args:
            timeout_cycles: max simulation cycles before failure
            verbose:        if True, print full cocotb output

        Returns:
            self (for chaining)

        Raises:
            RuntimeError if no kernel is loaded or simulation fails
        """
        if self._kernel is None:
            raise RuntimeError("pyaxel: no kernel loaded — call load() first")

        # Temp files for IPC between PyAXEL and the cocotb testbench
        result_fd,    result_path    = tempfile.mkstemp(suffix='.json', prefix='pyaxel_result_')
        overrides_fd, overrides_path = tempfile.mkstemp(suffix='.json', prefix='pyaxel_overrides_')
        os.close(result_fd)
        os.close(overrides_fd)

        try:
            # Write overrides to temp file
            with open(overrides_path, 'w') as f:
                json.dump({str(k): v for k, v in self._mem_overrides.items()}, f)

            # Environment variables read by test_pyaxel_runner
            env = os.environ.copy()
            env['PYAXEL_KERNEL']        = self._kernel_path
            env['PYAXEL_RESULT']        = result_path
            env['PYAXEL_OVERRIDES']     = overrides_path
            env['PYAXEL_TIMEOUT']       = str(timeout_cycles)
            env['COCOTB_TEST_FILTER']   = 'test_pyaxel_runner'

            sim_dir = os.path.join(self.project_root, 'Src', 'Top_level_GPU')

            print("pyaxel: starting simulation...")

            proc = subprocess.run(
                ['make'],
                cwd=sim_dir,
                env=env,
                capture_output=not verbose,
                text=True
            )

            if proc.returncode != 0:
                if not verbose:
                    # Show last 3000 chars of output on failure
                    output = (proc.stdout or '') + (proc.stderr or '')
                    tail = output[-3000:] if len(output) > 3000 else output
                    print(tail)
                raise RuntimeError("pyaxel: simulation failed (see output above)")

            # Read result JSON written by test_pyaxel_runner
            if not os.path.isfile(result_path) or os.path.getsize(result_path) == 0:
                raise RuntimeError("pyaxel: result file not written by testbench")

            with open(result_path) as f:
                raw = json.load(f)

            # Pull out the cycle count metadata key
            self._last_cycles = raw.pop('__cycles__', None)
            self._result = {int(k): v for k, v in raw.items()}

            print(f"pyaxel: kernel completed"
                  + (f" in {self._last_cycles} cycles" if self._last_cycles else ""))
            return self

        finally:
            for p in (result_path, overrides_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    # ── Result access ─────────────────────────────────────────────────────────

    def read_mem(self, addr, count=1):
        """
        Read data memory words as signed 32-bit integers.

        Args:
            addr:  starting address
            count: number of words to read (default 1)

        Returns:
            single int if count=1, list of int if count>1
        """
        self._check_result()
        values = [self._to_signed(self._result.get(addr + i, 0))
                  for i in range(count)]
        return values if count > 1 else values[0]

    def read_mem_raw(self, addr, count=1):
        """
        Read data memory words as unsigned 32-bit integers.

        Returns:
            single int if count=1, list of int if count>1
        """
        self._check_result()
        values = [self._result.get(addr + i, 0) for i in range(count)]
        return values if count > 1 else values[0]

    def dump_mem(self, start=0, count=32):
        """Print a region of data memory after run()."""
        self._check_result()
        print(f"Data memory [{start}..{start + count - 1}]:")
        for i in range(count):
            addr   = start + i
            raw    = self._result.get(addr, 0)
            signed = self._to_signed(raw)
            print(f"  [{addr:3d}]  {raw:#010x}  ({signed})")

    @property
    def cycles(self):
        """Cycle count from the last run(), or None if not yet run."""
        return self._last_cycles

    # ── Kernel info ───────────────────────────────────────────────────────────

    def info(self):
        """Print full kernel binary info (header + disassembly)."""
        if self._kernel is None:
            print("pyaxel: no kernel loaded")
            return
        dump_axelbin(self._kernel_path)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _check_result(self):
        if self._result is None:
            raise RuntimeError("pyaxel: no result — call run() first")

    @staticmethod
    def _to_signed(v):
        v &= 0xFFFFFFFF
        return v - 0x100000000 if v >= 0x80000000 else v