import cocotb
from cocotb.triggers import Timer

from tests.common import *


@cocotb.test()
async def test_reset_clears_general_registers(dut):
    await setup_dut(dut)

    for addr in range(1, 29):
        got = await read_port1(dut, addr)
        assert_u32(got, 0, f"reset R{addr}")


@cocotb.test()
async def test_write_and_read_single_register(dut):
    await setup_dut(dut)

    await write_reg(dut, 5, 42)
    got = await read_port1(dut, 5)
    assert_u32(got, 42, "R5 write/read")


@cocotb.test()
async def test_write_and_read_all_general_registers(dut):
    await setup_dut(dut)

    for addr in range(1, 29):
        await write_reg(dut, addr, addr * 0x11111111)

    for addr in range(1, 29):
        got = await read_port1(dut, addr)
        assert_u32(got, addr * 0x11111111, f"R{addr} all-reg sweep")


@cocotb.test()
async def test_r0_is_hardwired_zero(dut):
    await setup_dut(dut)

    await write_reg(dut, 0, 0xDEADBEEF)

    got1, got2, got3 = await read_all_ports(dut, 0, 0, 0)
    assert_u32(got1, 0, "R0 port1")
    assert_u32(got2, 0, "R0 port2")
    assert_u32(got3, 0, "R0 port3")


@cocotb.test()
async def test_write_enable_disabled_does_not_write(dut):
    await setup_dut(dut)

    await write_reg_disabled(dut, 6, 1234)
    got = await read_port1(dut, 6)
    assert_u32(got, 0, "w_en disabled write ignored")


@cocotb.test()
async def test_overwrite_register(dut):
    await setup_dut(dut)

    await write_reg(dut, 7, 111)
    await write_reg(dut, 7, 222)

    got = await read_port1(dut, 7)
    assert_u32(got, 222, "overwrite R7")


@cocotb.test()
async def test_three_read_ports_independent(dut):
    await setup_dut(dut)

    await write_reg(dut, 1, 0xAAAA0001)
    await write_reg(dut, 2, 0xBBBB0002)
    await write_reg(dut, 3, 0xCCCC0003)

    got1, got2, got3 = await read_all_ports(dut, 1, 2, 3)

    assert_u32(got1, 0xAAAA0001, "read port1 R1")
    assert_u32(got2, 0xBBBB0002, "read port2 R2")
    assert_u32(got3, 0xCCCC0003, "read port3 R3")


@cocotb.test()
async def test_same_register_on_all_read_ports(dut):
    await setup_dut(dut)

    await write_reg(dut, 12, 0x12345678)

    got1, got2, got3 = await read_all_ports(dut, 12, 12, 12)

    assert_u32(got1, 0x12345678, "same reg port1")
    assert_u32(got2, 0x12345678, "same reg port2")
    assert_u32(got3, 0x12345678, "same reg port3")


@cocotb.test()
async def test_special_registers_normal_simt_mode(dut):
    await setup_dut(dut)

    set_special_inputs(dut, thread_idx=7, block_idx=2, block_dim=4)

    got1, got2, got3 = await read_all_ports(dut, THREAD_IDX, BLOCK_IDX, BLOCK_DIM)

    assert_u32(got1, 7, "R29 THREAD_IDX normal mode")
    assert_u32(got2, 2, "R30 BLOCK_IDX")
    assert_u32(got3, 4, "R31 BLOCK_DIM")


@cocotb.test()
async def test_r29_single_thread_fpga_mode_uses_blockidx(dut):
    await setup_dut(dut)

    set_special_inputs(dut, thread_idx=99, block_idx=3, block_dim=1)

    got = await read_port1(dut, THREAD_IDX)

    assert_u32(got, 3, "R29 uses blockIdx when blockDim == 1")


@cocotb.test()
async def test_r29_normal_mode_uses_threadidx_when_blockdim_gt_1(dut):
    await setup_dut(dut)

    set_special_inputs(dut, thread_idx=11, block_idx=3, block_dim=4)

    got = await read_port1(dut, THREAD_IDX)

    assert_u32(got, 11, "R29 uses threadIdx when blockDim > 1")


@cocotb.test()
async def test_writes_to_special_registers_are_ignored(dut):
    await setup_dut(dut)

    set_special_inputs(dut, thread_idx=5, block_idx=6, block_dim=7)

    await write_reg(dut, THREAD_IDX, 0xAAAAAAAA)
    await write_reg(dut, BLOCK_IDX, 0xBBBBBBBB)
    await write_reg(dut, BLOCK_DIM, 0xCCCCCCCC)

    got1, got2, got3 = await read_all_ports(dut, THREAD_IDX, BLOCK_IDX, BLOCK_DIM)

    assert_u32(got1, 5, "write ignored R29")
    assert_u32(got2, 6, "write ignored R30")
    assert_u32(got3, 7, "write ignored R31")


@cocotb.test()
async def test_reset_after_writes_clears_general_registers(dut):
    await setup_dut(dut)

    await write_reg(dut, 10, 0xCAFEBABE)
    await write_reg(dut, 20, 0x12345678)

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    got10 = await read_port1(dut, 10)
    got20 = await read_port2(dut, 20)

    assert_u32(got10, 0, "reset clears R10")
    assert_u32(got20, 0, "reset clears R20")


@cocotb.test()
async def test_combinational_read_address_change(dut):
    await setup_dut(dut)

    await write_reg(dut, 4, 0x44444444)
    await write_reg(dut, 5, 0x55555555)

    dut.r_addr1.value = 4
    await Timer(1, unit="ns")
    assert_u32(dut.r_data1.value, 0x44444444, "comb read R4")

    dut.r_addr1.value = 5
    await Timer(1, unit="ns")
    assert_u32(dut.r_data1.value, 0x55555555, "comb read R5")