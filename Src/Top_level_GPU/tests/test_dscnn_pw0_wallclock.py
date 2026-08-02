import os
import time

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from .common import init_bus, launch_kernel, set_params
from .memory_models import program_memory_model, data_memory_model


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
        "../../../assembler/builds/hex/dscnn_pwconv.hex"
    )
)


@cocotb.test()
async def test_dscnn_pw0_wallclock(dut):
    """
    Plan step 12: wall-clock risk check. Runs the real dscnn_pwconv.axelc
    binary at pw0's REAL size (Cin=16, Cout=48, HW=21*8=168 pixels, the
    largest layer in the pipeline by MAC count -- 48*16*168 = 129024 MACs,
    bigger than pw1/pw2/pw3's 48*48*44=101376 despite fewer channels,
    because pw0 runs at the largest surviving spatial resolution) through
    real cocotb/Icarus simulation, once, to measure actual wall-clock cost
    and cycle count. NOT part of the default `make test` regression (not in
    Makefile's COCOTB_TEST_MODULES) since it is slow (~8 minutes); run
    standalone with:
        make results.xml COCOTB_TEST_MODULES=tests.test_dscnn_pw0_wallclock

    IMPORTANT, discovered while writing this test: top_level_gpu.sv:160
    (`accel_sel[n] = data_mem_req_valid[n] && (data_mem_req_addr[n] >=
    32'h1F0)`) diverts every data-memory address >= 0x1F0 (496 decimal) to
    the Phase-4 matmul-accelerator's 16-word ctrl register block instead of
    real memory -- confirmed real RTL address-decode behavior, not a
    testbench artifact (memory_models.py's data_memory_model deliberately
    skips those addresses too, matching the hardware). pw0's real footprint
    (Cin*HW=2688 input words + Cout*HW=8064 output words alone, before
    weights/bias/mult/shift) cannot fit under that 496-word ceiling no
    matter how addresses are chosen, so this test's writes land in the
    accelerator ctrl space and are silently discarded -- output correctness
    CANNOT be verified at real size under the current RTL. This is a
    pipeline-wide blocker (every layer's activation buffer is well over
    496 words; total weight footprint alone is ~3800 words), not specific
    to pw0 -- see the session report for full numbers. Isolated correctness
    at small synthetic size (test_dscnn_pwconv.py, addresses < 496) is
    unaffected and still valid. This test therefore only measures cycles/
    wall-clock, it does not check output values.
    """
    Cin, Cout, HW = 16, 48, 21 * 8
    Cin4 = Cin // 4

    in_base, w_base, bias_eff_base, out_base = 0, 10_000, 20_000, 30_000
    mult_base, shift_base = 40_000, 40_100

    data_memory = {}

    for channel in range(Cin):
        for pixel in range(HW):
            data_memory[in_base + channel * HW + pixel] = (channel * 2 + pixel) % 127

    for oc in range(Cout):
        src_channel = oc % Cin  # one-hot: output channel oc reads input channel oc%Cin
        lanes = [[0, 0, 0, 0] for _ in range(Cin4)]
        lanes[src_channel // 4][src_channel % 4] = 1
        for chunk in range(Cin4):
            packed = 0
            for lane in range(4):
                packed |= (lanes[chunk][lane] & 0xFF) << (8 * lane)
            data_memory[w_base + oc * Cin4 + chunk] = packed

    for oc in range(Cout):
        data_memory[bias_eff_base + oc] = oc % 17

    for oc in range(Cout):
        data_memory[mult_base + oc] = 256
        data_memory[shift_base + oc] = 8

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions = load_hex_file(HEX_PATH)
    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    set_params(
        data_memory,
        in_base, out_base, w_base, bias_eff_base,
        Cin4, HW, mult_base, shift_base, 0,
    )

    wall_start = time.monotonic()
    cyc = await launch_kernel(
        dut, instructions_ref, instructions,
        num_blocks=Cout // 4, blockDim=4,
        timeout_cycles=2_000_000,
    )
    wall_elapsed = time.monotonic() - wall_start

    assert cyc is not None, "TIMEOUT: dscnn_pwconv (real pw0 size) did not finish within 2,000,000 cycles"

    cocotb.log.info(
        f"dscnn_pwconv @ real pw0 size (Cin={Cin}, Cout={Cout}, HW={HW}, "
        f"{Cout // 4} blocks x 4 threads): {cyc} cycles, {wall_elapsed:.2f}s wall-clock "
        f"({cyc / wall_elapsed:.0f} cycles/s sim rate)"
    )
    cocotb.log.info(
        "dscnn_pw0_wallclock: cycle/timing measurement only -- output "
        "correctness is NOT checked here, see module docstring (accel "
        "ctrl address-decode ceiling at 0x1F0/496 words discards writes "
        "at this real size)."
    )
