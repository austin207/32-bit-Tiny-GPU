import cocotb

from tests.common import *


@cocotb.test()
async def test_reset_defaults(dut):
    await setup_dut(dut)

    assert_stack(
        dut,
        empty=1,
        full=0,
        overflow=0,
        top_pc=0,
        msg="reset defaults",
    )


@cocotb.test()
async def test_single_push_updates_top(dut):
    await setup_dut(dut)

    await push_entry(dut, 0xDEADBEEF)

    assert_stack(
        dut,
        empty=0,
        full=0,
        overflow=0,
        top_pc=0xDEADBEEF,
        msg="single push",
    )


@cocotb.test()
async def test_single_pop_returns_empty(dut):
    await setup_dut(dut)

    await push_entry(dut, 0xCAFEBABE)
    await pop_entry(dut)

    assert_stack(
        dut,
        empty=1,
        full=0,
        overflow=0,
        top_pc=0,
        msg="single pop",
    )


@cocotb.test()
async def test_pop_empty_does_not_underflow(dut):
    await setup_dut(dut)

    await pop_entry(dut)

    assert_stack(
        dut,
        empty=1,
        full=0,
        overflow=0,
        top_pc=0,
        msg="pop empty",
    )


@cocotb.test()
async def test_call_return_pair(dut):
    # Mirrors the actual CALL/SRET usage pattern axelcc emits: one push
    # (CALL) immediately followed by one pop (SRET). sema.c forbids nested
    # func calls, so a real compiled program never holds more than one
    # entry on this stack at a time -- this is the shape that matters most.
    await setup_dut(dut)

    call_site_return_pc = 0x00000018  # address right after a CALL instruction

    await push_entry(dut, call_site_return_pc)
    assert_stack(dut, empty=0, top_pc=call_site_return_pc, msg="after CALL")

    await pop_entry(dut)
    assert_stack(dut, empty=1, top_pc=0, msg="after SRET")


@cocotb.test()
async def test_lifo_order_two_entries(dut):
    await setup_dut(dut)

    await push_entry(dut, 0x1000)
    await push_entry(dut, 0x2000)

    assert_stack(
        dut,
        empty=0,
        full=1,
        top_pc=0x2000,
        msg="two push top (fills default depth-2 stack)",
    )

    await pop_entry(dut)

    assert_stack(
        dut,
        empty=0,
        full=0,
        top_pc=0x1000,
        msg="after pop returns previous top",
    )

    await pop_entry(dut)

    assert_stack(
        dut,
        empty=1,
        full=0,
        top_pc=0,
        msg="after second pop",
    )


@cocotb.test()
async def test_full_after_depth_pushes(dut):
    await setup_dut(dut)

    for idx in range(STACK_DEPTH):
        await push_entry(dut, 0x1000 + idx)

    assert_stack(
        dut,
        empty=0,
        full=1,
        overflow=0,
        top_pc=0x1000 + STACK_DEPTH - 1,
        msg="full after depth pushes",
    )


@cocotb.test()
async def test_overflow_combinational_when_push_full(dut):
    await setup_dut(dut)

    for idx in range(STACK_DEPTH):
        await push_entry(dut, 0x1000 + idx)

    await check_overflow_combinational(dut, pc=0xDEAD)

    # Keep push high across clock. RTL must not write new entry when full.
    await step(dut)
    dut.push.value = 0
    await Timer(1, unit="ns")

    assert_stack(
        dut,
        empty=0,
        full=1,
        overflow=0,
        top_pc=0x1000 + STACK_DEPTH - 1,
        msg="overflow push ignored",
    )


@cocotb.test()
async def test_overflow_clears_when_push_deasserted(dut):
    await setup_dut(dut)

    for idx in range(STACK_DEPTH):
        await push_entry(dut, 0x2000 + idx)

    await check_overflow_combinational(dut, pc=0xBEEF)

    dut.push.value = 0
    await Timer(1, unit="ns")

    assert_stack(
        dut,
        full=1,
        overflow=0,
        top_pc=0x2000 + STACK_DEPTH - 1,
        msg="overflow clears",
    )


@cocotb.test()
async def test_reset_after_pushes_clears_stack_pointer(dut):
    await setup_dut(dut)

    await push_entry(dut, 0xAAAA0001)

    dut.rst.value = 1
    await step(dut)
    dut.rst.value = 0
    await Timer(1, unit="ns")

    assert_stack(
        dut,
        empty=1,
        full=0,
        overflow=0,
        top_pc=0,
        msg="reset after pushes",
    )


@cocotb.test()
async def test_push_after_empty_pop_works(dut):
    await setup_dut(dut)

    await pop_entry(dut)
    await push_entry(dut, 0x12345678)

    assert_stack(
        dut,
        empty=0,
        full=0,
        top_pc=0x12345678,
        msg="push after empty pop",
    )


# ── Simultaneous push+pop characterization ──────────────────────────────────
# axelcc never actually asserts call_en and sret_en together (decoder.sv's
# case statement is one-hot per opcode), so this shape is unreachable from
# real compiled programs. It's still exercised here as a standalone-module
# robustness check, since a silent "both asserted" bug would otherwise be
# invisible until some future RTL change accidentally created the condition.


@cocotb.test()
async def test_simultaneous_push_pop_when_partial_pop_wins(dut):
    await setup_dut(dut)

    await push_entry(dut, 0x1000)
    assert_stack(dut, empty=0, full=0, top_pc=0x1000, msg="one entry before")

    await push_and_pop_entry(dut, 0x9999)

    assert_stack(
        dut,
        empty=1,
        full=0,
        overflow=0,
        top_pc=0,
        msg="simultaneous push+pop on partial stack: pop wins",
    )


@cocotb.test()
async def test_simultaneous_push_pop_when_full_pop_wins(dut):
    await setup_dut(dut)

    await push_entry(dut, 0x1000)
    await push_entry(dut, 0x2000)
    assert_stack(dut, full=1, top_pc=0x2000, msg="full before")

    await push_and_pop_entry(dut, 0x9999)

    assert_stack(
        dut,
        empty=0,
        full=0,
        overflow=0,
        top_pc=0x1000,
        msg="simultaneous push+pop on full stack: pop wins, no overflow",
    )


@cocotb.test()
async def test_simultaneous_push_pop_when_empty_push_wins(dut):
    await setup_dut(dut)

    await push_and_pop_entry(dut, 0x55AA55AA)

    assert_stack(
        dut,
        empty=0,
        full=0,
        overflow=0,
        top_pc=0x55AA55AA,
        msg="simultaneous push+pop on empty stack: pop illegal, push wins",
    )


@cocotb.test()
async def test_orphaned_write_not_observable_after_simultaneous_pop(dut):
    # The "pop wins" case still lets push's stack_mem write land (at the
    # pre-edge sp index) even though sp itself shrinks -- that write is
    # provably unreachable because sp only grows by writing-before-reading
    # each index it advances to. Prove it end to end: drive the orphaned
    # write, then fill and drain normally and confirm the poison value
    # never surfaces.
    await setup_dut(dut)

    await push_entry(dut, 0x1000)
    await push_and_pop_entry(dut, 0xBAD0BAD0)
    assert_stack(dut, empty=1, top_pc=0, msg="after orphaning write")

    await push_entry(dut, 0x3000)
    assert_stack(dut, empty=0, full=0, top_pc=0x3000, msg="fresh push after orphan")

    await push_entry(dut, 0x4000)
    assert_stack(dut, full=1, top_pc=0x4000, msg="fill to full after orphan")

    await pop_entry(dut)
    assert_stack(dut, top_pc=0x3000, msg="drain 1: no poison")

    await pop_entry(dut)
    assert_stack(dut, empty=1, top_pc=0, msg="drain 2: no poison")


@cocotb.test()
async def test_overflow_deasserts_immediately_when_pop_makes_room_while_push_held(dut):
    await setup_dut(dut)

    await push_entry(dut, 0x1000)
    await push_entry(dut, 0x2000)
    assert_stack(dut, full=1, msg="full before")

    # Hold push high (new candidate pc) and pulse pop on the same edge.
    dut.push.value = 1
    dut.pop.value = 1
    dut.push_return_pc.value = u32(0x9999)
    await step(dut)

    # Deassert only pop -- push is still driven high from before this edge,
    # so if overflow were latched (rather than purely combinational on the
    # now-updated stack_full) it would still read 1 here.
    dut.pop.value = 0
    await Timer(1, unit="ns")

    assert_stack(
        dut,
        full=0,
        overflow=0,
        top_pc=0x1000,
        msg="overflow clears immediately once pop makes room, even with push still held",
    )

    dut.push.value = 0
    await Timer(1, unit="ns")


@cocotb.test()
async def test_push_return_pc_glitch_does_not_affect_stored_entry(dut):
    # push_return_pc is only sampled while push=1. Toggling it while push=0
    # must never leak into the stored/visible top entry (i.e. no
    # accidental combinational or level-sensitive read path).
    await setup_dut(dut)

    await push_entry(dut, 0xAAAA0000)
    assert_stack(dut, top_pc=0xAAAA0000, msg="initial push")

    for i in range(3):
        dut.push_return_pc.value = u32(0xFFFFFFFF - i)
        await step(dut)
        assert_stack(
            dut,
            empty=0,
            top_pc=0xAAAA0000,
            msg=f"push_return_pc glitch iter={i} does not affect stored entry",
        )


@cocotb.test()
async def test_async_reset_without_clock_edge(dut):
    # call_stack.sv's always_ff is sensitive to `posedge clk or posedge
    # rst` -- rst is asynchronous, so it must take effect without waiting
    # for a clock edge. Every other reset test in this suite happens to
    # also cross a RisingEdge(clk), which would mask a bug where rst was
    # accidentally made synchronous-only.
    await setup_dut(dut)

    await push_entry(dut, 0xDEAD0000)
    assert_stack(dut, empty=0, top_pc=0xDEAD0000, msg="before async reset")

    dut.rst.value = 1
    await Timer(1, unit="ns")  # no RisingEdge(dut.clk) here on purpose

    assert_stack(
        dut,
        empty=1,
        full=0,
        overflow=0,
        top_pc=0,
        msg="async reset takes effect without a clock edge",
    )

    dut.rst.value = 0
    await Timer(1, unit="ns")


@cocotb.test()
async def test_full_boundary_repeated_blocked_pushes_preserve_top(dut):
    await setup_dut(dut)

    await push_entry(dut, 0x1000)
    await push_entry(dut, 0x2000)
    assert_stack(dut, full=1, top_pc=0x2000, msg="full before")

    dut.push.value = 1
    dut.pop.value = 0
    for i in range(5):
        dut.push_return_pc.value = u32(0xBADC0DE0 + i)
        await step(dut)
        assert_stack(
            dut,
            full=1,
            overflow=1,
            top_pc=0x2000,
            msg=f"repeated blocked push iter={i} preserves top and mem",
        )

    dut.push.value = 0
    await Timer(1, unit="ns")

    assert_stack(
        dut,
        full=1,
        overflow=0,
        top_pc=0x2000,
        msg="top still intact after releasing push",
    )


@cocotb.test()
async def test_reset_dominates_simultaneous_push_pop(dut):
    await setup_dut(dut)

    await push_entry(dut, 0x1000)
    assert_stack(dut, empty=0, top_pc=0x1000, msg="one entry before")

    dut.push.value = 1
    dut.pop.value = 1
    dut.rst.value = 1
    dut.push_return_pc.value = u32(0x1234)
    await step(dut)

    dut.push.value = 0
    dut.pop.value = 0
    dut.rst.value = 0
    await Timer(1, unit="ns")

    assert_stack(
        dut,
        empty=1,
        full=0,
        overflow=0,
        top_pc=0,
        msg="reset dominates even with push+pop asserted on the same edge",
    )
