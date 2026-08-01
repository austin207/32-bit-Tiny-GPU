import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from .common import init_bus, launch_kernel
from .memory_models import program_memory_model, data_memory_model


def load_hex_file(path):
    instructions = {}
    with open(path) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if line:
                instructions[i] = int(line, 16)
    return instructions


BUILD_HEX = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../assembler/builds/hex")
)


@cocotb.test()
async def test_axelcc_chain(dut):
    """
    Proves sequential kernel launches on real GPU RTL: three separate
    axelcc-compiled programs run back to back, each launched fresh via
    launch_kernel() (full DUT reset between stages), sharing one
    data_memory dict the whole way through -- this is the mechanism Phase
    5 (attention/transformer kernels: QK^T, softmax, then x V) needs, and
    it's already provable with axelcc-compiled kernels specifically, not
    just hand-assembled .axelbin phase kernels (see
    test_phase16_digit64_classifier for the hand-assembled precedent).

    stage1: mem[10] = mem[0] + mem[1]
    stage2: mem[11] = mem[10] * 2
    stage3: mem[12] = mem[11] + mem[0]

    mem[0]=3, mem[1]=4:
      stage1 -> mem[10] = 7
      stage2 -> mem[11] = 14
      stage3 -> mem[12] = 17
    """
    instr1 = load_hex_file(os.path.join(BUILD_HEX, "test_chain1.hex"))
    instr2 = load_hex_file(os.path.join(BUILD_HEX, "test_chain2.hex"))
    instr3 = load_hex_file(os.path.join(BUILD_HEX, "test_chain3.hex"))

    data_memory = {0: 3, 1: 4}

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions_ref = [instr1]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    cyc1 = await launch_kernel(dut, instructions_ref, instr1)
    assert cyc1 is not None, "TIMEOUT: chain stage1 did not finish"
    got10 = data_memory.get(10)
    assert got10 == 7, f"stage1: mem[10]={got10}, expected 7"

    cyc2 = await launch_kernel(dut, instructions_ref, instr2)
    assert cyc2 is not None, "TIMEOUT: chain stage2 did not finish"
    got11 = data_memory.get(11)
    assert got11 == 14, f"stage2: mem[11]={got11}, expected 14"

    cyc3 = await launch_kernel(dut, instructions_ref, instr3)
    assert cyc3 is not None, "TIMEOUT: chain stage3 did not finish"
    got12 = data_memory.get(12)
    assert got12 == 17, f"stage3: mem[12]={got12}, expected 17"

    cocotb.log.info(
        f"axelcc chain PASSED: mem[10]={got10} mem[11]={got11} mem[12]={got12} "
        f"cycles=({cyc1},{cyc2},{cyc3})"
    )
