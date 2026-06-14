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


@cocotb.test()
async def test_axelcc_relu(dut):
    """
    Verify axelcc-compiled ReLU kernel on full Top_level_GPU.

    Input:
        mem[0] =  5
        mem[1] = -3
        mem[2] =  8
        mem[3] = -1

    Expected:
        mem[4] = 5
        mem[5] = 0
        mem[6] = 8
        mem[7] = 0
    """

    base = os.path.dirname(__file__)
    hex_path = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "../../../assembler/builds/hex/axelcc_relu.hex"
    )
)

    instructions = load_hex_file(hex_path)
    cocotb.log.info(f"Loaded {len(instructions)} axelcc instructions from {hex_path}")

    data_memory = {
        0: 5,
        1: 0xFFFFFFFD,  # -3
        2: 8,
        3: 0xFFFFFFFF,  # -1
    }

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    # Reset
    dut.rst.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)

    dut.rst.value = 0
    await RisingEdge(dut.clk)

    # Start memory models
    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    # DCR configure: 1 block, 4 threads
    dut.dcr_write_en.value = 1

    dut.dcr_addr.value = 0
    dut.dcr_data.value = 1      # num_blocks = 1
    await RisingEdge(dut.clk)

    dut.dcr_addr.value = 1
    dut.dcr_data.value = 4      # blockDim = 4
    await RisingEdge(dut.clk)

    dut.dcr_addr.value = 2
    dut.dcr_data.value = 1      # start
    await RisingEdge(dut.clk)

    dut.dcr_write_en.value = 0

    # Wait for kernel_done
    cycle_count = 0
    for _ in range(10_000):
        await RisingEdge(dut.clk)
        cycle_count += 1

        if dut.kernel_done.value == 1:
            break
    else:
        assert False, "TIMEOUT: axelcc ReLU kernel did not finish"

    await Timer(1, unit="ns")

    expected = {
        4: 5,
        5: 0,
        6: 8,
        7: 0,
    }

    errors = []
    for addr, exp in expected.items():
        got = data_memory.get(addr)

        if got != exp:
            errors.append(f"mem[{addr}] got={got} expected={exp}")
        else:
            cocotb.log.info(f"mem[{addr}] = {got} PASS")

    assert not errors, "\n".join(errors)

    cocotb.log.info(f"axelcc ReLU PASSED in {cycle_count} cycles")