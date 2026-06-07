import os
import cocotb
from cocotb.clock import Clock

from tests.common import load_axelbin, init_bus, run_kernel, u32_to_signed, print_core_debug
from tests.memory_models import program_memory_model, data_memory_model


DEBUG_MEM = False
DEBUG_PMEM = False


def unpack_int8x4(word):
    word &= 0xFFFFFFFF
    out = []

    for shift in (0, 8, 16, 24):
        b = (word >> shift) & 0xFF
        out.append(b - 256 if b >= 128 else b)

    return out


def dot4(a_word, b_word):
    a = unpack_int8x4(a_word)
    b = unpack_int8x4(b_word)
    return sum(x * y for x, y in zip(a, b))


def clamp_i8(v):
    if v > 127:
        return 127
    if v < -128:
        return -128
    return v


def relu(v):
    return v if v > 0 else 0


def hidden_golden(memory):
    expected = {}

    for hidden_id in range(16):
        acc = 0

        for k in range(16):
            w = memory.get(hidden_id * 16 + k, 0)
            x = memory.get(256 + k, 0)
            acc += dot4(w, x)

        expected[272 + hidden_id] = clamp_i8(relu(acc >> 8))

    return expected


@cocotb.test()
async def test_digit64_hidden_phase15(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base, "../../assembler/builds/bin/phase15_digit64_hidden.axelbin")

    kernel = load_axelbin(path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    expected = hidden_golden(data_memory)

    print("\n── Phase 15: true 64->16 hidden layer ──")
    print(f"  text_words={kernel['text_words']} data_words={kernel['data_words']}")
    print(f"  blocks={kernel['num_blocks']} blockDim={kernel['blockDim']}")

    init_bus(dut)

    instructions_ref = [instructions]

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
            debug_addr_min=0,
            debug_addr_max=287,
        )
    )

    kc, elapsed = await run_kernel(dut, kernel, timeout_cycles=200000)

    if kc is None:
        await print_core_debug(dut)
        assert False, f"phase15 hung after {elapsed} cycles"

    all_pass = True
    values = []

    for addr, exp in sorted(expected.items()):
        got = u32_to_signed(data_memory.get(addr, 0))
        values.append(got)
        status = "PASS" if got == exp else "FAIL"
        print(f"  h[{addr-272:2d}] mem[{addr}] = {got:4d} expected {exp:4d} {status}")
        all_pass &= (got == exp)

    print(f"  h = {values}")
    print(f"  kernel_cycles = {kc}")

    assert all_pass, "phase15 hidden mismatch"