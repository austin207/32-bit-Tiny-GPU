import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


# State encodings from scheduler.sv
IDLE     = 0b0000
FETCH    = 0b0001
DECODE   = 0b0010
REQUEST  = 0b0011
WAIT     = 0b0100
EXECUTE  = 0b0101
UPDATE   = 0b0110
DIVERGE  = 0b0111
SYNC_POP = 0b1000

ALL_THREADS = 0b1111


def state(dut) -> int:
    return int(dut.current_state.value) & 0xF


def mask(dut) -> int:
    return int(dut.active_mask.value) & 0xF


def bit(signal) -> int:
    return int(signal.value) & 1


async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())


def init_inputs(dut):
    dut.rst.value = 0
    dut.core_start.value = 0
    dut.fetcher_done.value = 0
    dut.lsu_done.value = 0
    dut.mem_read_en.value = 0
    dut.mem_write_en.value = 0
    dut.ret.value = 0
    dut.divergence_detected.value = 0
    dut.taken_mask.value = 0
    dut.sync_en.value = 0
    dut.saved_mask.value = ALL_THREADS


async def step(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def reset_dut(dut):
    dut.rst.value = 1
    await step(dut)

    assert_state(dut, IDLE, "reset")
    assert_outputs(
        dut,
        fetcher_en=0,
        lsu_en=0,
        execute_en=0,
        write_back_en=0,
        block_done=0,
        pc_en=0,
        active_mask=ALL_THREADS,
        msg="reset",
    )

    dut.rst.value = 0
    await step(dut)


async def setup_dut(dut):
    await start_clock(dut)
    init_inputs(dut)
    await reset_dut(dut)


def assert_state(dut, expected, msg=""):
    got = state(dut)
    assert got == expected, f"{msg}: expected state {expected:04b}, got {got:04b}"


def assert_outputs(
    dut,
    fetcher_en=None,
    lsu_en=None,
    execute_en=None,
    write_back_en=None,
    block_done=None,
    pc_en=None,
    active_mask=None,
    msg="",
):
    checks = {
        "fetcher_en": fetcher_en,
        "lsu_en": lsu_en,
        "execute_en": execute_en,
        "write_back_en": write_back_en,
        "block_done": block_done,
        "pc_en": pc_en,
    }

    for name, expected in checks.items():
        if expected is None:
            continue
        got = bit(getattr(dut, name))
        assert got == expected, f"{msg}: {name} expected {expected}, got {got}"

    if active_mask is not None:
        got_mask = mask(dut)
        exp_mask = active_mask & 0xF
        assert got_mask == exp_mask, (
            f"{msg}: active_mask expected {exp_mask:04b}, got {got_mask:04b}"
        )


async def start_block(dut):
    dut.core_start.value = 1
    await step(dut)
    dut.core_start.value = 0
    await Timer(1, unit="ns")

    assert_state(dut, FETCH, "start_block")
    assert_outputs(
        dut,
        fetcher_en=1,
        lsu_en=0,
        execute_en=0,
        write_back_en=0,
        block_done=0,
        pc_en=0,
        active_mask=ALL_THREADS,
        msg="start_block",
    )


async def complete_fetch_to_decode(dut):
    dut.fetcher_done.value = 1
    await step(dut)
    dut.fetcher_done.value = 0
    await Timer(1, unit="ns")

    assert_state(dut, DECODE, "fetch done -> decode")
    assert_outputs(
        dut,
        fetcher_en=0,
        lsu_en=0,
        execute_en=0,
        write_back_en=0,
        block_done=0,
        pc_en=0,
        msg="fetch done -> decode",
    )


async def decode_to_execute_nonmem(dut):
    dut.mem_read_en.value = 0
    dut.mem_write_en.value = 0
    await step(dut)

    assert_state(dut, EXECUTE, "decode nonmem -> execute")


async def decode_to_request_mem(dut, read=True, write=False):
    dut.mem_read_en.value = 1 if read else 0
    dut.mem_write_en.value = 1 if write else 0
    await step(dut)

    assert_state(dut, REQUEST, "decode mem -> request")


async def request_to_wait(dut):
    await step(dut)

    assert_state(dut, WAIT, "request -> wait")
    assert_outputs(
        dut,
        lsu_en=1,
        fetcher_en=0,
        execute_en=0,
        write_back_en=0,
        block_done=0,
        pc_en=0,
        msg="request pulse",
    )


async def wait_to_execute(dut):
    dut.lsu_done.value = ALL_THREADS
    await step(dut)
    dut.lsu_done.value = 0
    await Timer(1, unit="ns")

    assert_state(dut, EXECUTE, "wait all done -> execute")


async def execute_to_update(dut):
    await step(dut)

    assert_state(dut, UPDATE, "execute -> update")
    assert_outputs(
        dut,
        execute_en=1,
        fetcher_en=0,
        lsu_en=0,
        write_back_en=0,
        block_done=0,
        pc_en=0,
        msg="execute pulse",
    )


async def update_normal_to_fetch(dut):
    dut.ret.value = 0
    dut.divergence_detected.value = 0
    dut.sync_en.value = 0
    await step(dut)

    assert_state(dut, FETCH, "update normal -> fetch")
    assert_outputs(
        dut,
        write_back_en=1,
        pc_en=1,
        block_done=0,
        msg="update normal pulse",
    )


async def update_ret_to_idle(dut):
    dut.ret.value = 1
    dut.divergence_detected.value = 0
    dut.sync_en.value = 0
    await step(dut)
    dut.ret.value = 0

    assert_state(dut, IDLE, "update ret -> idle")
    assert_outputs(
        dut,
        write_back_en=1,
        block_done=1,
        pc_en=0,
        msg="update ret pulse",
    )


async def update_diverge_to_diverge_state(dut, taken_mask):
    dut.ret.value = 0
    dut.divergence_detected.value = 1
    dut.taken_mask.value = taken_mask & 0xF
    dut.sync_en.value = 0
    await step(dut)

    assert_state(dut, DIVERGE, "update divergence -> diverge")
    assert_outputs(
        dut,
        write_back_en=1,
        pc_en=1,
        block_done=0,
        msg="update divergence pulse",
    )


async def diverge_to_fetch(dut, expected_mask):
    dut.divergence_detected.value = 0
    await step(dut)

    assert_state(dut, FETCH, "diverge -> fetch")
    assert_outputs(
        dut,
        active_mask=expected_mask,
        fetcher_en=0,
        write_back_en=0,
        pc_en=0,
        msg="diverge mask update",
    )


async def update_sync_to_sync_pop_state(dut, saved_mask):
    dut.ret.value = 0
    dut.divergence_detected.value = 0
    dut.sync_en.value = 1
    dut.saved_mask.value = saved_mask & 0xF
    await step(dut)

    assert_state(dut, SYNC_POP, "update sync -> sync_pop")
    assert_outputs(
        dut,
        write_back_en=1,
        pc_en=1,
        block_done=0,
        msg="update sync pulse",
    )


async def sync_pop_to_fetch(dut, expected_mask):
    dut.sync_en.value = 0
    await step(dut)

    assert_state(dut, FETCH, "sync_pop -> fetch")
    assert_outputs(
        dut,
        active_mask=expected_mask,
        fetcher_en=0,
        write_back_en=0,
        pc_en=0,
        msg="sync_pop mask update",
    )


async def run_to_update_nonmem(dut):
    await start_block(dut)
    await complete_fetch_to_decode(dut)
    await decode_to_execute_nonmem(dut)
    await execute_to_update(dut)


async def run_to_update_mem(dut, read=True, write=False):
    await start_block(dut)
    await complete_fetch_to_decode(dut)
    await decode_to_request_mem(dut, read=read, write=write)
    await request_to_wait(dut)
    await wait_to_execute(dut)
    await execute_to_update(dut)