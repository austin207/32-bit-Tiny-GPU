import os
import cocotb
from cocotb.clock import Clock

from tests.common import load_axelbin, init_bus, run_kernel, print_core_debug
from tests.memory_models import program_memory_model, data_memory_model


async def run_ldr_test(dut, filename, expected):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base, f"../../assembler/builds/bin/{filename}")

    kernel = load_axelbin(path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    init_bus(dut)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    kc, elapsed = await run_kernel(dut, kernel)

    if kc is None:
        await print_core_debug(dut)
        assert False, f"{filename} hung after {elapsed} cycles"

    all_pass = True
    for addr, exp in sorted(expected.items()):
        got = data_memory.get(addr, 0) & 0xFFFFFFFF
        status = "PASS" if got == exp else "FAIL"
        print(f"  mem[{addr}] = 0x{got:08x} expected 0x{exp:08x} {status}")
        all_pass &= (got == exp)

    print(f"  kernel_cycles = {kc}")
    assert all_pass, f"{filename} mismatch"


@cocotb.test()
async def test_ldr_regbase_single(dut):
    print("\n── Phase 9: R6-base LDR single-thread ──")
    await run_ldr_test(
        dut,
        "phase9_ldr_regbase_single.axelbin",
        {8: 0x12345678},
    )


@cocotb.test()
async def test_ldr_regbase_broadcast(dut):
    print("\n── Phase 9: R6-base LDR 4-thread broadcast ──")
    await run_ldr_test(
        dut,
        "phase9_ldr_regbase_broadcast.axelbin",
        {
            8: 0x12345678,
            9: 0x12345678,
            10: 0x12345678,
            11: 0x12345678,
        },
    )