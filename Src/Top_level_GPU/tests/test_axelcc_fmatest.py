import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from .common import init_bus, u32_to_signed
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
        "../../../assembler/builds/hex/test_fmatest.hex"
    )
)


@cocotb.test()
async def test_axelcc_fmatest(dut):
    """
    fma(a, b, c) = a*b + c. Plain scalar FMA (alu.sv 6'h0C: operand1*operand2+operand3).
    Not dot4 -- dot4 is a separate opcode (0x16) with packed INT8x4 lanes.
    Small scalar inputs used deliberately to avoid 32-bit overflow noise.

    a = 6, b = 7, c = 5
    expected = 6*7 + 5 = 47
    """
    a = 6
    b = 7
    c = 5
    expected = a * b + c

    cocotb.log.info(f"fma test: a={a} b={b} c={c} expected={expected}")

    instructions = load_hex_file(HEX_PATH)
    data_memory = {0: a, 1: b, 2: c}

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
        assert False, "TIMEOUT: fmatest did not finish"

    await Timer(1, unit="ns")

    got = data_memory.get(3)
    got_signed = u32_to_signed(got) if got is not None else None

    assert got_signed == expected, (
        f"fmatest: mem[3]={got_signed}, expected {expected}"
    )
    cocotb.log.info(f"axelcc fmatest PASSED, mem[3]={got_signed}")