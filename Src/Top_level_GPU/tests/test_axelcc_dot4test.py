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
        "../../../assembler/builds/hex/test_dot4test.hex"
    )
)


@cocotb.test()
async def test_axelcc_dot4test(dut):
    """
    dot4(a, b) = packed INT8x4 dot product (alu.sv 6'h16), not scalar FMA
    (6'h0C). Regression test for the EXPR_DOT4 codegen bug: codegen.c used
    to call emit_fma() for dot4() calls, silently emitting opcode 0x0C
    (plain scalar multiply-add on the full 32-bit operands) instead of
    0x16 (four independent signed INT8 lane multiplies, summed).

    a = 0x01020304 -> lanes [a0=4, a1=3, a2=2, a3=1]
    b = 0x01010101 -> lanes [b0=1, b1=1, b2=1, b3=1]
    expected = 4*1 + 3*1 + 2*1 + 1*1 = 10

    If codegen still emitted FMA, mem[0]*mem[1] would overflow 32 bits and
    produce a value nowhere near 10 -- a clearly distinguishable failure.
    """
    a = 0x01020304
    b = 0x01010101
    expected = 4 * 1 + 3 * 1 + 2 * 1 + 1 * 1

    cocotb.log.info(f"dot4 test: a=0x{a:08x} b=0x{b:08x} expected={expected}")

    instructions = load_hex_file(HEX_PATH)
    data_memory = {0: a, 1: b}

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
        assert False, "TIMEOUT: dot4test did not finish"

    await Timer(1, unit="ns")

    got = data_memory.get(2)
    got_signed = u32_to_signed(got) if got is not None else None

    assert got_signed == expected, (
        f"dot4test: mem[2]={got_signed}, expected {expected}"
    )
    cocotb.log.info(f"axelcc dot4test PASSED, mem[2]={got_signed}")
