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
        "../../../assembler/builds/hex/test_relu_builtin.hex"
    )
)


@cocotb.test()
async def test_axelcc_relu_builtin(dut):
    """
    Regression test for a codegen gap: `relu(x)` was fully lexed, parsed,
    and sema-checked, but codegen.c's eval_expr had no EXPR_RELU case --
    calling it failed with "unsupported expression kind". The existing
    relu.axelc kernel (test_axelcc_relu.py) computes ReLU manually via
    if/else and never exercised the builtin, so this gap went unnoticed
    until a compiler-quality-pass audit found it. Fixed by wiring
    EXPR_RELU to the RELU opcode (alu.sv 6'h17) exactly like EXPR_EXP8.

    Same memory layout and expected values as test_axelcc_relu.py, so the
    builtin's result is directly comparable to the hand-rolled version it
    was meant to replace.

    mem[0..3] = [5, -3, 8, -1] -> mem[4..7] = [5, 0, 8, 0]
    """
    instructions = load_hex_file(HEX_PATH)
    data_memory = {0: 5, 1: 0xFFFFFFFD, 2: 8, 3: 0xFFFFFFFF}

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    cyc = await launch_kernel(dut, instructions_ref, instructions, blockDim=4)
    assert cyc is not None, "TIMEOUT: relu_builtin did not finish"

    expected = {4: 5, 5: 0, 6: 8, 7: 0}
    got = {addr: u32_to_signed(data_memory.get(addr)) for addr in expected}

    assert got == expected, f"relu_builtin: got={got}, expected={expected}"
    cocotb.log.info(f"axelcc relu_builtin PASSED: {got}")
