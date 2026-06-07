import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


MASK32 = 0xFFFFFFFF


def u32(v: int) -> int:
    return int(v) & MASK32


def val(signal) -> int:
    return int(signal.value) & MASK32


def bit(signal) -> int:
    return int(signal.value) & 1


async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())


def init_inputs(dut):
    dut.rst.value = 0
    dut.core_en.value = 0
    dut.pc_value.value = 0
    dut.resp_valid.value = 0
    dut.resp_data.value = 0


async def step(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def reset_dut(dut):
    dut.rst.value = 1
    await step(dut)

    assert bit(dut.req_valid) == 0, f"reset req_valid expected 0, got {dut.req_valid.value}"
    assert bit(dut.done) == 0, f"reset done expected 0, got {dut.done.value}"
    assert val(dut.req_addr) == 0, f"reset req_addr expected 0, got {dut.req_addr.value}"
    assert val(dut.instruction) == 0, f"reset instruction expected 0, got {dut.instruction.value}"

    dut.rst.value = 0
    await step(dut)


async def setup_dut(dut):
    await start_clock(dut)
    init_inputs(dut)
    await reset_dut(dut)


async def issue_request(dut, pc, keep_core_en=False):
    dut.core_en.value = 1
    dut.pc_value.value = u32(pc)
    dut.resp_valid.value = 0
    await step(dut)

    assert bit(dut.req_valid) == 1, f"request req_valid expected 1, got {dut.req_valid.value}"
    assert val(dut.req_addr) == u32(pc), f"request addr expected 0x{u32(pc):08x}, got 0x{val(dut.req_addr):08x}"
    assert bit(dut.done) == 0, f"request done expected 0, got {dut.done.value}"

    if not keep_core_en:
        dut.core_en.value = 0
        await Timer(1, unit="ns")


async def wait_no_response(dut, cycles=1):
    dut.resp_valid.value = 0

    for i in range(cycles):
        await step(dut)
        assert bit(dut.req_valid) == 0, f"waiting req_valid expected 0 at wait cycle {i}, got {dut.req_valid.value}"
        assert bit(dut.done) == 0, f"waiting done expected 0 at wait cycle {i}, got {dut.done.value}"


async def complete_response(dut, data):
    dut.resp_valid.value = 1
    dut.resp_data.value = u32(data)
    await step(dut)

    assert bit(dut.done) == 1, f"response done expected 1, got {dut.done.value}"
    assert val(dut.instruction) == u32(data), (
        f"response instruction expected 0x{u32(data):08x}, "
        f"got 0x{val(dut.instruction):08x}"
    )

    dut.resp_valid.value = 0
    await Timer(1, unit="ns")


def assert_fetch_outputs(dut, req_valid=None, done=None, req_addr=None, instruction=None, msg=""):
    if req_valid is not None:
        assert bit(dut.req_valid) == req_valid, (
            f"{msg} req_valid expected {req_valid}, got {dut.req_valid.value}"
        )

    if done is not None:
        assert bit(dut.done) == done, (
            f"{msg} done expected {done}, got {dut.done.value}"
        )

    if req_addr is not None:
        assert val(dut.req_addr) == u32(req_addr), (
            f"{msg} req_addr expected 0x{u32(req_addr):08x}, "
            f"got 0x{val(dut.req_addr):08x}"
        )

    if instruction is not None:
        assert val(dut.instruction) == u32(instruction), (
            f"{msg} instruction expected 0x{u32(instruction):08x}, "
            f"got 0x{val(dut.instruction):08x}"
        )