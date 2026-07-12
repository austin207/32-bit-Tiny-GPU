import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from .common import init_bus
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
        "../../../assembler/builds/hex/test_ltcheck.hex"
    )
)


async def _run_ltcheck(dut, a, b, expected):
    instructions = load_hex_file(HEX_PATH)
    data_memory = {0: a & 0xFFFFFFFF, 1: b & 0xFFFFFFFF}

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.rst.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    dut.dcr_write_en.value = 1
    dut.dcr_addr.value = 0
    dut.dcr_data.value = 1
    await RisingEdge(dut.clk)
    dut.dcr_addr.value = 1
    dut.dcr_data.value = 1
    await RisingEdge(dut.clk)
    dut.dcr_addr.value = 2
    dut.dcr_data.value = 1
    await RisingEdge(dut.clk)
    dut.dcr_write_en.value = 0

    for _ in range(10_000):
        await RisingEdge(dut.clk)
        if dut.kernel_done.value == 1:
            break
    else:
        assert False, f"TIMEOUT: ltcheck(a={a}, b={b}) did not finish"

    await Timer(1, unit="ns")

    got = data_memory.get(2)
    assert got == expected, (
        f"ltcheck(a={a}, b={b}): mem[2]={got}, expected {expected}"
    )
    cocotb.log.info(f"axelcc ltcheck(a={a}, b={b}) PASSED, mem[2]={got}")


@cocotb.test()
async def test_axelcc_ltcheck_true(dut):
    """a < b: expect r=1."""
    await _run_ltcheck(dut, a=2, b=5, expected=1)


@cocotb.test()
async def test_axelcc_ltcheck_false(dut):
    """a >= b: expect r=0."""
    await _run_ltcheck(dut, a=5, b=2, expected=0)