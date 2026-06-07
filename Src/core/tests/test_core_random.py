import random
import cocotb

from tests.common import *


RNG_SEED = 0xC04E2026


def rand_u8_small():
    return random.randint(0, 200)


def rand_i8():
    return random.randint(-8, 8)


@cocotb.test()
async def test_random_const_add_threadidx_programs(dut):
    random.seed(RNG_SEED)

    instructions = {}
    data_memory = {}

    await setup_core(
        dut,
        instructions=instructions,
        data_memory=data_memory,
        block_idx=0,
        block_dim=4,
    )

    for i in range(20):
        await reset_dut(dut, block_idx=0, block_dim=4)

        base = random.randint(0, 1000)

        instructions.clear()
        instructions.update(program_dict([
            instr_const(R1, base),
            instr_add(R2, THREAD_IDX, R1),
            instr_str(R2, THREAD_IDX, 0),
            instr_ret(),
        ]))

        data_memory.clear()

        cycles = await run_core_loaded(dut, timeout_cycles=500)

        expected = [base + t for t in range(4)]
        assert_mem_range(data_memory, 0, expected, f"random const/add iter={i}")


@cocotb.test()
async def test_random_ldr_add_const_programs(dut):
    random.seed(RNG_SEED + 1)

    instructions = {}
    data_memory = {}

    await setup_core(
        dut,
        instructions=instructions,
        data_memory=data_memory,
        block_idx=0,
        block_dim=4,
    )

    for i in range(20):
        await reset_dut(dut, block_idx=0, block_dim=4)

        values = [rand_u8_small() for _ in range(4)]
        bias = random.randint(0, 50)

        instructions.clear()
        instructions.update(program_dict([
            instr_ldr(R1, THREAD_IDX, 0),
            instr_const(R2, bias),
            instr_add(R3, R1, R2),
            instr_const(R5, 4),
            instr_add(R6, THREAD_IDX, R5),
            instr_str(R3, R6, 0),
            instr_ret(),
        ]))

        data_memory.clear()
        data_memory.update({addr: value for addr, value in enumerate(values)})

        cycles = await run_core_loaded(dut, timeout_cycles=1000)

        expected = [v + bias for v in values]
        assert_mem_range(data_memory, 4, expected, f"random ldr/add iter={i}")


@cocotb.test()
async def test_random_dot4_matvec_programs(dut):
    random.seed(RNG_SEED + 2)

    instructions = {}
    data_memory = {}

    await setup_core(
        dut,
        instructions=instructions,
        data_memory=data_memory,
        block_idx=0,
        block_dim=4,
    )

    for i in range(20):
        await reset_dut(dut, block_idx=0, block_dim=4)

        rows = [[rand_i8() for _ in range(4)] for _ in range(4)]
        x = [rand_i8() for _ in range(4)]

        packed_rows = [pack_i8x4(row) for row in rows]
        packed_x = pack_i8x4(x)

        instructions.clear()
        instructions.update(program_dict([
            instr_ldr(R1, THREAD_IDX, 0),
            instr_const(R2, 4),
            instr_ldr(R3, R2, 0),
            instr_const(R4, 0),
            instr_dot(R4, R1, R3),
            instr_const(R5, 8),
            instr_add(R6, THREAD_IDX, R5),
            instr_str(R4, R6, 0),
            instr_ret(),
        ]))

        data_memory.clear()
        data_memory.update({
            0: packed_rows[0],
            1: packed_rows[1],
            2: packed_rows[2],
            3: packed_rows[3],
            4: packed_x,
        })

        cycles = await run_core_loaded(dut, timeout_cycles=1500)

        expected = [
            dot4_model(packed_rows[t], packed_x, 0)
            for t in range(4)
        ]

        assert_mem_range(data_memory, 8, expected, f"random dot4 matvec iter={i}")