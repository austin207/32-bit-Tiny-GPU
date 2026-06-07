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
        top_mask=0b1111,
        msg="reset defaults",
    )


@cocotb.test()
async def test_single_push_updates_top(dut):
    await setup_dut(dut)

    await push_entry(dut, 0xDEADBEEF, 0b0101)

    assert_stack(
        dut,
        empty=0,
        full=0,
        overflow=0,
        top_pc=0xDEADBEEF,
        top_mask=0b0101,
        msg="single push",
    )


@cocotb.test()
async def test_single_pop_returns_empty(dut):
    await setup_dut(dut)

    await push_entry(dut, 0xCAFEBABE, 0b1010)
    await pop_entry(dut)

    assert_stack(
        dut,
        empty=1,
        full=0,
        overflow=0,
        top_pc=0,
        top_mask=0b1111,
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
        top_mask=0b1111,
        msg="pop empty",
    )


@cocotb.test()
async def test_lifo_order_two_entries(dut):
    await setup_dut(dut)

    await push_entry(dut, 0x1000, 0b0001)
    await push_entry(dut, 0x2000, 0b0010)

    assert_stack(
        dut,
        empty=0,
        full=0,
        top_pc=0x2000,
        top_mask=0b0010,
        msg="two push top",
    )

    await pop_entry(dut)

    assert_stack(
        dut,
        empty=0,
        full=0,
        top_pc=0x1000,
        top_mask=0b0001,
        msg="after pop returns previous top",
    )


@cocotb.test()
async def test_lifo_order_four_entries(dut):
    await setup_dut(dut)

    entries = [
        (0x1000, 0b0001),
        (0x2000, 0b0010),
        (0x3000, 0b0100),
        (0x4000, 0b1000),
    ]

    for pc, saved_mask in entries:
        await push_entry(dut, pc, saved_mask)

    assert_stack(
        dut,
        empty=0,
        full=1,
        top_pc=0x4000,
        top_mask=0b1000,
        msg="four entries full top",
    )

    for pc, saved_mask in reversed(entries[:-1]):
        await pop_entry(dut)
        assert_stack(
            dut,
            empty=0,
            top_pc=pc,
            top_mask=saved_mask,
            msg=f"LIFO after pop pc=0x{pc:08x}",
        )

    await pop_entry(dut)

    assert_stack(
        dut,
        empty=1,
        full=0,
        top_pc=0,
        top_mask=0b1111,
        msg="all popped",
    )


@cocotb.test()
async def test_full_after_four_pushes(dut):
    await setup_dut(dut)

    for idx in range(STACK_DEPTH):
        await push_entry(dut, 0x1000 + idx, idx)

    assert_stack(
        dut,
        empty=0,
        full=1,
        overflow=0,
        top_pc=0x1003,
        top_mask=0b0011,
        msg="full after four pushes",
    )


@cocotb.test()
async def test_overflow_combinational_when_push_full(dut):
    await setup_dut(dut)

    for idx in range(STACK_DEPTH):
        await push_entry(dut, 0x1000 + idx, idx)

    await check_overflow_combinational(dut, pc=0xDEAD, saved_mask=0b1111)

    # Keep push high across clock. RTL must not write new entry when full.
    await step(dut)
    dut.push.value = 0
    await Timer(1, unit="ns")

    assert_stack(
        dut,
        empty=0,
        full=1,
        overflow=0,
        top_pc=0x1003,
        top_mask=0b0011,
        msg="overflow push ignored",
    )


@cocotb.test()
async def test_overflow_clears_when_push_deasserted(dut):
    await setup_dut(dut)

    for idx in range(STACK_DEPTH):
        await push_entry(dut, 0x2000 + idx, idx)

    await check_overflow_combinational(dut, pc=0xBEEF, saved_mask=0b1111)

    dut.push.value = 0
    await Timer(1, unit="ns")

    assert_stack(
        dut,
        full=1,
        overflow=0,
        top_pc=0x2003,
        top_mask=0b0011,
        msg="overflow clears",
    )


@cocotb.test()
async def test_reset_after_pushes_clears_stack_pointer(dut):
    await setup_dut(dut)

    await push_entry(dut, 0xAAAA0001, 0b0001)
    await push_entry(dut, 0xBBBB0002, 0b0010)

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
        top_mask=0b1111,
        msg="reset after pushes",
    )


@cocotb.test()
async def test_push_after_empty_pop_works(dut):
    await setup_dut(dut)

    await pop_entry(dut)
    await push_entry(dut, 0x12345678, 0b1100)

    assert_stack(
        dut,
        empty=0,
        full=0,
        top_pc=0x12345678,
        top_mask=0b1100,
        msg="push after empty pop",
    )


@cocotb.test()
async def test_masks_all_patterns(dut):
    await setup_dut(dut)

    for saved_mask in range(16):
        await push_entry(dut, 0x5000 + saved_mask, saved_mask)

        assert_stack(
            dut,
            top_pc=0x5000 + saved_mask,
            top_mask=saved_mask,
            msg=f"mask pattern {saved_mask:04b}",
        )

        await pop_entry(dut)