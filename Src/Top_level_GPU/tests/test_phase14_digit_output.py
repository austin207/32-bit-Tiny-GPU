import os
import cocotb
from cocotb.clock import Clock

from tests.common import load_axelbin, init_bus, run_kernel, u32_to_signed, print_core_debug
from tests.memory_models import program_memory_model, data_memory_model


@cocotb.test()
async def test_digit_output_phase14(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base, "../../assembler/builds/bin/phase14_digit_output.axelbin")

    kernel = load_axelbin(path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    data_memory[20] = 42
    data_memory[21] = 37
    data_memory[22] = 0
    data_memory[23] = 6

    expected = {40: 7, 41: 5, 42: 2, 43: 5}

    print("\n── Phase 14: small digit output layer ──")

    init_bus(dut)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    kc, elapsed = await run_kernel(dut, kernel)

    if kc is None:
        await print_core_debug(dut)
        assert False, f"phase14 hung after {elapsed} cycles"

    scores = []
    all_pass = True
    for addr, exp in sorted(expected.items()):
        got = u32_to_signed(data_memory.get(addr, 0))
        scores.append(got)
        status = "PASS" if got == exp else "FAIL"
        print(f"  y[{addr-40}] mem[{addr}] = {got:4d} expected {exp:4d} {status}")
        all_pass &= (got == exp)

    pred = max(range(len(scores)), key=lambda i: scores[i])

    print(f"  scores = {scores}")
    print(f"  argmax = class {pred}")
    print(f"  kernel_cycles = {kc}")

    assert all_pass, "phase14 output mismatch"
    assert pred == 0, f"phase14 expected argmax class 0, got {pred}"