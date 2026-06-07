import os
import cocotb
from cocotb.clock import Clock

from tests.common import load_axelbin, init_bus, run_kernel, u32_to_signed, print_core_debug
from tests.memory_models import program_memory_model, data_memory_model
from tests.test_phase15_digit64_hidden import hidden_golden, clamp_i8, relu


DEBUG_MEM = False
DEBUG_PMEM = False


def output_golden(memory):
    expected = {}

    for cls in range(10):
        acc = 0

        for h in range(16):
            hv = u32_to_signed(memory.get(272 + h, 0))
            w = u32_to_signed(memory.get(288 + cls * 16 + h, 0))
            acc += hv * w

        expected[480 + cls] = clamp_i8(relu(acc >> 8))

    return expected


@cocotb.test()
async def test_digit64_classifier_phase15_phase16(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base = os.path.dirname(os.path.dirname(__file__))

    p15 = os.path.join(base, "../../assembler/builds/bin/phase15_digit64_hidden.axelbin")
    p16 = os.path.join(base, "../../assembler/builds/bin/phase16_digit64_output.axelbin")

    k15 = load_axelbin(p15)
    k16 = load_axelbin(p16)

    instr15 = {i: v for i, v in enumerate(k15["instructions"])}
    instr16 = {i: v for i, v in enumerate(k16["instructions"])}

    data_memory = {i: v for i, v in enumerate(k15["data_mem_raw"])}

    phase16_mem = {i: v for i, v in enumerate(k16["data_mem_raw"])}
    for addr, val in phase16_mem.items():
        if addr >= 288:
            data_memory[addr] = val

    expected_h = hidden_golden(data_memory)

    print("\n── Phase 16: chained true 64->16->10 classifier ──")
    print(f"  phase15 words={k15['text_words']} data={k15['data_words']}")
    print(f"  phase16 words={k16['text_words']} data={k16['data_words']}")

    init_bus(dut)

    instructions_ref = [instr15]

    cocotb.start_soon(
        program_memory_model(
            dut,
            instructions_ref,
            debug=DEBUG_PMEM,
        )
    )

    cocotb.start_soon(
        data_memory_model(
            dut,
            data_memory,
            debug=DEBUG_MEM,
            debug_addr_min=256,
            debug_addr_max=491,
        )
    )

    kc15, elapsed15 = await run_kernel(dut, k15, timeout_cycles=200000)

    if kc15 is None:
        await print_core_debug(dut)
        assert False, f"phase15 hung after {elapsed15} cycles"

    hidden_values = []
    for addr, exp in sorted(expected_h.items()):
        got = u32_to_signed(data_memory.get(addr, 0))
        hidden_values.append(got)
        assert got == exp, f"hidden mem[{addr}] expected {exp}, got {got}"

    instructions_ref[0] = instr16
    expected_y = output_golden(data_memory)

    kc16, elapsed16 = await run_kernel(dut, k16, timeout_cycles=200000)

    if kc16 is None:
        await print_core_debug(dut)
        assert False, f"phase16 hung after {elapsed16} cycles"

    scores = []
    all_pass = True

    print(f"  hidden = {hidden_values}")

    for addr, exp in sorted(expected_y.items()):
        got = u32_to_signed(data_memory.get(addr, 0))
        scores.append(got)
        status = "PASS" if got == exp else "FAIL"
        print(f"  class {addr-480:2d} mem[{addr}] = {got:4d} expected {exp:4d} {status}")
        all_pass &= (got == exp)

    pred = max(range(len(scores)), key=lambda i: scores[i])

    print(f"  scores = {scores}")
    print(f"  argmax = class {pred}")
    print(f"  phase15 cycles = {kc15}")
    print(f"  phase16 cycles = {kc16}")
    print(f"  total cycles = {kc15 + kc16}")

    assert all_pass, "phase16 output mismatch"