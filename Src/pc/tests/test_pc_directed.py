import cocotb
from cocotb.triggers import Timer

from tests.common import *


@cocotb.test()
async def test_reset_clears_pc_and_nzp(dut):
    await setup_dut(dut)

    assert_pc(dut, 0, "reset PC")
    assert_nzp(dut, 0, "reset NZP")


@cocotb.test()
async def test_pc_en_low_holds_pc(dut):
    await setup_dut(dut)

    dut.pc_en.value = 0
    await step(dut)
    await step(dut)
    await step(dut)

    assert_pc(dut, 0, "pc_en low hold")


@cocotb.test()
async def test_single_increment(dut):
    await setup_dut(dut)

    await increment_pc(dut, 1)

    assert_pc(dut, 1, "single increment")


@cocotb.test()
async def test_multiple_increment(dut):
    await setup_dut(dut)

    await increment_pc(dut, 5)

    assert_pc(dut, 5, "five increments")


@cocotb.test()
async def test_nzp_store_without_pc_update(dut):
    await setup_dut(dut)

    await increment_pc(dut, 1)
    await store_nzp(dut, NZP_P)

    assert_pc(dut, 1, "NZP store does not update PC")
    assert_nzp(dut, NZP_P, "NZP store positive")


@cocotb.test()
async def test_branch_taken_positive(dut):
    await setup_dut(dut)

    await increment_pc(dut, 1)
    await store_nzp(dut, NZP_P)
    await branch_cycle(dut, NZP_P, 5)

    assert_pc(dut, 6, "branch positive taken")


@cocotb.test()
async def test_branch_taken_negative(dut):
    await setup_dut(dut)

    await increment_pc(dut, 3)
    await store_nzp(dut, NZP_N)
    await branch_cycle(dut, NZP_N, 7)

    assert_pc(dut, 10, "branch negative taken")


@cocotb.test()
async def test_branch_taken_zero(dut):
    await setup_dut(dut)

    await increment_pc(dut, 4)
    await store_nzp(dut, NZP_Z)
    await branch_cycle(dut, NZP_Z, 9)

    assert_pc(dut, 13, "branch zero taken")


@cocotb.test()
async def test_branch_not_taken_increments_by_one(dut):
    await setup_dut(dut)

    await increment_pc(dut, 1)
    await store_nzp(dut, NZP_P)
    await branch_cycle(dut, NZP_N, 5)

    assert_pc(dut, 2, "branch not taken increments")


@cocotb.test()
async def test_branch_mask_all_takes_any_nzp(dut):
    await setup_dut(dut)

    await increment_pc(dut, 2)
    await store_nzp(dut, NZP_Z)
    await branch_cycle(dut, NZP_ALL, 6)

    assert_pc(dut, 8, "branch mask ALL")


@cocotb.test()
async def test_branch_mask_zero_never_takes(dut):
    await setup_dut(dut)

    await increment_pc(dut, 2)
    await store_nzp(dut, NZP_P)
    await branch_cycle(dut, 0b000, 6)

    assert_pc(dut, 3, "branch mask zero not taken")


@cocotb.test()
async def test_branch_en_low_ignores_offset(dut):
    await setup_dut(dut)

    await increment_pc(dut, 2)
    await store_nzp(dut, NZP_P)

    dut.pc_en.value = 1
    dut.branch_en.value = 0
    dut.nzp_mask.value = NZP_P
    dut.branch_offset.value = 100
    await step(dut)

    assert_pc(dut, 3, "branch_en low ignores offset")


@cocotb.test()
async def test_branch_taken_offset_zero_holds_pc(dut):
    await setup_dut(dut)

    await increment_pc(dut, 5)
    await store_nzp(dut, NZP_P)
    await branch_cycle(dut, NZP_P, 0)

    assert_pc(dut, 5, "taken branch offset zero holds PC")


@cocotb.test()
async def test_block_rst_clears_pc_and_nzp(dut):
    await setup_dut(dut)

    await increment_pc(dut, 8)
    await store_nzp(dut, NZP_P)

    await block_reset_cycle(dut)

    assert_pc(dut, 0, "block_rst clears PC")
    assert_nzp(dut, 0, "block_rst clears NZP")


@cocotb.test()
async def test_block_rst_priority_over_pc_increment(dut):
    await setup_dut(dut)

    await increment_pc(dut, 5)

    dut.block_rst.value = 1
    dut.pc_en.value = 1
    dut.branch_en.value = 0
    await step(dut)

    dut.block_rst.value = 0
    dut.pc_en.value = 0

    assert_pc(dut, 0, "block_rst priority over increment")


@cocotb.test()
async def test_block_rst_priority_over_branch_and_nzp_store(dut):
    await setup_dut(dut)

    await increment_pc(dut, 5)
    await store_nzp(dut, NZP_P)

    dut.block_rst.value = 1
    dut.pc_en.value = 1
    dut.branch_en.value = 1
    dut.branch_offset.value = 10
    dut.nzp_en.value = 1
    dut.nzp_flag.value = NZP_N
    dut.nzp_mask.value = NZP_P
    await step(dut)

    dut.block_rst.value = 0
    dut.pc_en.value = 0
    dut.branch_en.value = 0
    dut.nzp_en.value = 0

    assert_pc(dut, 0, "block_rst priority over branch")
    assert_nzp(dut, 0, "block_rst priority over NZP store")


@cocotb.test()
async def test_nzp_update_and_branch_same_cycle_uses_old_nzp(dut):
    await setup_dut(dut)

    await increment_pc(dut, 1)
    await store_nzp(dut, NZP_P)

    # Same cycle asks to update NZP to negative and branch on negative.
    # RTL uses old nzp_reg for branch decision, so branch is NOT taken.
    dut.pc_en.value = 1
    dut.branch_en.value = 1
    dut.branch_offset.value = 10
    dut.nzp_mask.value = NZP_N
    dut.nzp_en.value = 1
    dut.nzp_flag.value = NZP_N
    await step(dut)

    assert_pc(dut, 2, "same-cycle NZP update uses old NZP for branch")
    assert_nzp(dut, NZP_N, "NZP updated after same cycle")


@cocotb.test()
async def test_reset_priority_over_block_rst(dut):
    await setup_dut(dut)

    await increment_pc(dut, 5)
    await store_nzp(dut, NZP_P)

    dut.rst.value = 1
    dut.block_rst.value = 1
    dut.pc_en.value = 1
    dut.branch_en.value = 1
    dut.branch_offset.value = 10
    await step(dut)

    dut.rst.value = 0
    dut.block_rst.value = 0
    dut.pc_en.value = 0
    dut.branch_en.value = 0

    assert_pc(dut, 0, "rst priority")
    assert_nzp(dut, 0, "rst clears NZP")