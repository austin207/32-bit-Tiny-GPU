import os
import cocotb
from cocotb.clock import Clock

from tests.common import load_axelbin, init_bus, run_kernel, u32_to_signed, print_core_debug
from tests.memory_models import program_memory_model, data_memory_model


@cocotb.test()
async def test_digit_hidden_phase13(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base, "../../assembler/builds/bin/phase13_digit_hidden.axelbin")

    kernel = load_axelbin(path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    expected = {20: 42, 21: 37, 22: 0, 23: 6}

    print("\n── Phase 13: small digit hidden layer ──")

    init_bus(dut)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    kc, elapsed = await run_kernel(dut, kernel)

    if kc is None:
        await print_core_debug(dut)
        assert False, f"phase13 hung after {elapsed} cycles"

    all_pass = True
    for addr, exp in sorted(expected.items()):
        got = u32_to_signed(data_memory.get(addr, 0))
        status = "PASS" if got == exp else "FAIL"
        print(f"  h[{addr-20}] mem[{addr}] = {got:4d} expected {exp:4d} {status}")
        all_pass &= (got == exp)

    print(f"  kernel_cycles = {kc}")
    assert all_pass, "phase13 output mismatch"