"""
Exact reimplementation of the gemmlowp/TFLite fixed-point primitives used by
TFLite's real int8 quantized kernels (conv/depthwise/FC output requant, and
SOFTMAX). Transcribed directly from the actual TFLite/gemmlowp source
(tensorflow/lite/kernels/internal/{quantization_util.cc,common.h},
tensorflow/lite/kernels/internal/reference/softmax.h,
tensorflow/lite/kernels/activations.cc, and gemmlowp/fixedpoint/fixedpoint.h)
-- not approximated -- so dscnn_reference.py's host-side numbers are
bit-exact against a real TFLite interpreter, and the GPU kernels (which
replicate this same math using the IMULH primitive) can be verified against
it directly rather than against a looser tolerance.

All functions operate on plain Python ints representing 32-bit two's
complement values (kept in range via `i32`/`u32` below), mirroring C++'s
int32_t/uint32_t wraparound semantics exactly -- this is deliberate: TFLite's
own reference kernels rely on that wraparound (`Add`/`Mul` in fixedpoint.h
are documented "Not saturating. Overflow is undefined behavior" but wrap in
practice on every real target, same assumption axelcc's own IMUL makes).
"""


def i32(x):
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x


def u32(x):
    return x & 0xFFFFFFFF


def _trunc_div(a, b):
    """C++ integer division: truncates toward zero (Python // floors)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def count_leading_zeros_u32(x):
    x = u32(x)
    if x == 0:
        return 32
    return 32 - x.bit_length()


def _round_half_away_from_zero(x):
    """C++'s std::round (TfLiteRound): half-away-from-zero, NOT Python's
    round()-half-to-even -- matters for QuantizeMultiplier's exact-tie edge
    case (astronomically unlikely with real scales, but this module's whole
    point is not assuming "unlikely to matter")."""
    import math
    return math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)


# ── gemmlowp/fixedpoint.h ───────────────────────────────────────────────────

def srdhm(a, b):
    """SaturatingRoundingDoublingHighMul(int32_t a, int32_t b)."""
    a, b = i32(a), i32(b)
    if a == b and a == -(1 << 31):
        return (1 << 31) - 1
    ab64 = a * b  # exact (Python big int)
    nudge = (1 << 30) if ab64 >= 0 else (1 - (1 << 30))
    return i32(_trunc_div(ab64 + nudge, 1 << 31))


def rdpot(x, exponent):
    """RoundingDivideByPOT(int32_t x, exponent): correctly-rounded x/2**exponent."""
    x = i32(x)
    if exponent == 0:
        return x
    mask = (1 << exponent) - 1
    remainder = x & mask
    threshold = (mask >> 1) + (1 if x < 0 else 0)
    result = x >> exponent  # Python's >> on ints is an arithmetic (floor) shift, matching C++ signed >> on real hardware
    if remainder > threshold:
        result += 1
    return i32(result)


def srmbpot(x, exponent):
    """SaturatingRoundingMultiplyByPOT(int32_t x, exponent): +exponent saturating left shift, -exponent = rdpot."""
    x = i32(x)
    if exponent == 0:
        return x
    if exponent < 0:
        return rdpot(x, -exponent)
    threshold = (1 << (31 - exponent)) - 1
    if x > threshold:
        return (1 << 31) - 1
    if x < -threshold:
        return -(1 << 31)
    return i32(x << exponent)


def rescale(raw, src_integer_bits, dst_integer_bits):
    """gemmlowp::Rescale<dst>(FixedPoint<src> x)."""
    return srmbpot(raw, src_integer_bits - dst_integer_bits)


def rounding_half_sum(a, b):
    a, b = i32(a), i32(b)
    s = a + b
    sign = 1 if s >= 0 else -1
    return i32(_trunc_div(s + sign, 2))


# Q0.31 constants transcribed verbatim from fixedpoint.h's
# GEMMLOWP_CHECKED_FIXEDPOINT_CONSTANT invocations (raw int32 values, not
# recomputed from the doubles -- these ARE the ground truth).
_EXP_CONST_TERM = 1895147668       # exp(-1/8), Q0.31
_EXP_CONST_1_OVER_3 = 715827883    # 1/3,        Q0.31
_EXP_BARREL = [                    # (exponent, exp(-2**exponent) as Q0.31)
    (-2, 1672461947), (-1, 1302514674), (0, 790015084),
    (1, 290630308), (2, 39332535), (3, 720401), (4, 242),
]
_F2_ONE = 1 << 29                  # FixedPoint<2>::One(), 2 integer bits, 29 fractional bits
_RECIP_CONST_48_OVER_17 = 1515870810   # F2, 48/17
_RECIP_CONST_NEG32_OVER_17 = -1010580540  # F2, -32/17


def _exp_on_interval_neg_quarter_to_0(a_raw):
    """exp(x) for x in [-1/4, 0), FixedPoint<0> in and out (Q0.31)."""
    x = i32(a_raw + (1 << 28))  # + ConstantPOT<-3>() = 1 << (31 + (-3))
    x2 = srdhm(x, x)
    x3 = srdhm(x2, x)
    x4 = srdhm(x2, x2)
    x4_over_4 = rdpot(x4, 2)
    tmp = srdhm(i32(x4_over_4 + x3), _EXP_CONST_1_OVER_3)
    tmp = i32(tmp + x2)
    poly = rdpot(tmp, 1)
    inner = i32(x + poly)
    return i32(_EXP_CONST_TERM + srdhm(_EXP_CONST_TERM, inner))


def exp_on_negative_values(a_raw, integer_bits):
    """exp(x) for x <= 0, FixedPoint<integer_bits> in, FixedPoint<0> out (Q0.31).

    `integer_bits` must be <= 5 (the >5 saturation-clamp branch in the real
    gemmlowp source is not implemented -- this module only ever calls this
    with integer_bits=5, TFLite SOFTMAX's kScaledDiffIntegerBits).
    """
    assert integer_bits <= 5
    fractional_bits = 31 - integer_bits
    one_quarter = 1 << (fractional_bits - 2)
    mask = one_quarter - 1
    a_mod_quarter_minus_one_quarter = i32((a_raw & mask) - one_quarter)
    rescaled = srmbpot(a_mod_quarter_minus_one_quarter, integer_bits)
    result = _exp_on_interval_neg_quarter_to_0(rescaled)
    remainder = i32(a_mod_quarter_minus_one_quarter - a_raw)

    for exponent, mult_raw in _EXP_BARREL:
        if integer_bits > exponent:
            shift_amount = fractional_bits + exponent
            if remainder & (1 << shift_amount):
                result = srdhm(result, mult_raw)

    if a_raw == 0:
        result = (1 << 31) - 1  # FixedPoint<0>::One() == ScalarRawMax()
    return result


def one_over_one_plus_x_for_x_in_0_1(a_raw):
    """1/(1+x) for x in (0,1), FixedPoint<0> in and out (Q0.31), 3-step Newton-Raphson."""
    half_denominator = rounding_half_sum(a_raw, (1 << 31) - 1)
    x = i32(_RECIP_CONST_48_OVER_17 + srdhm(half_denominator, _RECIP_CONST_NEG32_OVER_17))
    for _ in range(3):
        half_denominator_times_x = srdhm(half_denominator, x)
        one_minus = i32(_F2_ONE - half_denominator_times_x)
        x = i32(x + rescale(srdhm(x, one_minus), 4, 2))
    # return Rescale<0>(ExactMulByPot<-1>(x)): ExactMulByPot<-1> reinterprets
    # x's raw bits from F2 (2 integer bits) to F1 (1 integer bit) with NO
    # shift (that's what "exact" means -- pure bookkeeping), so the only
    # real arithmetic left is Rescale<0> from F1->F0: exponent=1-0=1, a
    # saturating left shift by 1 -- NOT a direct F2->F0 rescale (exponent 2).
    return rescale(x, 1, 0)


def get_reciprocal(x, x_integer_digits):
    """GetReciprocal(int32_t x, x_integer_digits, &num_bits_over_unit) -> (raw, num_bits_over_unit)."""
    x_u = u32(x)
    headroom_plus_one = count_leading_zeros_u32(x_u)
    num_bits_over_unit = x_integer_digits - headroom_plus_one
    shifted = u32(x_u << headroom_plus_one)
    shifted_sum_minus_one = i32(u32(shifted - (1 << 31)))
    raw = one_over_one_plus_x_for_x_in_0_1(shifted_sum_minus_one)
    return raw, num_bits_over_unit


# ── quantization_util.cc ────────────────────────────────────────────────────

def quantize_multiplier(double_multiplier):
    """QuantizeMultiplier: double -> (quantized_multiplier: Q0.31 int32, shift).

    Positive shift = left-shift (multiplier > 1); negative = right-shift
    (multiplier < 1, the common case for conv/depthwise/FC output requant).
    """
    if double_multiplier == 0.0:
        return 0, 0
    import math
    mantissa, exponent = math.frexp(double_multiplier)  # double_multiplier == mantissa * 2**exponent, 0.5<=|mantissa|<1
    shift = exponent
    q_fixed = int(_round_half_away_from_zero(mantissa * (1 << 31)))
    if q_fixed == (1 << 31):
        q_fixed //= 2
        shift += 1
    if shift < -31:
        shift = 0
        q_fixed = 0
    return i32(q_fixed), shift


def multiply_by_quantized_multiplier(x, quantized_multiplier, shift):
    """MultiplyByQuantizedMultiplier(int32_t x, int32_t quantized_multiplier, int shift).

    The general (either-sign-shift) form actually used at conv/FC/depthwise
    output requantization time (common.h's non-NEON, double-rounding path,
    which is what TFLITE_SINGLE_ROUNDING=0 -- the default -- selects).
    """
    left_shift = max(shift, 0)
    right_shift = -min(shift, 0)
    return rdpot(srdhm(i32(x << left_shift), quantized_multiplier), right_shift)


def calculate_input_radius(input_integer_bits, input_left_shift, total_signed_bits=31):
    import math
    max_input_rescaled = (
        1.0 * ((1 << input_integer_bits) - 1)
        * (1 << (total_signed_bits - input_integer_bits))
        / (1 << input_left_shift)
    )
    return int(math.floor(max_input_rescaled))


def preprocess_softmax_scaling(beta, input_scale, input_integer_bits):
    """PreprocessSoftmaxScaling -> (quantized_multiplier, left_shift), both int."""
    max_real_multiplier = (1 << 31) - 1.0
    input_beta_real_multiplier = min(
        beta * input_scale * (1 << (31 - input_integer_bits)), max_real_multiplier
    )
    # QuantizeMultiplierGreaterThanOne requires > 1; for typical FC-logit
    # input scales this always holds in practice (input_scale*2**26-ish).
    return quantize_multiplier(input_beta_real_multiplier)


# ── reference/softmax.h (int8/uint8 quantized path) ────────────────────────

_K_SCALED_DIFF_INTEGER_BITS = 5
_K_ACCUMULATION_INTEGER_BITS = 12


def tflite_softmax_int8(input_int8, input_scale, out_zp=-128, beta=1.0):
    """Bit-exact reimplementation of reference_ops::Softmax<int8_t,int8_t>.

    `input_int8`: list of raw int8 values (already includes the input
    tensor's own zero point -- softmax's max-subtraction cancels it exactly
    like the real kernel, no explicit zero-point handling needed).
    Output scale/zero_point for int8 softmax is always a hardware constant
    in TFLite (1/256, -128); out_zp is exposed as a parameter only for
    clarity, not because TFLite lets it vary.
    """
    input_multiplier, input_left_shift = preprocess_softmax_scaling(
        beta, input_scale, _K_SCALED_DIFF_INTEGER_BITS
    )
    diff_min = -calculate_input_radius(_K_SCALED_DIFF_INTEGER_BITS, input_left_shift)

    max_in_row = max(input_int8)

    sum_of_exps = 0
    for v in input_int8:
        input_diff = i32(v - max_in_row)
        if input_diff >= diff_min:
            input_diff_rescaled = multiply_by_quantized_multiplier(
                input_diff, input_multiplier, input_left_shift
            )
            exp_val = exp_on_negative_values(input_diff_rescaled, _K_SCALED_DIFF_INTEGER_BITS)
            sum_of_exps = i32(sum_of_exps + rescale(exp_val, 0, _K_ACCUMULATION_INTEGER_BITS))

    shifted_scale, num_bits_over_unit = get_reciprocal(sum_of_exps, _K_ACCUMULATION_INTEGER_BITS)
    exponent = num_bits_over_unit + 31 - 8  # sizeof(int8_t)*8 == 8
    assert 0 <= exponent <= 31

    output = []
    for v in input_int8:
        input_diff = i32(v - max_in_row)
        if input_diff >= diff_min:
            input_diff_rescaled = multiply_by_quantized_multiplier(
                input_diff, input_multiplier, input_left_shift
            )
            exp_val = exp_on_negative_values(input_diff_rescaled, _K_SCALED_DIFF_INTEGER_BITS)
            unsat_output = rdpot(srdhm(shifted_scale, exp_val), exponent)
            shifted_output = i32(unsat_output + (-128))
            output.append(max(-128, min(127, shifted_output)))
        else:
            output.append(-128)
    return output
