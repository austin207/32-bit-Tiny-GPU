import os
import cocotb
from cocotb.clock import Clock

from tests.common import load_axelbin, init_bus, run_kernel, u32_to_signed, print_core_debug
from tests.memory_models import program_memory_model, data_memory_model


@cocotb.test()
async def test_q8_matmul_4x16(dut):
    """Phase 20: Q8 4x16 tiled matmul — 4b x 4t, 4 DOT4 chunks per output."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base, "../../assembler/builds/bin/phase20_q8_matmul_4x16.axelbin")

    kernel = load_axelbin(path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory  = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    # A rows (4 chunks each, all identical chunks per row):
    #   row0=[1,1,1,1]x4, row1=[2,2,2,2]x4, row2=[0,3,4,0]x4, row3=[1,2,3,4]x4
    # B^T cols (4 chunks each, all identical):
    #   col0=[1,1,1,1]x4, col1=[2,2,2,2]x4, col2=[1,0,1,0]x4, col3=[0,1,0,1]x4
    #
    # C[i][k] = 4 * DOT4(A_row[i], B_col[k]):
    #   row0: [16, 32,  8,  8]
    #   row1: [32, 64, 16, 16]
    #   row2: [28, 56, 16, 12]
    #   row3: [40, 80, 16, 24]
    expected = {
        32: 16, 33: 32, 34:  8, 35:  8,
        36: 32, 37: 64, 38: 16, 39: 16,
        40: 28, 41: 56, 42: 16, 43: 12,
        44: 40, 45: 80, 46: 16, 47: 24,
    }

    print("\n── Phase 20: Q8 4x16 tiled matmul, 4b x 4t, 4 DOT4 chunks ──")

    init_bus(dut)
    cocotb.start_soon(program_memory_model(dut, [instructions]))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    kc, elapsed = await run_kernel(dut, kernel)

    if kc is None:
        await print_core_debug(dut)
        assert False, f"phase20 hung after {elapsed} cycles"

    all_pass = True
    for row in range(4):
        row_vals = []
        for col in range(4):
            addr = 32 + row * 4 + col
            got  = u32_to_signed(data_memory.get(addr, 0))
            exp  = expected[addr]
            row_vals.append(f"{got:4d}(exp {exp:4d})")
            all_pass &= (got == exp)
        status = "PASS" if all(
            u32_to_signed(data_memory.get(32 + row*4 + c, 0)) == expected[32 + row*4 + c]
            for c in range(4)
        ) else "FAIL"
        print(f"  C[{row}]: [{', '.join(row_vals)}]  {status}")

    print(f"  kernel_cycles = {kc}")
    assert all_pass, "phase20 output mismatch"