import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


STACK_DEPTH = 4
THREADS_PER_CORE = 4
MASK32 = 0xFFFFFFFF
MASK_THREADS = (1 << THREADS_PER_CORE) - 1


def u32(v: int) -> int:
    return int(v) & MASK32


def mask4(v: int) -> int:
    return int(v) & MASK_THREADS


def bit(signal) -> int:
    return int(signal.value) & 1


def val32(signal) -> int:
    return int(signal.value) & MASK32


def val_mask(signal) -> int:
    return int(signal.value) & MASK_THREADS


async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())


def init_inputs(dut):
    dut.rst.value = 0
    dut.push.value = 0
    dut.pop.value = 0
    dut.push_sync_pc.value = 0
    dut.push_saved_mask.value = 0


async def step(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def reset_dut(dut):
    init_inputs(dut)

    dut.rst.value = 1
    await step(dut)
    await step(dut)

    dut.rst.value = 0
    await Timer(1, unit="ns")

    assert_stack(
        dut,
        empty=1,
        full=0,
        overflow=0,
        top_pc=0,
        top_mask=MASK_THREADS,
        msg="reset",
    )


async def setup_dut(dut):
    await start_clock(dut)
    await reset_dut(dut)


async def push_entry(dut, pc, saved_mask):
    dut.push.value = 1
    dut.pop.value = 0
    dut.push_sync_pc.value = u32(pc)
    dut.push_saved_mask.value = mask4(saved_mask)
    await step(dut)

    dut.push.value = 0
    await Timer(1, unit="ns")


async def pop_entry(dut):
    dut.push.value = 0
    dut.pop.value = 1
    await step(dut)

    dut.pop.value = 0
    await Timer(1, unit="ns")


async def check_overflow_combinational(dut, pc=0xDEAD, saved_mask=0xF):
    dut.push.value = 1
    dut.pop.value = 0
    dut.push_sync_pc.value = u32(pc)
    dut.push_saved_mask.value = mask4(saved_mask)
    await Timer(1, unit="ns")

    assert_stack(
        dut,
        overflow=1,
        msg="overflow combinational",
    )


def assert_stack(
    dut,
    empty=None,
    full=None,
    overflow=None,
    top_pc=None,
    top_mask=None,
    msg="",
):
    if empty is not None:
        got = bit(dut.stack_empty)
        exp = empty & 1
        assert got == exp, f"{msg}: stack_empty expected {exp}, got {got}"

    if full is not None:
        got = bit(dut.stack_full)
        exp = full & 1
        assert got == exp, f"{msg}: stack_full expected {exp}, got {got}"

    if overflow is not None:
        got = bit(dut.stack_overflow)
        exp = overflow & 1
        assert got == exp, f"{msg}: stack_overflow expected {exp}, got {got}"

    if top_pc is not None:
        got = val32(dut.top_sync_pc)
        exp = u32(top_pc)
        assert got == exp, (
            f"{msg}: top_sync_pc expected 0x{exp:08x}, got 0x{got:08x}"
        )

    if top_mask is not None:
        got = val_mask(dut.top_saved_mask)
        exp = mask4(top_mask)
        assert got == exp, (
            f"{msg}: top_saved_mask expected 0b{exp:04b}, got 0b{got:04b}"
        )


def expected_empty(stack):
    return 1 if len(stack) == 0 else 0


def expected_full(stack):
    return 1 if len(stack) == STACK_DEPTH else 0


def expected_top_pc(stack):
    return 0 if len(stack) == 0 else stack[-1][0]


def expected_top_mask(stack):
    return MASK_THREADS if len(stack) == 0 else stack[-1][1]


def assert_against_model(dut, stack, msg=""):
    assert_stack(
        dut,
        empty=expected_empty(stack),
        full=expected_full(stack),
        overflow=0,
        top_pc=expected_top_pc(stack),
        top_mask=expected_top_mask(stack),
        msg=msg,
    )