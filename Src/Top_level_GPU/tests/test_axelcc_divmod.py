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
        "../../../assembler/builds/hex/test_divmod.hex"
    )
)


@cocotb.test()
async def test_axelcc_divmod(dut):
    """
    Regression test for a codegen gap: axelcc's parser accepted `/` and `%`
    as binary operators, but codegen.c's EXPR_BINOP switch had no case for
    TOK_SLASH/TOK_PERCENT -- any kernel using them failed to compile with a
    misleading "comparison op not valid" error, even though DIV (0x04) and
    MOD (0x05) are fully implemented in hardware. Found while scoping the
    Phase 5 softmax kernel, which needs `/` to normalize exp8 scores.

    mem[0]=17, mem[1]=5 -> mem[2] = 17/5 = 3, mem[3] = 17%5 = 2
    """
    instructions = load_hex_file(HEX_PATH)
    data_memory = {0: 17, 1: 5}

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    cyc = await launch_kernel(dut, instructions_ref, instructions)
    assert cyc is not None, "TIMEOUT: divmodtest did not finish"

    got_div = u32_to_signed(data_memory.get(2))
    got_mod = u32_to_signed(data_memory.get(3))

    assert got_div == 3, f"divmodtest: mem[2]={got_div}, expected 3"
    assert got_mod == 2, f"divmodtest: mem[3]={got_mod}, expected 2"
    cocotb.log.info(f"axelcc divmodtest PASSED: mem[2]={got_div} mem[3]={got_mod}")
