import cocotb
from cocotb.triggers import Timer

"""Combinational Circuits Like ALU don't need a clock, but we can still use timers to wait for signal propagation.
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def pack_int8(lane0, lane1, lane2, lane3):
    """Pack 4 signed INT8 values into a 32-bit word.
    lane0 occupies bits [7:0], lane3 occupies bits [31:24].
    Negative values are automatically masked to 8-bit two's complement.
    """
    return (
        (lane0 & 0xFF)        |
        ((lane1 & 0xFF) << 8) |
        ((lane2 & 0xFF) << 16)|
        ((lane3 & 0xFF) << 24)
    )

def to_signed32(v):
    """Interpret a 32-bit cocotb value as a signed Python int."""
    v = int(v) & 0xFFFFFFFF
    return v - 0x100000000 if v >= 0x80000000 else v

def u32(v):
    """Convert a signed Python int to unsigned 32-bit for driving DUT inputs."""
    return v & 0xFFFFFFFF


# ── Existing tests ────────────────────────────────────────────────────────────

@cocotb.test()
async def test_ADD(dut):

    dut.operand1.value = 0
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0

    dut.operand1.value = 5
    dut.operand2.value = 3
    dut.op_select.value = 0x01 # ADD
    await Timer(1, unit="ns")
    assert dut.result.value == 8, f"Expected 8 got {dut.result.value}"

@cocotb.test()
async def test_SUB(dut):

    dut.operand1.value = 0
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0

    dut.operand1.value = 10
    dut.operand2.value = 4
    dut.op_select.value = 0x02 # SUB
    await Timer(1, unit="ns")
    assert dut.result.value == 6, f"Expected 6 got {dut.result.value}"

@cocotb.test()
async def test_CMP_equal(dut):

    dut.operand1.value = 0
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0

    dut.operand1.value = 5
    dut.operand2.value = 5
    dut.op_select.value = 0x0D # CMP
    await Timer(1, unit="ns")
    assert dut.nzp_flag.value == 0b010, f"Expected zero flag set got {dut.nzp_flag.value}"

@cocotb.test()
async def test_CMP_greater(dut):

    dut.operand1.value = 0
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0

    dut.operand1.value = 7
    dut.operand2.value = 3
    dut.op_select.value = 0x0D # CMP
    await Timer(1, unit="ns")
    assert dut.nzp_flag.value == 0b001, f"Expected positive flag set got {dut.nzp_flag.value}"

@cocotb.test()
async def test_CMP_less(dut):

    dut.operand1.value = 0
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0

    dut.operand1.value = 2
    dut.operand2.value = 9
    dut.op_select.value = 0x0D # CMP
    await Timer(1, unit="ns")
    assert dut.nzp_flag.value == 0b100, f"Expected negative flag set got {dut.nzp_flag.value}"

@cocotb.test()
async def test_NOT(dut):

    dut.operand1.value = 0
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0

    dut.operand1.value = 0x00000000
    dut.op_select.value = 0x0B # NOT
    await Timer(1, unit="ns")
    assert dut.result.value == 0xFFFFFFFF, f"Expected 0xFFFFFFFF got {dut.result.value}"


# ── DOT4 (0x16) ───────────────────────────────────────────────────────────────
# operand1 = packed INT8 vec A (lane0=bits[7:0] ... lane3=bits[31:24])
# operand2 = packed INT8 vec B
# operand3 = INT32 accumulator (initial value of Rd)
# result   = operand3 + sum(A[i] * B[i])

@cocotb.test()
async def test_DOT4_positive(dut):
    """All positive lanes, zero accumulator.
    A=[1,2,3,4]  B=[1,2,3,4]  acc=0
    expected = 1+4+9+16 = 30
    """
    dut.operand1.value = pack_int8(1, 2, 3, 4)
    dut.operand2.value = pack_int8(1, 2, 3, 4)
    dut.operand3.value = 0
    dut.op_select.value = 0x16
    await Timer(1, unit="ns")
    assert to_signed32(dut.result.value) == 30, \
        f"DOT4 positive: expected 30, got {to_signed32(dut.result.value)}"

@cocotb.test()
async def test_DOT4_accumulate(dut):
    """Non-zero accumulator: result must add to existing Rd value.
    A=[1,1,1,1]  B=[2,2,2,2]  acc=10
    dot = 2+2+2+2 = 8, result = 18
    """
    dut.operand1.value = pack_int8(1, 1, 1, 1)
    dut.operand2.value = pack_int8(2, 2, 2, 2)
    dut.operand3.value = 10
    dut.op_select.value = 0x16
    await Timer(1, unit="ns")
    assert to_signed32(dut.result.value) == 18, \
        f"DOT4 accumulate: expected 18, got {to_signed32(dut.result.value)}"

@cocotb.test()
async def test_DOT4_mixed_signs(dut):
    """Mixed positive and negative lanes, zero accumulator.
    A=[1,-1,2,-2]  B=[3,4,5,6]  acc=0
    dot = 1*3 + (-1)*4 + 2*5 + (-2)*6 = 3-4+10-12 = -3
    """
    dut.operand1.value = pack_int8(1, -1, 2, -2)
    dut.operand2.value = pack_int8(3,  4, 5,  6)
    dut.operand3.value = 0
    dut.op_select.value = 0x16
    await Timer(1, unit="ns")
    assert to_signed32(dut.result.value) == -3, \
        f"DOT4 mixed signs: expected -3, got {to_signed32(dut.result.value)}"


# ── RELU (0x17) ───────────────────────────────────────────────────────────────
# result = (operand1 < 0) ? 0 : operand1  (signed comparison)

@cocotb.test()
async def test_RELU_positive(dut):
    """Positive input passes through unchanged."""
    dut.operand1.value = 42
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0x17
    await Timer(1, unit="ns")
    assert to_signed32(dut.result.value) == 42, \
        f"RELU positive: expected 42, got {to_signed32(dut.result.value)}"

@cocotb.test()
async def test_RELU_negative(dut):
    """Negative input is clamped to zero."""
    dut.operand1.value = u32(-7)
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0x17
    await Timer(1, unit="ns")
    assert to_signed32(dut.result.value) == 0, \
        f"RELU negative: expected 0, got {to_signed32(dut.result.value)}"

@cocotb.test()
async def test_RELU_zero(dut):
    """Zero input returns zero."""
    dut.operand1.value = 0
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0x17
    await Timer(1, unit="ns")
    assert to_signed32(dut.result.value) == 0, \
        f"RELU zero: expected 0, got {to_signed32(dut.result.value)}"


# ── CLAMP (0x18) ──────────────────────────────────────────────────────────────
# result = min(127, max(-128, operand1))  signed INT8 output range

@cocotb.test()
async def test_CLAMP_in_range(dut):
    """Value inside [-128, 127] passes through unchanged."""
    dut.operand1.value = 50
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0x18
    await Timer(1, unit="ns")
    assert to_signed32(dut.result.value) == 50, \
        f"CLAMP in-range: expected 50, got {to_signed32(dut.result.value)}"

@cocotb.test()
async def test_CLAMP_above_max(dut):
    """Value above 127 is clamped to 127."""
    dut.operand1.value = 200
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0x18
    await Timer(1, unit="ns")
    assert to_signed32(dut.result.value) == 127, \
        f"CLAMP above max: expected 127, got {to_signed32(dut.result.value)}"

@cocotb.test()
async def test_CLAMP_below_min(dut):
    """Value below -128 is clamped to -128."""
    dut.operand1.value = u32(-200)
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0x18
    await Timer(1, unit="ns")
    assert to_signed32(dut.result.value) == -128, \
        f"CLAMP below min: expected -128, got {to_signed32(dut.result.value)}"

@cocotb.test()
async def test_CLAMP_exact_boundary(dut):
    """Values exactly at +127 and -128 are not modified."""
    # Upper boundary
    dut.operand1.value = 127
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0x18
    await Timer(1, unit="ns")
    assert to_signed32(dut.result.value) == 127, \
        f"CLAMP boundary +127: expected 127, got {to_signed32(dut.result.value)}"

    # Lower boundary
    dut.operand1.value = u32(-128)
    dut.op_select.value = 0x18
    await Timer(1, unit="ns")
    assert to_signed32(dut.result.value) == -128, \
        f"CLAMP boundary -128: expected -128, got {to_signed32(dut.result.value)}"


# ── MAX (0x19) ────────────────────────────────────────────────────────────────
# result = (operand1 >= operand2) ? operand1 : operand2  signed comparison

@cocotb.test()
async def test_MAX_first_greater(dut):
    """operand1 > operand2: result is operand1."""
    dut.operand1.value = 10
    dut.operand2.value = 5
    dut.operand3.value = 0
    dut.op_select.value = 0x19
    await Timer(1, unit="ns")
    assert to_signed32(dut.result.value) == 10, \
        f"MAX first greater: expected 10, got {to_signed32(dut.result.value)}"

@cocotb.test()
async def test_MAX_second_greater(dut):
    """operand2 > operand1: result is operand2."""
    dut.operand1.value = 3
    dut.operand2.value = 8
    dut.operand3.value = 0
    dut.op_select.value = 0x19
    await Timer(1, unit="ns")
    assert to_signed32(dut.result.value) == 8, \
        f"MAX second greater: expected 8, got {to_signed32(dut.result.value)}"

@cocotb.test()
async def test_MAX_equal(dut):
    """Equal inputs: result is either operand (both are the same value)."""
    dut.operand1.value = 7
    dut.operand2.value = 7
    dut.operand3.value = 0
    dut.op_select.value = 0x19
    await Timer(1, unit="ns")
    assert to_signed32(dut.result.value) == 7, \
        f"MAX equal: expected 7, got {to_signed32(dut.result.value)}"

@cocotb.test()
async def test_MAX_both_negative(dut):
    """Both operands negative: result is the less-negative one.
    max(-3, -7) = -3
    """
    dut.operand1.value = u32(-3)
    dut.operand2.value = u32(-7)
    dut.operand3.value = 0
    dut.op_select.value = 0x19
    await Timer(1, unit="ns")
    assert to_signed32(dut.result.value) == -3, \
        f"MAX both negative: expected -3, got {to_signed32(dut.result.value)}"