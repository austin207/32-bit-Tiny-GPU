"""
pyaxel — Python runtime for the 32-bit Tiny GPU

Loads .axelbin kernel binaries and runs them via cocotb RTL simulation.

Example:
    import pyaxel

    gpu = pyaxel.GPU()
    gpu.load("assembler/builds/bin/phase6_simt_relu.axelbin")
    gpu.run()

    result = gpu.read_mem(4, 4)
    print(result)   # [5, 0, 8, 0]
"""

from .gpu import GPU

__all__ = ['GPU']
__version__ = '0.1.0'