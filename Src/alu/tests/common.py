from cocotb.triggers import Timer


# ── Opcode constants ──────────────────────────────────────────────────────────

OP_NOP   = 0x00
OP_ADD   = 0x01
OP_SUB   = 0x02
OP_MUL   = 0x03
OP_DIV   = 0x04
OP_MOD   = 0x05
OP_SHL   = 0x06
OP_SHR   = 0x07
OP_AND   = 0x08
OP_OR    = 0x09
OP_XOR   = 0x0A
OP_NOT   = 0x0B
OP_FMA   = 0x0C
OP_CMP   = 0x0D
OP_IMUL  = 0x13
OP_SAR   = 0x14
OP_DOT4  = 0x16
OP_RELU  = 0x17
OP_CLAMP = 0x18
OP_MAX   = 0x19
OP_MIN  = 0x1A
OP_EXP8 = 0x1B

MASK32 = 0xFFFFFFFF


# ── Integer helpers ───────────────────────────────────────────────────────────

def u32(v: int) -> int:
    return v & MASK32


def s32(v: int) -> int:
    v = int(v) & MASK32
    return v - 0x100000000 if v & 0x80000000 else v


def s8(v: int) -> int:
    v = int(v) & 0xFF
    return v - 0x100 if v & 0x80 else v


def pack_i8x4(vals) -> int:
    assert len(vals) == 4
    return (
        ((vals[0] & 0xFF) << 0)  |
        ((vals[1] & 0xFF) << 8)  |
        ((vals[2] & 0xFF) << 16) |
        ((vals[3] & 0xFF) << 24)
    )


def unpack_i8x4(word: int):
    word = int(word) & MASK32
    return [
        s8((word >> 0) & 0xFF),
        s8((word >> 8) & 0xFF),
        s8((word >> 16) & 0xFF),
        s8((word >> 24) & 0xFF),
    ]


def dot4_model(a_word: int, b_word: int, acc: int = 0) -> int:
    a = unpack_i8x4(a_word)
    b = unpack_i8x4(b_word)
    total = s32(acc)
    for i in range(4):
        total += a[i] * b[i]
    return s32(total)


def trunc_div_u32(a: int, b: int) -> int:
    # RTL OP_DIV is unsigned division because operand1/operand2 are unsigned.
    return u32(u32(a) // u32(b))


def trunc_mod_u32(a: int, b: int) -> int:
    # RTL OP_MOD is unsigned modulo because operand1/operand2 are unsigned.
    return u32(u32(a) % u32(b))


# ── DUT helpers ───────────────────────────────────────────────────────────────

async def drive_alu(dut, op, operand1=0, operand2=0, operand3=0):
    dut.operand1.value = u32(operand1)
    dut.operand2.value = u32(operand2)
    dut.operand3.value = u32(operand3)
    dut.op_select.value = op
    await Timer(1, unit="ns")


def result_u32(dut) -> int:
    return int(dut.result.value) & MASK32


def result_s32(dut) -> int:
    return s32(int(dut.result.value))


def nzp(dut) -> int:
    return int(dut.nzp_flag.value) & 0x7


def assert_result_u32(dut, expected, msg=""):
    got = result_u32(dut)
    exp = u32(expected)
    assert got == exp, f"{msg}: expected 0x{exp:08x}, got 0x{got:08x}"


def assert_result_s32(dut, expected, msg=""):
    got = result_s32(dut)
    exp = s32(expected)
    assert got == exp, f"{msg}: expected {exp}, got {got}"


def assert_nzp(dut, expected, msg=""):
    got = nzp(dut)
    exp = expected & 0x7
    assert got == exp, f"{msg}: expected NZP {exp:03b}, got {got:03b}"