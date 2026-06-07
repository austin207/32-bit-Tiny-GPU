import os
import cocotb
from cocotb.clock import Clock

from tests.common import load_axelbin, init_bus, run_kernel, u32_to_signed, print_core_debug
from tests.memory_models import program_memory_model, data_memory_model


@cocotb.test()
async def test_q8_matmul_4x4(dut):
    """Phase 18: Q8 4x4 matmul - 4 blocks, 4 threads, DOT4 accelerated."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(
        base,
        "../../assembler/builds/bin/phase18_q8_matmul_4x4.axelbin"
    )

    kernel = load_axelbin(path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    expected_matrix = [
        [1, 2, 8, 3],
        [4, 7, 9, 11],
        [17, 5, 6, 16],
        [23, 0, 22, 15],
    ]

    expected = {}
    for row in range(4):
        for col in range(4):
            expected[8 + row * 4 + col] = expected_matrix[row][col]

    print("\n── Phase 18: Q8 4x4 matmul (DOT4), 4b x 4t ──")

    init_bus(dut)
    cocotb.start_soon(program_memory_model(dut, [instructions]))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    kc, elapsed = await run_kernel(dut, kernel)

    if kc is None:
        await print_core_debug(dut)
        assert False, f"phase18 hung after {elapsed} cycles"

    print("\nFinal C matrix:")
    all_pass = True

    for row in range(4):
        got_row = []
        exp_row = []
        for col in range(4):
            addr = 8 + row * 4 + col
            got = u32_to_signed(data_memory.get(addr, 0))
            exp = expected[addr]
            got_row.append(got)
            exp_row.append(exp)
            all_pass &= (got == exp)

        print(f"  row {row}: got {got_row} expected {exp_row}")

    print("\nOutput memory:")
    for addr in range(8, 24):
        got = u32_to_signed(data_memory.get(addr, 0))
        exp = expected[addr]
        status = "PASS" if got == exp else "FAIL"
        print(f"  mem[{addr:02d}] = {got:4d} expected {exp:4d} {status}")

    print(f"  kernel_cycles = {kc}")
    assert all_pass, "phase18 output mismatch"