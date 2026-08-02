import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


STACK_DEPTH = 2
MASK32 = 0xFFFFFFFF


def u32(v: int) -> int:
    return int(v) & MASK32


def bit(signal) -> int:
    return int(signal.value) & 1


def val32(signal) -> int:
    return int(signal.value) & MASK32


async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())


def init_inputs(dut):
    dut.rst.value = 0
    dut.push.value = 0
    dut.pop.value = 0
    dut.push_return_pc.value = 0


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
        msg="reset",
    )


async def setup_dut(dut):
    await start_clock(dut)
    await reset_dut(dut)


async def push_entry(dut, pc):
    dut.push.value = 1
    dut.pop.value = 0
    dut.push_return_pc.value = u32(pc)
    await step(dut)

    dut.push.value = 0
    await Timer(1, unit="ns")


async def pop_entry(dut):
    dut.push.value = 0
    dut.pop.value = 1
    await step(dut)

    dut.pop.value = 0
    await Timer(1, unit="ns")


async def push_and_pop_entry(dut, pc):
    """
    Assert push and pop in the same cycle. Characterizes call_stack.sv's
    actual simultaneous push+pop RTL behavior: inside the always_ff block,
    pop's `sp <= sp - 1` is the second non-blocking assignment to `sp` in
    program order, so it is the one that lands whenever pop is legal
    (stack not empty) -- push's `stack_mem` write still happens, but
    becomes unreachable the moment `sp` shrinks below it, so it is never
    observable. Net rule: pop wins whenever pop is legal; push only takes
    effect when pop was illegal (stack was empty). See model_step().
    """
    dut.push.value = 1
    dut.pop.value = 1
    dut.push_return_pc.value = u32(pc)
    await step(dut)

    dut.push.value = 0
    dut.pop.value = 0
    await Timer(1, unit="ns")


def model_step(stack, push, pop, push_pc, depth=STACK_DEPTH):
    """
    Reference model for call_stack.sv's real simultaneous push+pop
    semantics (see push_and_pop_entry's docstring): pop takes priority
    whenever legal; push only takes effect when pop was illegal or not
    asserted. Mutates `stack` (a Python list, index -1 is top) in place.
    """
    if pop and len(stack) > 0:
        stack.pop()
    elif push and len(stack) < depth:
        stack.append(u32(push_pc))


async def check_overflow_combinational(dut, pc=0xDEAD):
    dut.push.value = 1
    dut.pop.value = 0
    dut.push_return_pc.value = u32(pc)
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
        got = val32(dut.top_return_pc)
        exp = u32(top_pc)
        assert got == exp, (
            f"{msg}: top_return_pc expected 0x{exp:08x}, got 0x{got:08x}"
        )


def expected_empty(stack):
    return 1 if len(stack) == 0 else 0


def expected_full(stack):
    return 1 if len(stack) == STACK_DEPTH else 0


def expected_top_pc(stack):
    return 0 if len(stack) == 0 else stack[-1]


def assert_against_model(dut, stack, msg=""):
    assert_stack(
        dut,
        empty=expected_empty(stack),
        full=expected_full(stack),
        overflow=0,
        top_pc=expected_top_pc(stack),
        msg=msg,
    )
