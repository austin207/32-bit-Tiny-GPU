import random
import cocotb

from tests.common import *


RNG_SEED = 0x15A15A


def rand_u32():
    return random.getrandbits(32)


@cocotb.test()
async def test_random_reads_with_random_waits(dut):
    random.seed(RNG_SEED)
    await setup_dut(dut)

    for i in range(100):
        addr = rand_u32()
        data = rand_u32()
        waits = random.randint(0, 5)

        await issue_read(dut, addr=addr)
        await wait_no_response(dut, cycles=waits)
        await complete_read_response(dut, data=data)

        assert_lsu_outputs(
            dut,
            done=1,
            mem_read_data=data,
            read_write_switch=1,
            msg=f"random read iter={i}",
        )

        await step(dut)


@cocotb.test()
async def test_random_writes_with_random_waits(dut):
    random.seed(RNG_SEED + 1)
    await setup_dut(dut)

    for i in range(100):
        addr = rand_u32()
        data = rand_u32()
        waits = random.randint(0, 5)

        await issue_write(dut, addr=addr, data=data)
        await wait_no_response(dut, cycles=waits)
        await complete_write_response(dut)

        assert_lsu_outputs(
            dut,
            done=1,
            write_data=data,
            read_write_switch=0,
            msg=f"random write iter={i}",
        )

        await step(dut)


@cocotb.test()
async def test_random_mixed_reads_and_writes(dut):
    random.seed(RNG_SEED + 2)
    await setup_dut(dut)

    for i in range(200):
        op = random.choice(["read", "write"])
        addr = rand_u32()
        data = rand_u32()
        waits = random.randint(0, 3)

        if op == "read":
            await issue_read(dut, addr=addr)
            await wait_no_response(dut, cycles=waits)
            await complete_read_response(dut, data=data)

            assert_lsu_outputs(
                dut,
                done=1,
                mem_read_data=data,
                read_write_switch=1,
                msg=f"random mixed read iter={i}",
            )

        else:
            await issue_write(dut, addr=addr, data=data)
            await wait_no_response(dut, cycles=waits)
            await complete_write_response(dut)

            assert_lsu_outputs(
                dut,
                done=1,
                write_data=data,
                read_write_switch=0,
                msg=f"random mixed write iter={i}",
            )

        await step(dut)


@cocotb.test()
async def test_random_idle_noise_ignored(dut):
    random.seed(RNG_SEED + 3)
    await setup_dut(dut)

    for i in range(100):
        dut.core_en.value = 0
        dut.mem_read_en.value = random.randint(0, 1)
        dut.mem_write_en.value = random.randint(0, 1)
        dut.mem_data_address.value = rand_u32()
        dut.mem_write_data.value = rand_u32()
        dut.resp_valid.value = random.randint(0, 1)
        dut.resp_data.value = rand_u32()

        await step(dut)

        assert_lsu_outputs(
            dut,
            req_valid=0,
            done=0,
            req_addr=0,
            mem_read_data=0,
            msg=f"random idle noise iter={i}",
        )


@cocotb.test()
async def test_random_reset_during_pending_ops(dut):
    random.seed(RNG_SEED + 4)
    await setup_dut(dut)

    for i in range(50):
        op = random.choice(["read", "write"])
        addr = rand_u32()
        data = rand_u32()

        if op == "read":
            await issue_read(dut, addr=addr)
        else:
            await issue_write(dut, addr=addr, data=data)

        await wait_no_response(dut, cycles=random.randint(0, 3))

        dut.rst.value = 1
        await step(dut)

        assert_lsu_outputs(
            dut,
            req_valid=0,
            done=0,
            req_addr=0,
            mem_read_data=0,
            msg=f"random reset pending iter={i}",
        )

        dut.rst.value = 0
        await step(dut)


@cocotb.test()
async def test_random_read_priority_when_both_read_and_write_high(dut):
    random.seed(RNG_SEED + 5)
    await setup_dut(dut)

    for i in range(100):
        addr = rand_u32()
        write_data = rand_u32()
        read_data = rand_u32()

        dut.core_en.value = 1
        dut.mem_read_en.value = 1
        dut.mem_write_en.value = 1
        dut.mem_data_address.value = addr
        dut.mem_write_data.value = write_data
        dut.resp_valid.value = 0
        await step(dut)

        assert_lsu_outputs(
            dut,
            req_valid=1,
            req_addr=addr,
            done=0,
            read_write_switch=1,
            msg=f"random read priority request iter={i}",
        )

        deassert_controls(dut)

        await complete_read_response(dut, data=read_data)

        assert_lsu_outputs(
            dut,
            done=1,
            mem_read_data=read_data,
            read_write_switch=1,
            msg=f"random read priority response iter={i}",
        )

        await step(dut)