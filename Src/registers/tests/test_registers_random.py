import random
import cocotb

from tests.common import *


RNG_SEED = 0x517E1234

def rand_u32():
    return random.getrandbits(32)


@cocotb.test()
async def test_random_general_register_write_read_port1(dut):
    random.seed(RNG_SEED)
    await setup_dut(dut)

    mirror = {addr: 0 for addr in range(1, 29)}

    for i in range(300):
        addr = random.randint(1, 28)
        data = rand_u32()

        await write_reg(dut, addr, data)
        mirror[addr] = u32(data)

        got = await read_port1(dut, addr)
        assert_u32(got, mirror[addr], f"random write/read port1 iter={i} R{addr}")


@cocotb.test()
async def test_random_general_register_three_ports(dut):
    random.seed(RNG_SEED + 1)
    await setup_dut(dut)

    mirror = {addr: 0 for addr in range(1, 29)}

    for addr in range(1, 29):
        data = rand_u32()
        await write_reg(dut, addr, data)
        mirror[addr] = u32(data)

    for i in range(200):
        a1 = random.randint(1, 28)
        a2 = random.randint(1, 28)
        a3 = random.randint(1, 28)

        got1, got2, got3 = await read_all_ports(dut, a1, a2, a3)

        assert_u32(got1, mirror[a1], f"random port1 iter={i} R{a1}")
        assert_u32(got2, mirror[a2], f"random port2 iter={i} R{a2}")
        assert_u32(got3, mirror[a3], f"random port3 iter={i} R{a3}")


@cocotb.test()
async def test_random_write_enable_disabled(dut):
    random.seed(RNG_SEED + 2)
    await setup_dut(dut)

    mirror = {addr: 0 for addr in range(1, 29)}

    for i in range(100):
        addr = random.randint(1, 28)
        data = rand_u32()

        await write_reg_disabled(dut, addr, data)

        got = await read_port1(dut, addr)
        assert_u32(got, mirror[addr], f"disabled random write ignored iter={i} R{addr}")


@cocotb.test()
async def test_random_special_register_values(dut):
    random.seed(RNG_SEED + 3)
    await setup_dut(dut)

    for i in range(100):
        thread_idx = rand_u32()
        block_idx = rand_u32()
        block_dim = random.randint(2, 1024)

        set_special_inputs(dut, thread_idx=thread_idx, block_idx=block_idx, block_dim=block_dim)

        got1, got2, got3 = await read_all_ports(dut, THREAD_IDX, BLOCK_IDX, BLOCK_DIM)

        assert_u32(got1, thread_idx, f"random R29 normal mode iter={i}")
        assert_u32(got2, block_idx, f"random R30 iter={i}")
        assert_u32(got3, block_dim, f"random R31 iter={i}")


@cocotb.test()
async def test_random_r29_single_thread_mode(dut):
    random.seed(RNG_SEED + 4)
    await setup_dut(dut)

    for i in range(100):
        thread_idx = rand_u32()
        block_idx = rand_u32()

        set_special_inputs(dut, thread_idx=thread_idx, block_idx=block_idx, block_dim=1)

        got = await read_port1(dut, THREAD_IDX)
        assert_u32(got, block_idx, f"random R29 blockDim=1 iter={i}")


@cocotb.test()
async def test_random_writes_to_r0_and_specials_ignored(dut):
    random.seed(RNG_SEED + 5)
    await setup_dut(dut)

    set_special_inputs(dut, thread_idx=11, block_idx=22, block_dim=4)

    protected = [R0, THREAD_IDX, BLOCK_IDX, BLOCK_DIM]

    for i in range(100):
        addr = random.choice(protected)
        data = rand_u32()

        await write_reg(dut, addr, data)

        got0 = await read_port1(dut, R0)
        got29 = await read_port1(dut, THREAD_IDX)
        got30 = await read_port1(dut, BLOCK_IDX)
        got31 = await read_port1(dut, BLOCK_DIM)

        assert_u32(got0, 0, f"random protected R0 iter={i}")
        assert_u32(got29, 11, f"random protected R29 iter={i}")
        assert_u32(got30, 22, f"random protected R30 iter={i}")
        assert_u32(got31, 4, f"random protected R31 iter={i}")


@cocotb.test()
async def test_random_reset_after_many_writes(dut):
    random.seed(RNG_SEED + 6)
    await setup_dut(dut)

    for _ in range(200):
        await write_reg(dut, random.randint(1, 28), rand_u32())

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    for addr in range(1, 29):
        got = await read_port1(dut, addr)
        assert_u32(got, 0, f"random reset clears R{addr}")