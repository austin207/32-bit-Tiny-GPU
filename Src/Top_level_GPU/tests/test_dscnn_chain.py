import glob
import os

import numpy as np

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from .common import init_bus, launch_kernel, set_params, u32_to_signed
from .memory_models import program_memory_model, data_memory_model
from .dscnn_reference import (
    load_model, tensor_quant, _build_all_layers, _SOFTMAX,
    derive_softmax_exp_shift, write_padded_channel_plane, run_dscnn_host,
    run_tflite_reference,
)
from .dscnn_features import load_and_extract, quantize_to_int8


def load_hex_file(path):
    instructions = {}
    with open(path) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if line:
                instructions[i] = int(line, 16)
    return instructions


BUILD_HEX = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../assembler/builds/hex")
)

RAW_DATA_DIR = (
    "/mnt/c/Users/austi/OneDrive/Desktop/Project/Personal/"
    "voice-fan-controller/training/data/raw"
)

# Real per-kernel-launch cost: task #24's wall-clock check measured pw0
# (the largest-MAC-count layer, real size) comfortably finishing inside
# 2,000,000 cycles. Every other layer in this chain has fewer or equal
# MACs (see dscnn_reference.py's __main__ output for each layer's real
# weight/channel counts), so one shared generous ceiling covers the whole
# chain without needing a per-kernel table.
CHAIN_TIMEOUT_CYCLES = 3_000_000

# Ctrl-reg window the RTL's accel_sel decode claims (see project memory
# project_accel_ctrl_address_ceiling.md) -- the address allocator below
# starts at 0x200 specifically to never need to reason about it again.
ADDR_START = 0x200


class AddrAlloc:
    """Simple bump allocator for data_memory addresses, starting past the
    accelerator's 0x1F0-0x1FF ctrl-reg window so every buffer this test
    hands out is unconditionally real data memory."""

    def __init__(self, start=ADDR_START):
        self.cursor = start

    def alloc(self, size):
        addr = self.cursor
        self.cursor += size
        return addr


def write_array(data_memory, base, values):
    for i, v in enumerate(values):
        data_memory[base + i] = v & 0xFFFFFFFF


def read_plane(data_memory, base, length):
    return [u32_to_signed(data_memory.get(base + i, 0)) for i in range(length)]


@cocotb.test()
async def test_dscnn_chain(dut):
    """
    Task #25: full end-to-end DS-CNN chain, all 12 kernel launches (stem ->
    4x[depthwise, pointwise] -> maxpool -> fc -> softmax) on real GPU RTL,
    sharing one data_memory dict across launches (same mechanism as
    test_phase5_attn_chain.py), driven by REAL model weights
    (dscnn_reference.py's _build_all_layers, reading dscnn_fan_int8.tflite
    directly) and one REAL WAV file's extracted+quantized features
    (dscnn_features.py, real librosa/soundfile pipeline). This is the first
    time this pipeline runs at real size on RTL -- every isolated kernel
    test before this used small hand-picked synthetic addresses/shapes;
    this test is only possible now that task #33 (accel ctrl address-decode
    fix, see project memory project_accel_ctrl_address_ceiling.md) removed
    the 496-word data-memory ceiling that made real-size execution
    categorically impossible.

    Padding is filled host-side between stages (write_padded_channel_plane),
    per the plan's design correction #1 -- axelcc's `if` can't express a 2D
    bounds check, so the host reads back each stage's raw (unpadded) RTL
    output, pads its border with that stage's own in_zp, and writes the
    padded plane into the next depthwise stage's input region before
    launching it. Pointwise stages need no padding (1x1 kernel) and read
    directly from the preceding depthwise stage's raw output.

    Two-tier correctness check, per dscnn_reference.py's own documented
    precision caveats (module docstring, "two known real precision
    caveats"):
      1. PRIMARY (bit-exact): RTL output must exactly equal
         run_dscnn_host()'s output. Both implement the literal same
         single-stage integer pipeline (dscnn_*.axelc's actual arithmetic,
         not TFLite's two-stage gemmlowp rescale) -- any divergence here is
         a genuine RTL/compiler/host-tooling bug, not expected precision
         drift, and must fail the test.
      2. SECONDARY (functional, not bit-exact): argmax must match the real
         TFLite interpreter's argmax on the same input -- the meaningful
         hardware-proof signal task #26's breadth check already validated
         at the host level (18/18 classes). Per-element deltas against the
         interpreter are logged, not asserted, since the single-stage vs.
         gemmlowp two-stage rescale and the softmax shift-only exp_shift
         approximation are BOTH already-documented, expected sources of
         divergence (see dscnn_reference.py's module docstring) -- bit-exact
         agreement with the interpreter was never the design's goal.

    WAV file: one real "power_on" sample (same class dscnn_features.py's
    own __main__ self-test already uses) -- not one of the two classes
    (timer_2h/timer_4h) task #26 flagged as a genuine model ambiguity.
    """
    model, sg = load_model()
    layers = _build_all_layers(model, sg)

    in_scale, in_zp = tensor_quant(sg, 0)

    wav_candidates = sorted(glob.glob(os.path.join(RAW_DATA_DIR, "power_on", "*.wav")))
    assert wav_candidates, f"no WAV files found under {RAW_DATA_DIR}/power_on"
    wav_path = wav_candidates[0]

    spec_db = load_and_extract(wav_path)
    features_int8 = quantize_to_int8(spec_db, in_scale[0], in_zp[0]).flatten().tolist()

    host_out = run_dscnn_host(model, sg, features_int8, layers=layers)
    host_argmax = host_out.index(max(host_out))

    tflite_out, _ = run_tflite_reference(
        np.array(features_int8, dtype="int8").reshape(1, 81, 32, 1)
    )
    tflite_out = tflite_out.flatten().tolist()
    tflite_argmax = tflite_out.index(max(tflite_out))

    alloc = AddrAlloc()
    data_memory = {}

    hex_cache = {}

    def hexfile(name):
        if name not in hex_cache:
            hex_cache[name] = load_hex_file(os.path.join(BUILD_HEX, name + ".hex"))
        return hex_cache[name]

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions_ref = [hexfile("dscnn_stem_conv")]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    cycles = {}

    # ── Stem ─────────────────────────────────────────────────────────────
    stem = layers["stem"]
    stem_in_base = alloc.alloc(stem["H_padded"] * stem["W_padded"])
    write_padded_channel_plane(
        data_memory, stem_in_base, stem["H_padded"], stem["W_padded"],
        stem["pad_top"], stem["pad_left"], stem["H_in"], stem["W_in"],
        features_int8, stem["in_zp"],
    )
    stem_w_base = alloc.alloc(len(stem["weights_packed"]))
    write_array(data_memory, stem_w_base, stem["weights_packed"])
    stem_bias_base = alloc.alloc(stem["Cout"])
    write_array(data_memory, stem_bias_base, stem["bias_eff"])
    stem_mult_base = alloc.alloc(stem["Cout"])
    write_array(data_memory, stem_mult_base, stem["mult"])
    stem_shift_base = alloc.alloc(stem["Cout"])
    write_array(data_memory, stem_shift_base, stem["shift"])
    stem_out_base = alloc.alloc(stem["Cout"] * stem["H_out"] * stem["W_out"])

    set_params(
        data_memory,
        stem_in_base, stem_out_base, stem_w_base, stem_bias_base,
        stem["H_out"], stem["W_out"], stem["W_padded"],
        stem["stride"], stem_mult_base, stem_shift_base, stem["out_zp"],
    )
    cyc = await launch_kernel(
        dut, instructions_ref, hexfile("dscnn_stem_conv"),
        num_blocks=4, blockDim=4, timeout_cycles=CHAIN_TIMEOUT_CYCLES,
    )
    assert cyc is not None, "TIMEOUT: stem"
    cycles["stem"] = cyc

    prev_out_base = stem_out_base
    prev_C, prev_H, prev_W = stem["Cout"], stem["H_out"], stem["W_out"]

    # ── 4x [depthwise, pointwise] blocks ────────────────────────────────
    for dw_name, pw_name in (("dw0", "pw0"), ("dw1", "pw1"), ("dw2", "pw2"), ("dw3", "pw3")):
        dw = layers[dw_name]
        pw = layers[pw_name]

        assert prev_C == dw["Cout"], f"{dw_name}: channel mismatch {prev_C} != {dw['Cout']}"
        assert (prev_H, prev_W) == (dw["H_in"], dw["W_in"]), (
            f"{dw_name}: spatial mismatch {(prev_H, prev_W)} != {(dw['H_in'], dw['W_in'])}"
        )

        dw_in_base = alloc.alloc(dw["Cout"] * dw["H_padded"] * dw["W_padded"])
        for c in range(dw["Cout"]):
            plane = read_plane(data_memory, prev_out_base + c * prev_H * prev_W, prev_H * prev_W)
            write_padded_channel_plane(
                data_memory, dw_in_base + c * dw["H_padded"] * dw["W_padded"],
                dw["H_padded"], dw["W_padded"], dw["pad_top"], dw["pad_left"],
                prev_H, prev_W, plane, dw["in_zp"],
            )

        dw_w_base = alloc.alloc(len(dw["weights_packed"]))
        write_array(data_memory, dw_w_base, dw["weights_packed"])
        dw_bias_base = alloc.alloc(dw["Cout"])
        write_array(data_memory, dw_bias_base, dw["bias_eff"])
        dw_mult_base = alloc.alloc(dw["Cout"])
        write_array(data_memory, dw_mult_base, dw["mult"])
        dw_shift_base = alloc.alloc(dw["Cout"])
        write_array(data_memory, dw_shift_base, dw["shift"])
        dw_out_base = alloc.alloc(dw["Cout"] * dw["H_out"] * dw["W_out"])

        set_params(
            data_memory,
            dw_in_base, dw_out_base, dw_w_base, dw_bias_base,
            dw["H_out"], dw["W_out"], dw["H_padded"], dw["W_padded"],
            dw["stride"], dw_mult_base, dw_shift_base, dw["out_zp"],
        )
        cyc = await launch_kernel(
            dut, instructions_ref, hexfile("dscnn_dwconv"),
            num_blocks=dw["Cout"] // 4, blockDim=4, timeout_cycles=CHAIN_TIMEOUT_CYCLES,
        )
        assert cyc is not None, f"TIMEOUT: {dw_name}"
        cycles[dw_name] = cyc

        prev_out_base = dw_out_base
        prev_C, prev_H, prev_W = dw["Cout"], dw["H_out"], dw["W_out"]

        # Pointwise: 1x1, no padding, reads dw's raw output directly.
        assert prev_C == pw["Cin"], f"{pw_name}: channel mismatch {prev_C} != {pw['Cin']}"
        assert prev_H * prev_W == pw["HW"], f"{pw_name}: HW mismatch {prev_H * prev_W} != {pw['HW']}"

        pw_w_base = alloc.alloc(len(pw["weights_packed"]))
        write_array(data_memory, pw_w_base, pw["weights_packed"])
        pw_bias_base = alloc.alloc(pw["Cout"])
        write_array(data_memory, pw_bias_base, pw["bias_eff"])
        pw_mult_base = alloc.alloc(pw["Cout"])
        write_array(data_memory, pw_mult_base, pw["mult"])
        pw_shift_base = alloc.alloc(pw["Cout"])
        write_array(data_memory, pw_shift_base, pw["shift"])
        pw_out_base = alloc.alloc(pw["Cout"] * pw["HW"])

        set_params(
            data_memory,
            prev_out_base, pw_out_base, pw_w_base, pw_bias_base,
            pw["Cin4"], pw["HW"], pw_mult_base, pw_shift_base, pw["out_zp"],
        )
        cyc = await launch_kernel(
            dut, instructions_ref, hexfile("dscnn_pwconv"),
            num_blocks=pw["Cout"] // 4, blockDim=4, timeout_cycles=CHAIN_TIMEOUT_CYCLES,
        )
        assert cyc is not None, f"TIMEOUT: {pw_name}"
        cycles[pw_name] = cyc

        prev_out_base = pw_out_base
        prev_C = pw["Cout"]
        # prev_H, prev_W unchanged -- pointwise doesn't touch spatial dims.

    # ── Global max pool ──────────────────────────────────────────────────
    maxpool_HW = prev_H * prev_W
    maxpool_out_base = alloc.alloc(prev_C)
    set_params(data_memory, prev_out_base, maxpool_out_base, maxpool_HW)
    cyc = await launch_kernel(
        dut, instructions_ref, hexfile("dscnn_maxpool"),
        num_blocks=prev_C // 4, blockDim=4, timeout_cycles=CHAIN_TIMEOUT_CYCLES,
    )
    assert cyc is not None, "TIMEOUT: maxpool"
    cycles["maxpool"] = cyc

    # ── Fully connected ──────────────────────────────────────────────────
    fc = layers["fc"]
    assert prev_C == fc["Cin"], f"fc: channel mismatch {prev_C} != {fc['Cin']}"

    fc_w_base = alloc.alloc(len(fc["weights_packed"]))
    write_array(data_memory, fc_w_base, fc["weights_packed"])
    fc_bias_base = alloc.alloc(fc["Cout"])
    write_array(data_memory, fc_bias_base, fc["bias_eff"])
    fc_mult_base = alloc.alloc(fc["Cout"])
    write_array(data_memory, fc_mult_base, fc["mult"])
    fc_shift_base = alloc.alloc(fc["Cout"])
    write_array(data_memory, fc_shift_base, fc["shift"])
    fc_out_base = alloc.alloc(fc["Cout"])

    set_params(
        data_memory,
        maxpool_out_base, fc_out_base, fc_w_base, fc_bias_base,
        fc["Cin4"], fc_mult_base, fc_shift_base, fc["out_zp"],
    )
    cyc = await launch_kernel(
        dut, instructions_ref, hexfile("dscnn_fc"),
        num_blocks=fc["Cout"], blockDim=1, timeout_cycles=CHAIN_TIMEOUT_CYCLES,
    )
    assert cyc is not None, "TIMEOUT: fc"
    cycles["fc"] = cyc

    # ── Softmax ──────────────────────────────────────────────────────────
    sm_in_scale, _ = tensor_quant(sg, _SOFTMAX["in"])
    _, sm_out_zp = tensor_quant(sg, _SOFTMAX["out"])
    exp_shift = derive_softmax_exp_shift(sm_in_scale[0])
    N = fc["Cout"]
    softmax_out_base = alloc.alloc(N)

    set_params(data_memory, fc_out_base, softmax_out_base, N, exp_shift, sm_out_zp[0])
    cyc = await launch_kernel(
        dut, instructions_ref, hexfile("dscnn_softmax"),
        num_blocks=1, blockDim=1, timeout_cycles=CHAIN_TIMEOUT_CYCLES,
    )
    assert cyc is not None, "TIMEOUT: softmax"
    cycles["softmax"] = cyc

    # ── Verify ───────────────────────────────────────────────────────────
    rtl_out = read_plane(data_memory, softmax_out_base, N)
    rtl_argmax = rtl_out.index(max(rtl_out))

    deltas = [abs(r - t) for r, t in zip(rtl_out, tflite_out)]

    cocotb.log.info(
        f"dscnn_chain: wav={os.path.basename(wav_path)} "
        f"rtl_out={rtl_out} host_out={host_out} tflite_out={tflite_out} "
        f"rtl_argmax={rtl_argmax} host_argmax={host_argmax} tflite_argmax={tflite_argmax} "
        f"vs-tflite max|delta|={max(deltas)} mean|delta|={sum(deltas)/len(deltas):.2f} "
        f"cycles={cycles} total_cycles={sum(cycles.values())}"
    )

    assert rtl_out == host_out, (
        f"RTL vs host-golden MISMATCH (should be bit-exact, both implement the "
        f"same single-stage integer pipeline): rtl={rtl_out}, host={host_out}"
    )
    assert rtl_argmax == host_argmax

    assert rtl_argmax == tflite_argmax, (
        f"RTL argmax {rtl_argmax} != real TFLite interpreter argmax {tflite_argmax} "
        f"(rtl_out={rtl_out}, tflite_out={tflite_out}) -- functional disagreement, "
        f"not just the expected precision drift"
    )

    cocotb.log.info("dscnn_chain PASSED: bit-exact vs host golden, argmax matches real TFLite interpreter")
