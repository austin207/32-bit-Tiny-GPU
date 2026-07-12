import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from .common import init_bus
from .memory_models import program_memory_model, data_memory_model, accel_data_memory_model


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
        "../../../assembler/builds/hex/test_matmultest.hex"
    )
)

# Same A/B data and golden C as test_phase21_accel_matmul.py --
# same accelerator, same math. The only thing under test here is
# whether axelcc's compiled STMT_MMIO_MATMUL sequence matches the
# hand-assembled phase21 sequence.
EXPECTED_C = [
    [16, 32,  8,  8],
    [32, 64, 16, 16],
    [28, 56, 16, 12],
    [40, 80, 16, 24],
]


def _build_data_memory():
    m = {}
    for i in range(4): m[ 0 + i] = 0x01010101
    for i in range(4): m[ 4 + i] = 0x02020202
    for i in range(4): m[ 8 + i] = 0x00040300
    for i in range(4): m[12 + i] = 0x04030201
    for i in range(4): m[16 + i] = 0x01010101
    for i in range(4): m[20 + i] = 0x02020202
    for i in range(4): m[24 + i] = 0x00010001
    for i in range(4): m[28 + i] = 0x01000100
    return m


@cocotb.test()
async def test_axelcc_matmultest(dut):
    """
    mmio_matmul(0, 16, 32, 4, 4, 16, 0) compiled through axelcc.
    Same inputs/golden C as test_phase21_accel_matmul (hand-assembled).
    This is the direct check on whether axelcc's STMT_MMIO_MATMUL poll
    loop offset matches real hardware branch semantics.
    """
    instructions = load_hex_file(HEX_PATH)
    data_memory = _build_data_memory()

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
    cocotb.start_soon(accel_data_memory_model(dut, data_memory))

    dut.dcr_write_en.value = 1
    dut.dcr_addr.value = 0
    dut.dcr_data.value = 1      # num_blocks = 1
    await RisingEdge(dut.clk)
    dut.dcr_addr.value = 1
    dut.dcr_data.value = 1      # blockDim = 1 -- single thread is enough to trigger the accelerator
    await RisingEdge(dut.clk)
    dut.dcr_addr.value = 2
    dut.dcr_data.value = 1
    await RisingEdge(dut.clk)
    dut.dcr_write_en.value = 0

    cycle_count = 0
    for _ in range(100_000):
        await RisingEdge(dut.clk)
        cycle_count += 1
        if dut.kernel_done.value == 1:
            break
    else:
        assert False, f"TIMEOUT: matmultest did not finish after {cycle_count} cycles"

    await Timer(1, unit="ns")

    fail = 0
    for row in range(4):
        for col in range(4):
            addr = 32 + row * 4 + col
            got = data_memory.get(addr)
            exp = EXPECTED_C[row][col]
            if got != exp:
                cocotb.log.error(f"C[{row}][{col}] addr=0x{addr:03X} got={got} expected={exp} FAIL")
                fail += 1
            else:
                cocotb.log.info(f"C[{row}][{col}] addr=0x{addr:03X} got={got} PASS")

    assert fail == 0, f"matmultest: {fail}/16 C-matrix elements wrong"
    cocotb.log.info(f"axelcc matmultest PASSED: 16/16 correct, cycles={cycle_count}")