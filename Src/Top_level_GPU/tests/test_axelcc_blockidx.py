import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from .common import init_bus, launch_kernel, u32_to_signed
from .memory_models import program_memory_model, data_memory_model


def load_hex_file(path):
    instructions = {}
    with open(path) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if line:
                instructions[i] = int(line, 16)
    return instructions


HEX_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "../../../assembler/builds/hex/test_blockidx.hex"
    )
)


@cocotb.test()
async def test_axelcc_blockidx(dut):
    """
    De-risking test for `blockIdx` combined with num_blocks > 1: every
    kernel in this repo so far launched with num_blocks=1, so blockIdx has
    never been exercised as a real per-block register read across multiple
    dispatched blocks. The upcoming DS-CNN depthwise/pointwise/maxpool
    kernels rely on `channel = blockIdx*4 + threadIdx` to parallelize
    across channel counts larger than one block's threadDim, so this proves
    the register read + multi-block dispatch works on real RTL first.

    num_blocks=4, blockDim=4 (16 threads total, matching depthwise block0's
    channel count C=16) -> mem[0..15] = [0, 1, ..., 15], each thread storing
    its own globally-unique bid*4+tid at that same address.
    """
    instructions = load_hex_file(HEX_PATH)
    data_memory = {}

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    cyc = await launch_kernel(
        dut, instructions_ref, instructions, num_blocks=4, blockDim=4
    )
    assert cyc is not None, "TIMEOUT: blockidx_test did not finish"

    expected = {addr: addr for addr in range(16)}
    got = {addr: u32_to_signed(data_memory.get(addr)) for addr in expected}

    assert got == expected, f"blockidx_test: got={got}, expected={expected}"
    cocotb.log.info(f"axelcc blockidx_test PASSED: {got}")
