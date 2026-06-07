import cocotb

from tests.common import *


@cocotb.test()
async def test_reset_outputs_idle(dut):
    await start_clock(dut)
    await reset_dut(dut)

    assert int(dut.block_done.value) == 0
    assert int(dut.prog_mem_req_valid.value) == 0
    assert int(dut.data_mem_req_valid.value) == 0


@cocotb.test()
async def test_ret_only_completes_block(dut):
    instructions = program_dict([
        instr_ret(),
    ])

    cycles, data_memory = await run_core(dut, instructions, timeout_cycles=100)

    assert cycles > 0
    assert int(dut.block_done.value) == 1


@cocotb.test()
async def test_const_add_str_per_thread(dut):
    """
    Program:
      R1 = 5
      R2 = THREAD_IDX + R1
      mem[THREAD_IDX] = R2

    Expected:
      mem[0..3] = [5, 6, 7, 8]
    """
    instructions = program_dict([
        instr_const(R1, 5),
        instr_add(R2, THREAD_IDX, R1),
        instr_str(R2, THREAD_IDX, 0),
        instr_ret(),
    ])

    cycles, data_memory = await run_core(dut, instructions, timeout_cycles=500)

    assert_mem_range(data_memory, 0, [5, 6, 7, 8], "const/add/str")


@cocotb.test()
async def test_ldr_add_str_per_thread(dut):
    """
    Program:
      R1 = mem[THREAD_IDX]
      R2 = 1
      R3 = R1 + R2
      R5 = 4
      R6 = THREAD_IDX + R5
      mem[R6] = R3

    Expected:
      input  mem[0..3] = [10, 20, 30, 40]
      output mem[4..7] = [11, 21, 31, 41]
    """
    instructions = program_dict([
        instr_ldr(R1, THREAD_IDX, 0),
        instr_const(R2, 1),
        instr_add(R3, R1, R2),
        instr_const(R5, 4),
        instr_add(R6, THREAD_IDX, R5),
        instr_str(R3, R6, 0),
        instr_ret(),
    ])

    data_memory = {
        0: 10,
        1: 20,
        2: 30,
        3: 40,
    }

    cycles, data_memory = await run_core(
        dut,
        instructions,
        data_memory=data_memory,
        timeout_cycles=1000,
    )

    assert_mem_range(data_memory, 4, [11, 21, 31, 41], "ldr/add/str")


@cocotb.test()
async def test_blockidx_blockdim_special_registers(dut):
    """
    Program:
      R1 = BLOCK_IDX + BLOCK_DIM
      mem[THREAD_IDX] = R1

    blockIdx = 2
    blockDim = 4

    Expected:
      mem[0..3] = [6, 6, 6, 6]
    """
    instructions = program_dict([
        instr_add(R1, BLOCK_IDX, BLOCK_DIM),
        instr_str(R1, THREAD_IDX, 0),
        instr_ret(),
    ])

    cycles, data_memory = await run_core(
        dut,
        instructions,
        block_idx=2,
        block_dim=4,
        timeout_cycles=500,
    )

    assert_mem_range(data_memory, 0, [6, 6, 6, 6], "blockIdx/blockDim")


@cocotb.test()
async def test_cmp_does_not_write_back_to_register(dut):
    """
    CMP must update NZP only. It must not overwrite rd.

    Program:
      R1 = 5
      R2 = 5
      CMP R1, R2
      mem[THREAD_IDX] = R1

    Expected:
      R1 remains 5, so mem[0..3] = 5
    """
    instructions = program_dict([
        instr_const(R1, 5),
        instr_const(R2, 5),
        instr_cmp(R1, R2),
        instr_str(R1, THREAD_IDX, 0),
        instr_ret(),
    ])

    cycles, data_memory = await run_core(dut, instructions, timeout_cycles=800)

    assert_mem_range(data_memory, 0, [5, 5, 5, 5], "CMP no writeback")


@cocotb.test()
async def test_store_uses_rd_field_as_value_register(dut):
    """
    STR encoding contract:
      rd field = value register
      rs1 field = address register

    Program:
      R1 = 99
      R2 = 2
      mem[R2] = R1

    All threads write same value to same address.
    Expected:
      mem[2] = 99
    """
    instructions = program_dict([
        instr_const(R1, 99),
        instr_const(R2, 2),
        instr_str(R1, R2, 0),
        instr_ret(),
    ])

    cycles, data_memory = await run_core(dut, instructions, timeout_cycles=500)

    assert_mem(data_memory, 2, 99, "STR value/address field contract")


@cocotb.test()
async def test_dot4_matvec_per_thread(dut):
    """
    Same core-level shape as Phase 17.

    R1 = mem[THREAD_IDX]       A row
    R2 = 4
    R3 = mem[4]                x
    R4 = 0
    R4 = DOT4(R4, R1, R3)
    R5 = 8
    R6 = THREAD_IDX + R5
    mem[R6] = R4
    """
    instructions = program_dict([
        instr_ldr(R1, THREAD_IDX, 0),
        instr_const(R2, 4),
        instr_ldr(R3, R2, 0),
        instr_const(R4, 0),
        instr_dot(R4, R1, R3),
        instr_const(R5, 8),
        instr_add(R6, THREAD_IDX, R5),
        instr_str(R4, R6, 0),
        instr_ret(),
    ])

    data_memory = {
        0: pack_i8x4([1, 2, 0, 0]),
        1: pack_i8x4([0, 3, 4, 0]),
        2: pack_i8x4([0, 0, 5, 6]),
        3: pack_i8x4([7, 0, 0, 8]),
        4: pack_i8x4([1, 1, 1, 1]),
    }

    cycles, data_memory = await run_core(
        dut,
        instructions,
        data_memory=data_memory,
        timeout_cycles=1500,
    )

    assert_mem_range(data_memory, 8, [3, 7, 11, 15], "DOT4 matvec")


@cocotb.test()
async def test_branch_equal_skips_instruction(dut):
    """
    Program:
      R1 = 5
      R2 = 5
      CMP R1, R2
      BRz +2          # PC 3 -> PC 5
      R3 = 111        # skipped
      R3 = 222
      mem[THREAD_IDX] = R3
      RET

    Expected:
      mem[0..3] = 222
    """
    instructions = program_dict([
        instr_const(R1, 5),                  # 0
        instr_const(R2, 5),                  # 1
        instr_cmp(R1, R2),                   # 2
        encode_branch(nzp_mask=0b010, branch_offset=2),  # 3
        instr_const(R3, 111),                # 4 skipped
        instr_const(R3, 222),                # 5 target
        instr_str(R3, THREAD_IDX, 0),        # 6
        instr_ret(),                         # 7
    ])

    cycles, data_memory = await run_core(dut, instructions, timeout_cycles=1000)

    assert_mem_range(data_memory, 0, [222, 222, 222, 222], "branch equal skip")


@cocotb.test()
async def test_branch_not_taken_falls_through(dut):
    """
    Program:
      R1 = 5
      R2 = 6
      CMP R1, R2      # negative
      BRz +2          # not taken
      R3 = 111
      mem[THREAD_IDX] = R3
      RET

    Expected:
      mem[0..3] = 111
    """
    instructions = program_dict([
        instr_const(R1, 5),                  # 0
        instr_const(R2, 6),                  # 1
        instr_cmp(R1, R2),                   # 2
        encode_branch(nzp_mask=0b010, branch_offset=2),  # 3 not taken
        instr_const(R3, 111),                # 4
        instr_str(R3, THREAD_IDX, 0),        # 5
        instr_ret(),                         # 6
    ])

    cycles, data_memory = await run_core(dut, instructions, timeout_cycles=1000)

    assert_mem_range(data_memory, 0, [111, 111, 111, 111], "branch not taken")


@cocotb.test()
async def test_back_to_back_loads_clear_lsu_done_latch(dut):
    """
    Protects the core.sv LSU done latch fix.

    Program:
      R1 = mem[THREAD_IDX]
      R2 = mem[THREAD_IDX + 4]
      R3 = R1 + R2
      R5 = 8
      R6 = THREAD_IDX + R5
      mem[R6] = R3

    Expected:
      mem[8..11] = input0 + input1
    """
    instructions = program_dict([
        instr_ldr(R1, THREAD_IDX, 0),
        instr_ldr(R2, THREAD_IDX, 4),
        instr_add(R3, R1, R2),
        instr_const(R5, 8),
        instr_add(R6, THREAD_IDX, R5),
        instr_str(R3, R6, 0),
        instr_ret(),
    ])

    data_memory = {
        0: 1,
        1: 2,
        2: 3,
        3: 4,
        4: 10,
        5: 20,
        6: 30,
        7: 40,
    }

    cycles, data_memory = await run_core(
        dut,
        instructions,
        data_memory=data_memory,
        timeout_cycles=1500,
    )

    assert_mem_range(data_memory, 8, [11, 22, 33, 44], "back-to-back LDR")