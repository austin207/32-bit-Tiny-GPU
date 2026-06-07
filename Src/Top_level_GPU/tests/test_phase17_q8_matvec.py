import os
import cocotb
from cocotb.clock import Clock

from tests.common import load_axelbin, init_bus, run_kernel, u32_to_signed, print_core_debug
from tests.memory_models import program_memory_model, data_memory_model


@cocotb.test()
async def test_q8_matvec_4x4(dut):
    """Phase 17: Q8 4x4 matvec — 1 block, 4 threads, DOT4 accelerated."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(
        base,
        "../../assembler/builds/bin/phase17_q8_matvec_4x4.axelbin"
    )

    kernel = load_axelbin(path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    # Diagnostic DOT4 lane test:
    #
    # mem[0] = A_row[0] = [1,0,0,0] = 0x00000001
    # mem[1] = A_row[1] = [0,2,0,0] = 0x00000200
    # mem[2] = A_row[2] = [0,0,3,0] = 0x00030000
    # mem[3] = A_row[3] = [0,0,0,4] = 0x04000000
    # mem[4] = x        = [1,2,3,4] = 0x04030201
    #
    # y[0] = 1*1 = 1
    # y[1] = 2*2 = 4
    # y[2] = 3*3 = 9
    # y[3] = 4*4 = 16
    expected = {
        5: 3,
        6: 7,
        7: 11,
        8: 15,
    }

    print("\n── Phase 17: Q8 4x4 matvec (DOT4), 1b x 4t ──")

    init_bus(dut)
    cocotb.start_soon(program_memory_model(dut, [instructions]))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    kc, elapsed = await run_kernel(dut, kernel)

    if kc is None:
        await print_core_debug(dut)
        assert False, f"phase17 hung after {elapsed} cycles"

    print("\nFinal data memory dump:")
    for addr in range(0, 12):
        raw = data_memory.get(addr, 0) & 0xFFFFFFFF
        signed = u32_to_signed(raw)
        print(f"  mem[{addr:02d}] = 0x{raw:08x} ({signed})")

    all_pass = True
    for addr, exp in sorted(expected.items()):
        got = u32_to_signed(data_memory.get(addr, 0))
        status = "PASS" if got == exp else "FAIL"
        print(f"  y[{addr - 5}] mem[{addr}] = {got:4d}  expected {exp:4d}  {status}")
        all_pass &= (got == exp)

    print(f"  kernel_cycles = {kc}")
    assert all_pass, "phase17 output mismatch"