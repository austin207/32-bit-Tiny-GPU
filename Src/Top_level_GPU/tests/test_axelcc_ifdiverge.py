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
        "../../../assembler/builds/hex/test_ifdiverge.hex"
    )
)


@cocotb.test()
async def test_axelcc_ifdiverge(dut):
    """
    Regression for the STMT_IF double-pop bug fixed this session: real
    cross-thread if-divergence (different threads taking different branches
    of the SAME if, at the SAME time) used to corrupt every thread but the
    one core.sv's active_pc mux happened to select. Each row's max sits at
    a different column, so all three sequential ifs genuinely split the
    4 threads into mixed taken/not-taken groups.

    row0=[10,1,2,3]  row1=[1,10,2,3]  row2=[1,2,10,3]  row3=[1,2,3,10]
    expected max per row: 10, 10, 10, 10
    """
    rows = [
        [10, 1, 2, 3],
        [1, 10, 2, 3],
        [1, 2, 10, 3],
        [1, 2, 3, 10],
    ]
    data_memory = {}
    for i in range(4):
        for j in range(4):
            data_memory[i * 4 + j] = rows[i][j] & 0xFFFFFFFF

    instructions = load_hex_file(HEX_PATH)

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    cyc = await launch_kernel(dut, instructions_ref, instructions, blockDim=4)
    assert cyc is not None, "TIMEOUT: ifdiverge did not finish"

    got = [u32_to_signed(data_memory.get(16 + i)) for i in range(4)]
    assert got == [10, 10, 10, 10], f"ifdiverge: got={got}, expected [10,10,10,10]"

    cocotb.log.info(f"axelcc ifdiverge PASSED: {got}, cycles={cyc}")
