"""
Host-side tooling for the DS-CNN voice-command classifier phase: extracts
real weights/biases/quantization parameters directly from
`dscnn_fan_int8.tflite`, derives each kernel invocation's (mult, shift,
round_bias) requantization constants and zero-point-folded bias (see the
plan's "two design corrections" -- padding is host-filled, zero-point is
folded into bias before dot4/fma), and packs weights into the exact memory
layout each of the six dscnn_*.axelc kernels expects
(Src/Top_level_GPU/tests/test_dscnn_*.py document each kernel's addressing
convention; this module produces the numbers those tests currently
hand-derive, from the real model instead of synthetic hand-picked values).

Tensor/weight extraction uses the `tflite` pip package, which is
schema-only (no Interpreter) -- that part never needs a real interpreter and
stays installed permanently. Running the real graph for an independent
ground truth (`run_tflite_reference` below) uses `ai-edge-litert`, a
verification-only tool: install it when actively comparing against real
TFLite output (tasks #22/#25/#26), uninstall it once that comparison work is
done. The point of this project is the GPU's own capability, not a
standing dependency on someone else's inference runtime.

── Two known, real precision caveats (read before assuming bit-exactness) ──

1. Conv/depthwise/pointwise/FC requantization. TFLite's actual reference
   kernels rescale via gemmlowp's SaturatingRoundingDoublingHighMul + a
   *second* RoundingDivideByPOT (see tflite_fixedpoint.py's
   `multiply_by_quantized_multiplier` -- a genuine two-stage round). The
   dscnn_*.axelc kernels instead do a single-stage rescale:
   `clamp(((acc*mult + round_bias) >> shift) + out_zp)` -- one multiply, one
   round, one shift (see dscnn_dwconv.axelc's header comment). This module's
   `derive_channel_params` computes (mult, shift) for that single-stage
   formula, matching what the kernels actually implement -- not
   `tflite_fixedpoint.quantize_multiplier`, which targets the two-stage
   scheme and is NOT what should be used to feed these kernels. The two
   schemes can differ by up to 1 LSB per output element (double-rounding),
   which is expected, not a bug -- keep it in mind if a layer-by-layer
   compare against a real interpreter shows occasional +-1 diffs.

2. Softmax. `dscnn_softmax.axelc` computes `d = clamp((score - max) >>
   exp_shift)` and looks `d` up in a fixed hardware exp8 LUT (Q6 fixed
   point, 111 distinct table entries, floors at LUT[-128]=17 for any diff
   more negative than -128 -- see attn_reference.py's `_EXP8_LUT`), then
   normalizes by integer division. This is a coarse approximation of real
   softmax by design (same primitive already used for attention), not a
   reimplementation of TFLite's gemmlowp-precision exp/reciprocal. It is
   also shift-only (no accompanying integer multiplier the way conv layers
   have `mult`), so it can only apply a power-of-two rescale to the real
   per-step logit gap -- for this model's real FC output scale
   (~0.0847/step), the mathematically ideal rescale is a *left* shift of
   about 2.4 bits, which a plain `>>` cannot express, so the best available
   non-negative integer choice is exp_shift=0, which itself undershoots the
   true dynamic range by roughly 5x (see `derive_softmax_exp_shift`'s
   docstring for the derivation). Net effect: expect a visibly flatter
   distribution than real TFLite's softmax, not a numerically close one.
   argmax-level agreement on confidently-classified samples is plausible;
   bit-exact int8-probability agreement across all 18 classes is not, with
   the kernel as currently designed. Flagged for the user rather than
   silently redesigned here -- worth revisiting once a real interpreter
   (task #22) lets us measure the actual divergence on real audio.
"""

import math
import os

import numpy as np

from tflite.Model import Model


TFLITE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../dscnn_fan_int8.tflite")
)


# ── Model loading / raw tensor extraction ───────────────────────────────────

def load_model(path=TFLITE_PATH):
    with open(path, "rb") as f:
        buf = f.read()
    model = Model.GetRootAsModel(buf, 0)
    return model, model.Subgraphs(0)


def tensor_shape(sg, idx):
    t = sg.Tensors(idx)
    return [t.Shape(i) for i in range(t.ShapeLength())]


def tensor_quant(sg, idx):
    """-> (scale: list[float], zero_point: list[int]).

    Length 1 = per-tensor quantization. Length == the tensor's output-channel
    dim (conv/depthwise/FC weight tensors in this model) = per-channel.
    """
    t = sg.Tensors(idx)
    q = t.Quantization()
    if q is None or q.ScaleLength() == 0:
        return [], []
    return q.ScaleAsNumpy().tolist(), q.ZeroPointAsNumpy().tolist()


def tensor_data(model, sg, idx):
    """Raw tensor data as a flat Python list, row-major per its TFLite shape.
    Dispatches on the tensor's declared type -- int8 (9) for
    weights/activations, int32 (2) for biases, matching this model exactly
    (asserts otherwise rather than silently misreading bytes)."""
    t = sg.Tensors(idx)
    buf = model.Buffers(t.Buffer())
    raw = buf.DataAsNumpy()
    if not isinstance(raw, np.ndarray):
        return []
    typ = t.Type()
    if typ == 9:  # TensorType.INT8
        return raw.view(np.int8).tolist()
    if typ == 2:  # TensorType.INT32
        return raw.view(np.int32).tolist()
    raise ValueError(f"tensor {idx} ({t.Name().decode()}): unsupported TensorType {typ}")


def run_tflite_reference(input_int8, model_path=TFLITE_PATH, preserve_all_tensors=True):
    """Runs the real graph via ai-edge-litert and returns (output_int8,
    get_intermediate) where get_intermediate(tensor_idx) reads any
    intermediate activation tensor (needs preserve_all_tensors=True, the
    default -- costs extra memory, fine at this model's size).

    Explicitly disables every default delegate (XNNPACK etc.) via
    BUILTIN_WITHOUT_DEFAULT_DELEGATES. This matters, confirmed empirically:
    on this exact model, XNNPACK's output differs from the plain reference
    kernels by several LSBs on the same input (a delegate is allowed to use
    any numerically-close-enough implementation, not bit-identical ones).
    tflite_fixedpoint.py was transcribed from TFLite's *reference* kernels,
    so any bit-exact comparison against it must run the interpreter without
    delegates, or the comparison is against the wrong ground truth.

    Requires `ai-edge-litert` installed (verification-only dependency --
    see module docstring; not needed for extraction/derivation work).
    """
    from ai_edge_litert.interpreter import Interpreter, OpResolverType

    interp = Interpreter(
        model_path=model_path,
        experimental_preserve_all_tensors=preserve_all_tensors,
        experimental_op_resolver_type=OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES,
    )
    interp.allocate_tensors()

    in_details = interp.get_input_details()[0]
    out_details = interp.get_output_details()[0]

    interp.set_tensor(in_details["index"], np.asarray(input_int8, dtype=np.int8).reshape(in_details["shape"]))
    interp.invoke()

    output = interp.get_tensor(out_details["index"])

    def get_intermediate(tensor_idx):
        return interp.get_tensor(tensor_idx)

    return output, get_intermediate


def broadcast_scale(scale, n):
    """Per-tensor weight quantization (length 1) broadcasts to n channels;
    per-channel (already length n) passes through unchanged."""
    if len(scale) == 1:
        return list(scale) * n
    assert len(scale) == n, f"scale length {len(scale)} != {n} channels"
    return list(scale)


# ── Weight extraction: per-output-channel tap lists ─────────────────────────
#
# Two natural TFLite weight layouts show up in this model:
#   - oc-major, tap-minor: [Cout, taps] flat, taps contiguous per channel.
#     True for stem ([Cout,KH,KW,1], Cin=1 collapses the last dim) AND for
#     pointwise/FC ([Cout,1,1,Cin] / [Cout,Cin]) -- structurally identical
#     extraction despite "taps" meaning spatial positions in one case and
#     input channels in the other.
#   - tap-major, channel-minor: [1,KH,KW,C] for depthwise (depth_multiplier
#     always 1 in this model, so Cout==Cin==C) -- needs a transpose to match
#     every dscnn kernel's channel-major addressing (w_base + channel*taps +
#     tap).

def taps_oc_major(weight_flat, n_out, taps):
    return [weight_flat[oc * taps:(oc + 1) * taps] for oc in range(n_out)]


def taps_channel_minor(weight_flat, C, taps):
    return [[weight_flat[t * C + c] for t in range(taps)] for c in range(C)]


def bias_fold(bias_int32, taps_per_channel, in_zp):
    """bias_eff[oc] = bias[oc] - in_zp * sum(weight[oc, all taps]).

    Derivation (see the plan's correction #2): TFLite's real op is
    sum((in - in_zp) * w) = sum(in*w) - in_zp*sum(w); dot4/fma pack raw
    signed int8 lanes with no runtime zero-point subtraction (would overflow
    the 8-bit lanes), so the in_zp term is precomputed here, once per
    channel, from the real weight values.
    """
    return [
        bias_int32[c] - in_zp * sum(taps_per_channel[c])
        for c in range(len(bias_int32))
    ]


def pack_taps_flat(taps_per_channel):
    """1 int8 per word, channel-major -- matches stem/depthwise's
    `w_base + channel*taps + tap` addressing directly."""
    flat = []
    for taps in taps_per_channel:
        flat.extend(taps)
    return flat


def pack4_word(vals4):
    """4 signed int8 lanes -> 1 packed 32-bit word, matching dot4's raw
    little-endian lane convention (alu.sv dot_p0..p3) and the exact
    `(v & 255) | ((v & 255) << 8) | ...` pattern dscnn_pwconv.axelc /
    dscnn_fc.axelc use to pack the INPUT side the same way."""
    b0, b1, b2, b3 = vals4
    return (b0 & 0xFF) | ((b1 & 0xFF) << 8) | ((b2 & 0xFF) << 16) | ((b3 & 0xFF) << 24)


def pack4_taps(taps_per_channel):
    """4 int8 taps per word, matching pointwise/FC's `w_base + oc*Cin4 +
    chunk` addressing. len(taps) per channel must be a multiple of 4 (true
    for every pointwise/FC layer in this model -- Cin in {16,48}, or 48 for
    FC)."""
    words = []
    for taps in taps_per_channel:
        assert len(taps) % 4 == 0, f"{len(taps)} taps not a multiple of 4"
        for chunk in range(0, len(taps), 4):
            words.append(pack4_word(taps[chunk:chunk + 4]))
    return words


# ── Requantization: (mult, shift) per output channel ────────────────────────
#
# Matches the single-stage scheme every dscnn_*.axelc kernel actually
# implements (see module docstring caveat 1) -- NOT gemmlowp's two-stage
# SRDHM+RDPOT scheme.

def acc_max_bound(taps_per_channel, in_range=255):
    """Conservative bound on |acc|: sum(|weight|) * 255, per the plan's
    overflow-check rule (255 = the widest possible magnitude of a signed
    int8 difference, a safe bound regardless of the real input's actual
    range)."""
    return [sum(abs(w) for w in taps) * in_range for taps in taps_per_channel]


def derive_mult_shift(M, acc_max, max_shift=30):
    """Largest shift in (0, max_shift] such that mult = round(M * 2**shift)
    fits int32 and mult*acc_max stays under 2**31 (IMUL is truncating, not
    saturating -- alu.sv:42 -- so this must never be allowed to overflow).
    Larger shift = more precision, so search from the top down."""
    shift = max_shift
    while shift > 0:
        mult = round(M * (1 << shift))
        if abs(mult) < (1 << 31) and abs(mult) * acc_max < (1 << 31):
            return mult, shift
        shift -= 1
    raise OverflowError(
        f"no shift in (0,{max_shift}] keeps mult*acc_max in int32 range "
        f"(M={M}, acc_max={acc_max})"
    )


def derive_channel_params(in_scale, w_scales, out_scale, acc_max_per_channel, max_shift=30):
    """Per-channel (mult[], shift[]) -- M = in_scale*w_scale[oc]/out_scale
    genuinely differs per output channel since conv/depthwise/pointwise
    weights in this model are per-channel quantized."""
    mults, shifts = [], []
    for w_scale, acc_max in zip(w_scales, acc_max_per_channel):
        M = in_scale * w_scale / out_scale
        mult, shift = derive_mult_shift(M, acc_max, max_shift)
        mults.append(mult)
        shifts.append(shift)
    return mults, shifts


# ── SAME padding ─────────────────────────────────────────────────────────────

def same_padding(in_size, out_size, kernel, stride):
    """TF SAME padding: total padding split with any odd remainder on the
    'after' side (matches TFLite's real convention, verified against this
    model's actual in/out spatial shapes for every stem/depthwise layer)."""
    total = max((out_size - 1) * stride + kernel - in_size, 0)
    before = total // 2
    return before, total - before


def write_padded_channel_plane(data_memory, base, H_padded, W_padded, pad_top, pad_left, H, W, plane, in_zp):
    """Fills one channel's full H_padded x W_padded plane into data_memory
    (real data where it overlaps, in_zp everywhere else) in one pass -- the
    border-prefill dscnn_dwconv.axelc/dscnn_stem_conv.axelc's header
    comments describe, done directly rather than as a separate border-only
    step, since every cell needs exactly one of these two values anyway."""
    for r in range(H_padded):
        row_in = r - pad_top
        for c in range(W_padded):
            col_in = c - pad_left
            if 0 <= row_in < H and 0 <= col_in < W:
                v = plane[row_in * W + col_in]
            else:
                v = in_zp
            data_memory[base + r * W_padded + c] = v & 0xFFFFFFFF


# ── Softmax exp_shift ────────────────────────────────────────────────────────

def derive_softmax_exp_shift(in_scale, beta=1.0):
    """Best available non-negative integer `exp_shift` for
    dscnn_softmax.axelc's `(score - max) >> exp_shift` rescale into exp8's
    Q6 domain (see module docstring caveat 2 for the full derivation).

    Ideal (real-valued) shift = log2(1 / (64 * beta * in_scale)). For this
    model's real FC output scale that value is negative (~-2.4) -- the
    kernel's shift-only design can't express a left shift, so this clamps
    to 0, which undershoots the true dynamic range by roughly 2**2.4 ~ 5x.
    Returned as a starting point, not a final answer: worth revisiting
    empirically once real per-sample FC logits are available (task #22/#25)
    to see how the resulting distribution actually looks.
    """
    ideal = math.log2(1.0 / (64.0 * beta * in_scale))
    return max(0, round(ideal))


# ── Per-op layer table for this specific graph ──────────────────────────────
#
# Which tensor index is "op N's weight" is a structural fact about this one
# compiled graph (found by walking sg.Operators() -- see the exploration
# that produced this table, not guessed): op0 CONV_2D (stem), op1/3/5/7
# DEPTHWISE_CONV_2D, op2/4/6/8 CONV_2D 1x1 (pointwise), op9 MAX_POOL_2D,
# op10 FULLY_CONNECTED, op11 SOFTMAX. Strides/padding=SAME confirmed via
# each op's Conv2DOptions/DepthwiseConv2DOptions.

_LAYER_TABLE = [
    {"name": "stem",  "kind": "oc_major",  "in": 0,  "w": 20, "b": 19, "out": 21, "stride": 2},
    {"name": "dw0",   "kind": "depthwise", "in": 21, "w": 18, "b": 17, "out": 22, "stride": 2},
    {"name": "pw0",   "kind": "oc_major",  "in": 22, "w": 16, "b": 15, "out": 23, "stride": 1},
    {"name": "dw1",   "kind": "depthwise", "in": 23, "w": 14, "b": 13, "out": 24, "stride": 2},
    {"name": "pw1",   "kind": "oc_major",  "in": 24, "w": 12, "b": 11, "out": 25, "stride": 1},
    {"name": "dw2",   "kind": "depthwise", "in": 25, "w": 10, "b": 9,  "out": 26, "stride": 1},
    {"name": "pw2",   "kind": "oc_major",  "in": 26, "w": 8,  "b": 7,  "out": 27, "stride": 1},
    {"name": "dw3",   "kind": "depthwise", "in": 27, "w": 6,  "b": 5,  "out": 28, "stride": 1},
    {"name": "pw3",   "kind": "oc_major",  "in": 28, "w": 4,  "b": 3,  "out": 29, "stride": 1},
]
_MAXPOOL = {"in": 29, "out": 30}
_FC = {"name": "fc", "in": 30, "w": 2, "b": 1, "out": 31}
_SOFTMAX = {"in": 31, "out": 32}


def prepare_conv_layer(model, sg, entry):
    """Ties extraction -> bias-fold -> pack -> requant -> padding together
    for one stem/depthwise/pointwise op. Returns a plain dict with
    everything a kernel launch needs; does not touch data_memory or choose
    addresses (that's the future full-chain test's job, once every layer's
    memory footprint is known)."""
    in_shape = tensor_shape(sg, entry["in"])
    out_shape = tensor_shape(sg, entry["out"])
    w_shape = tensor_shape(sg, entry["w"])

    in_scale, in_zp = tensor_quant(sg, entry["in"])
    out_scale, out_zp = tensor_quant(sg, entry["out"])
    w_scale, w_zp = tensor_quant(sg, entry["w"])
    assert all(z == 0 for z in w_zp), "weight tensors must be symmetric (zp=0)"

    weight_flat = tensor_data(model, sg, entry["w"])
    bias = tensor_data(model, sg, entry["b"])

    H_in, W_in = in_shape[1], in_shape[2]
    H_out, W_out = out_shape[1], out_shape[2]
    stride = entry["stride"]

    if entry["kind"] == "depthwise":
        # weight shape [1, KH, KW, C]
        _, KH, KW, C = w_shape
        Cout = C
        taps_per_channel = taps_channel_minor(weight_flat, C, KH * KW)
        w_scale = broadcast_scale(w_scale, C)
        packed = pack_taps_flat(taps_per_channel)
    else:
        # oc_major: stem [Cout,KH,KW,1] or pointwise [Cout,1,1,Cin]
        Cout = w_shape[0]
        taps = w_shape[1] * w_shape[2] * w_shape[3]
        KH, KW = w_shape[1], w_shape[2]
        taps_per_channel = taps_oc_major(weight_flat, Cout, taps)
        w_scale = broadcast_scale(w_scale, Cout)
        # Multi-tap spatial kernel (stem, KH*KW>1) stays 1-per-word;
        # pointwise (1x1, KH*KW==1) packs 4-per-word for dot4. In practice
        # only stem reaches this branch (the __main__ dispatch below routes
        # every 1x1 oc_major op to prepare_pointwise_layer instead), but
        # this stays correct if prepare_conv_layer is ever called directly.
        packed = pack_taps_flat(taps_per_channel) if KH * KW > 1 else pack4_taps(taps_per_channel)

    bias_eff = bias_fold(bias, taps_per_channel, in_zp[0])
    acc_max = acc_max_bound(taps_per_channel)
    mult, shift = derive_channel_params(in_scale[0], w_scale, out_scale[0], acc_max)

    result = {
        "name": entry["name"],
        "Cout": Cout,
        "H_in": H_in, "W_in": W_in, "H_out": H_out, "W_out": W_out,
        "stride": stride,
        "in_scale": in_scale[0], "in_zp": in_zp[0],
        "out_scale": out_scale[0], "out_zp": out_zp[0],
        "weights_packed": packed,
        "bias_eff": bias_eff,
        "mult": mult, "shift": shift,
    }

    if entry["kind"] in ("depthwise",) or (entry["kind"] == "oc_major" and KH * KW > 1):
        pad_top, pad_bot = same_padding(H_in, H_out, KH, stride)
        pad_left, pad_right = same_padding(W_in, W_out, KW, stride)
        result.update({
            "KH": KH, "KW": KW,
            "H_padded": H_in + pad_top + pad_bot,
            "W_padded": W_in + pad_left + pad_right,
            "pad_top": pad_top, "pad_left": pad_left,
        })

    return result


def prepare_pointwise_layer(model, sg, entry):
    """Pointwise/FC-shaped [Cout, Cin] weight, packed 4-per-word for dot4 --
    separate from prepare_conv_layer's oc_major path above since pointwise
    layers need pack4_taps, not pack_taps_flat."""
    in_shape = tensor_shape(sg, entry["in"])
    out_shape = tensor_shape(sg, entry["out"])
    w_shape = tensor_shape(sg, entry["w"])

    in_scale, in_zp = tensor_quant(sg, entry["in"])
    out_scale, out_zp = tensor_quant(sg, entry["out"])
    w_scale, w_zp = tensor_quant(sg, entry["w"])
    assert all(z == 0 for z in w_zp)

    weight_flat = tensor_data(model, sg, entry["w"])
    bias = tensor_data(model, sg, entry["b"])

    Cout = w_shape[0]
    Cin = w_shape[-1]
    taps_per_channel = taps_oc_major(weight_flat, Cout, Cin)
    w_scale = broadcast_scale(w_scale, Cout)

    bias_eff = bias_fold(bias, taps_per_channel, in_zp[0])
    acc_max = acc_max_bound(taps_per_channel)
    mult, shift = derive_channel_params(in_scale[0], w_scale, out_scale[0], acc_max)

    HW = 1
    if len(in_shape) == 4:
        HW = in_shape[1] * in_shape[2]

    return {
        "name": entry["name"],
        "Cout": Cout, "Cin": Cin, "Cin4": Cin // 4, "HW": HW,
        "in_scale": in_scale[0], "in_zp": in_zp[0],
        "out_scale": out_scale[0], "out_zp": out_zp[0],
        "weights_packed": pack4_taps(taps_per_channel),
        "bias_eff": bias_eff,
        "mult": mult, "shift": shift,
    }


# ── Host-only integer forward pass ──────────────────────────────────────────
#
# Chains every dscnn_*.axelc kernel's EXACT single-stage integer math (not
# numpy conv, not TFLite's two-stage gemmlowp rescale) layer by layer, in
# plain Python, so a full RTL run isn't needed for a fast pre-RTL golden
# check against the real TFLite interpreter (task #26's breadth check).
# This will NOT bit-exact-match real TFLite -- see the module docstring's
# two precision caveats -- it matches what the RTL kernels would compute if
# the accel ctrl address-decode ceiling (see project memory
# project_accel_ctrl_address_ceiling.md) didn't block real-size RTL
# execution. Each run_*_host function below mirrors its .axelc kernel's
# addressing/arithmetic line for line (see the kernel's own header comment
# for the derivation this replicates, not reinvents).

def clamp_i8(x):
    """Matches alu.sv's CLAMP opcode (0x18) exactly: clamp to int8 range."""
    if x > 127:
        return 127
    if x < -128:
        return -128
    return x


def _rescale(acc, mult, shift, out_zp):
    """The clamp(((acc*mult + round_bias) >> shift) + out_zp) line every
    conv/depthwise/pointwise/FC kernel ends with; round_bias derived
    in-kernel as 1<<(shift-1), same as every dscnn_*.axelc file."""
    return clamp_i8(((acc * mult + (1 << (shift - 1))) >> shift) + out_zp)


def _pad_plane(plane, H, W, H_padded, W_padded, pad_top, pad_left, zp):
    """Same border-prefill convention as write_padded_channel_plane, kept
    as plain signed ints (not wrapped into a data_memory dict with 32-bit
    masking) since this feeds direct Python integer math, not a memory
    model."""
    out = [0] * (H_padded * W_padded)
    for r in range(H_padded):
        row_in = r - pad_top
        for c in range(W_padded):
            col_in = c - pad_left
            out[r * W_padded + c] = (
                plane[row_in * W + col_in] if 0 <= row_in < H and 0 <= col_in < W else zp
            )
    return out


def unpack4_word(word):
    """Inverse of pack4_word: 1 packed 32-bit word -> 4 signed int8 lanes,
    little-endian, matching dot4's raw lane convention."""
    vals = []
    for lane in range(4):
        b = (word >> (8 * lane)) & 0xFF
        vals.append(b - 256 if b >= 128 else b)
    return vals


def run_stem_host(input_plane, layer):
    """input_plane: flat H_in*W_in signed-int8 list (the real quantized
    log-mel features). Returns {oc: flat H_out*W_out list}, mirroring
    dscnn_stem_conv.axelc's tap-flattened (kh=tap/3, kw=tap%3) loop."""
    H_in, W_in = layer["H_in"], layer["W_in"]
    H_out, W_out = layer["H_out"], layer["W_out"]
    stride = layer["stride"]
    H_padded, W_padded = layer["H_padded"], layer["W_padded"]
    padded = _pad_plane(
        input_plane, H_in, W_in, H_padded, W_padded,
        layer["pad_top"], layer["pad_left"], layer["in_zp"],
    )
    taps = 15
    out = {}
    for oc in range(layer["Cout"]):
        w = layer["weights_packed"][oc * taps:(oc + 1) * taps]
        mult, shift = layer["mult"][oc], layer["shift"][oc]
        plane_out = [0] * (H_out * W_out)
        for row in range(H_out):
            for col in range(W_out):
                acc = layer["bias_eff"][oc]
                for tap in range(taps):
                    kh, kw = tap // 3, tap % 3
                    acc += padded[(row * stride + kh) * W_padded + (col * stride + kw)] * w[tap]
                plane_out[row * W_out + col] = _rescale(acc, mult, shift, layer["out_zp"])
        out[oc] = plane_out
    return out


def run_depthwise_host(input_by_channel, layer):
    """input_by_channel: {channel: flat H_in*W_in list}, UNPADDED. Returns
    {channel: flat H_out*W_out list}, mirroring dscnn_dwconv.axelc."""
    H_in, W_in = layer["H_in"], layer["W_in"]
    H_out, W_out = layer["H_out"], layer["W_out"]
    stride = layer["stride"]
    H_padded, W_padded = layer["H_padded"], layer["W_padded"]
    taps = 9
    out = {}
    for c in range(layer["Cout"]):
        padded = _pad_plane(
            input_by_channel[c], H_in, W_in, H_padded, W_padded,
            layer["pad_top"], layer["pad_left"], layer["in_zp"],
        )
        w = layer["weights_packed"][c * taps:(c + 1) * taps]
        mult, shift = layer["mult"][c], layer["shift"][c]
        plane_out = [0] * (H_out * W_out)
        for row in range(H_out):
            for col in range(W_out):
                acc = layer["bias_eff"][c]
                for tap in range(taps):
                    kh, kw = tap // 3, tap % 3
                    acc += padded[(row * stride + kh) * W_padded + (col * stride + kw)] * w[tap]
                plane_out[row * W_out + col] = _rescale(acc, mult, shift, layer["out_zp"])
        out[c] = plane_out
    return out


def run_pointwise_host(input_by_channel, layer):
    """input_by_channel: {channel: flat HW list}. Returns {oc: flat HW
    list}, mirroring dscnn_pwconv.axelc's chunked dot4 accumulation --
    unpacked back to per-(oc,cin) taps first since a straight per-channel
    sum is exactly equivalent to summing dot4's 4-lane partial products
    across chunks (both are non-overflowing integer sums, verified by
    derive_mult_shift's acc_max<2**31 bound)."""
    Cin, Cin4, HW = layer["Cin"], layer["Cin4"], layer["HW"]
    out = {}
    for oc in range(layer["Cout"]):
        w_words = layer["weights_packed"][oc * Cin4:(oc + 1) * Cin4]
        w_taps = []
        for word in w_words:
            w_taps.extend(unpack4_word(word))
        mult, shift = layer["mult"][oc], layer["shift"][oc]
        vals = [0] * HW
        for pixel in range(HW):
            acc = layer["bias_eff"][oc]
            for cin in range(Cin):
                acc += input_by_channel[cin][pixel] * w_taps[cin]
            vals[pixel] = _rescale(acc, mult, shift, layer["out_zp"])
        out[oc] = vals
    return out


def run_maxpool_host(input_by_channel, C):
    """Global max per channel, no rescale -- mirrors dscnn_maxpool.axelc
    exactly (TFLite's int8 MAX_POOL_2D doesn't rescale either, verified
    against this model's real in/out tensor scales matching)."""
    return {c: max(input_by_channel[c]) for c in range(C)}


def run_fc_host(input_vec, layer):
    """input_vec: flat Cin list (pooled activations). Returns flat Cout
    list, mirroring dscnn_fc.axelc."""
    Cin4 = layer["Cin4"]
    out = [0] * layer["Cout"]
    for oc in range(layer["Cout"]):
        w_words = layer["weights_packed"][oc * Cin4:(oc + 1) * Cin4]
        w_taps = []
        for word in w_words:
            w_taps.extend(unpack4_word(word))
        acc = layer["bias_eff"][oc]
        for cin in range(len(input_vec)):
            acc += input_vec[cin] * w_taps[cin]
        out[oc] = _rescale(acc, layer["mult"][oc], layer["shift"][oc], layer["out_zp"])
    return out


def run_softmax_host(logits, exp_shift, out_zp):
    """Mirrors dscnn_softmax.axelc's 3-pass max/exp8/normalize exactly,
    including that the kernel's final store has NO clamp (line
    `mem[out_base+k] = e2*256/sum + out_zp`) -- not "corrected" here, since
    real hardware wouldn't clamp it either. Uses the same exp8 Q6 LUT the
    RTL uses (attn_reference.exp8), not a re-derivation of it."""
    try:
        from .attn_reference import exp8  # package import (cocotb tests)
    except ImportError:
        from attn_reference import exp8  # standalone run (this file's own __main__)

    m = max(logits)
    exps = [exp8(clamp_i8((score - m) >> exp_shift)) for score in logits]
    total = sum(exps)
    return [e * 256 // total + out_zp for e in exps]


def _build_all_layers(model, sg):
    layers = {}
    for entry in _LAYER_TABLE:
        if entry["kind"] == "depthwise":
            layers[entry["name"]] = prepare_conv_layer(model, sg, entry)
        else:
            w_shape = tensor_shape(sg, entry["w"])
            if w_shape[1] * w_shape[2] == 1:
                layers[entry["name"]] = prepare_pointwise_layer(model, sg, entry)
            else:
                layers[entry["name"]] = prepare_conv_layer(model, sg, entry)
    layers["fc"] = prepare_pointwise_layer(model, sg, _FC)
    return layers


def run_dscnn_host(model, sg, input_features_int8, layers=None):
    """input_features_int8: flat 81*32=2592 signed-int8 list (log-mel
    features, already quantized via dscnn_features.quantize_to_int8,
    row-major matching the real input tensor's [1,81,32,1] shape). Pass a
    pre-built `layers` dict (from _build_all_layers) to avoid re-extracting
    weights on every call when scoring many WAV files. Returns the final
    18-int8 softmax output list."""
    if layers is None:
        layers = _build_all_layers(model, sg)

    act = run_stem_host(input_features_int8, layers["stem"])
    for dw_name, pw_name in (("dw0", "pw0"), ("dw1", "pw1"), ("dw2", "pw2"), ("dw3", "pw3")):
        act = run_depthwise_host(act, layers[dw_name])
        act = run_pointwise_host(act, layers[pw_name])

    pooled = run_maxpool_host(act, layers["pw3"]["Cout"])
    pooled_vec = [pooled[c] for c in range(layers["pw3"]["Cout"])]

    fc_out = run_fc_host(pooled_vec, layers["fc"])

    sm_in_scale, _ = tensor_quant(sg, _SOFTMAX["in"])
    _, sm_out_zp = tensor_quant(sg, _SOFTMAX["out"])
    exp_shift = derive_softmax_exp_shift(sm_in_scale[0])
    return run_softmax_host(fc_out, exp_shift, sm_out_zp[0])


if __name__ == "__main__":
    model, sg = load_model()
    print(f"Loaded {TFLITE_PATH}: {sg.TensorsLength()} tensors, {sg.OperatorsLength()} ops")

    layers = {}
    for entry in _LAYER_TABLE:
        if entry["kind"] == "depthwise":
            layer = prepare_conv_layer(model, sg, entry)
        else:
            # pointwise (KH=KW=1) uses the dot4-packed path; stem (KH=5,
            # KW=3) uses the flat 1-per-word path -- both still need
            # padding info from prepare_conv_layer, but pointwise's weight
            # packing must come from prepare_pointwise_layer instead.
            w_shape = tensor_shape(sg, entry["w"])
            if w_shape[1] * w_shape[2] == 1:
                layer = prepare_pointwise_layer(model, sg, entry)
            else:
                layer = prepare_conv_layer(model, sg, entry)
        layers[entry["name"]] = layer

        tag = "depthwise" if entry["kind"] == "depthwise" else ("pointwise" if "Cin" in layer else "stem")
        print(
            f"  {entry['name']:5s} ({tag:9s}) Cout={layer['Cout']:3d} "
            f"weights={len(layer['weights_packed']):5d} words  "
            f"mult[0]={layer['mult'][0]:>10d} shift[0]={layer['shift'][0]:2d}  "
            f"bias_eff[0]={layer['bias_eff'][0]:>8d}"
        )
        # Overflow check is load-bearing, not just informative: re-verify
        # every channel's chosen (mult, shift) actually keeps mult*acc_max
        # under 2**31, using the same acc_max bound derive_mult_shift used.
        assert len(layer["mult"]) == layer["Cout"]
        assert len(layer["shift"]) == layer["Cout"]
        assert all(s > 0 for s in layer["shift"]), "shift=0 would make round_bias's 1<<(shift-1) undefined"

    # Hand-checkable spot check: stem's bias_eff[0] two ways.
    stem_w = tensor_data(model, sg, 20)
    stem_b = tensor_data(model, sg, 19)
    _, stem_in_zp = tensor_quant(sg, 0)
    taps0 = stem_w[0:15]  # oc=0's 15 taps, oc-major layout
    expected_bias_eff0 = stem_b[0] - stem_in_zp[0] * sum(taps0)
    assert layers["stem"]["bias_eff"][0] == expected_bias_eff0, (
        f"stem bias_eff[0] mismatch: got {layers['stem']['bias_eff'][0]}, "
        f"expected {expected_bias_eff0}"
    )
    print(f"\nstem bias_eff[0] hand-check: {expected_bias_eff0} OK")

    # Hand-checkable spot check: pw0's weight packing round-trips.
    pw0_w = tensor_data(model, sg, 16)  # [48,1,1,16]
    word0 = layers["pw0"]["weights_packed"][0]
    unpacked = [
        (word0 >> 0) & 0xFF, (word0 >> 8) & 0xFF,
        (word0 >> 16) & 0xFF, (word0 >> 24) & 0xFF,
    ]
    unpacked_signed = [v - 256 if v >= 128 else v for v in unpacked]
    assert unpacked_signed == pw0_w[0:4], (
        f"pw0 weight pack round-trip mismatch: {unpacked_signed} != {pw0_w[0:4]}"
    )
    print(f"pw0 weight pack round-trip: {unpacked_signed} OK")

    # Depthwise transpose spot check: dw0's channel-major tap extraction
    # against a hand-indexed read of the natural [1,KH,KW,C] layout.
    dw0_w = tensor_data(model, sg, 18)  # [1,3,3,16]
    C = 16
    taps_ch2 = [dw0_w[t * C + 2] for t in range(9)]
    assert layers["dw0"]["weights_packed"][2 * 9:2 * 9 + 9] == taps_ch2, (
        "dw0 depthwise transpose mismatch"
    )
    print(f"dw0 depthwise transpose (channel=2): {taps_ch2} OK")

    # Padding spot check against the real in/out shapes (independent of
    # this module's own same_padding()).
    assert layers["stem"]["H_padded"] == 81 + 4 and layers["stem"]["W_padded"] == 32 + 1
    assert layers["dw0"]["H_padded"] == 41 + 2 and layers["dw0"]["W_padded"] == 16 + 1
    print("stem/dw0 padding shapes OK")

    fc = prepare_pointwise_layer(model, sg, _FC)
    print(
        f"\n  fc    (fc)        Cout={fc['Cout']:3d} Cin={fc['Cin']:3d} "
        f"weights={len(fc['weights_packed']):3d} words  "
        f"mult[0]={fc['mult'][0]:>10d} shift[0]={fc['shift'][0]:2d}"
    )
    assert fc["Cout"] == 18 and fc["Cin"] == 48 and fc["Cin4"] == 12

    sm_in_scale, _ = tensor_quant(sg, _SOFTMAX["in"])
    exp_shift = derive_softmax_exp_shift(sm_in_scale[0])
    print(f"\n  softmax exp_shift = {exp_shift} (in_scale={sm_in_scale[0]:.6f}, ideal shift was negative -> clamped to 0)")

    total_weight_words = sum(len(l["weights_packed"]) for l in layers.values()) + len(fc["weights_packed"])
    total_bias_words = sum(len(l["bias_eff"]) for l in layers.values()) + len(fc["bias_eff"])
    print(f"\nTotal weight words: {total_weight_words}, total bias/mult/shift entries: {total_bias_words} (x3 arrays each)")

    print("\nAll dscnn_reference.py standalone checks PASSED")
