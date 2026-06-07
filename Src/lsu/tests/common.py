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
    dut.mem_data_address.value = 0

    dut.resp_valid.value = 0
    dut.resp_data.value = 0

    dut.mem_write_en.value = 0
    dut.mem_write_data.value = 0
    dut.mem_read_en.value = 0


async def step(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def reset_dut(dut):
    dut.rst.value = 1
    await step(dut)

    assert bit(dut.req_valid) == 0, f"reset req_valid expected 0, got {dut.req_valid.value}"
    assert val(dut.req_addr) == 0, f"reset req_addr expected 0, got {dut.req_addr.value}"
    assert val(dut.mem_read_data) == 0, f"reset mem_read_data expected 0, got {dut.mem_read_data.value}"
    assert bit(dut.done) == 0, f"reset done expected 0, got {dut.done.value}"

    # NOTE:
    # Current RTL does not reset write_data or read_write_switch.
    # Do not assert reset value for those unless RTL is changed.

    dut.rst.value = 0
    await step(dut)


async def setup_dut(dut):
    await start_clock(dut)
    init_inputs(dut)
    await reset_dut(dut)


def deassert_controls(dut):
    dut.core_en.value = 0
    dut.mem_read_en.value = 0
    dut.mem_write_en.value = 0
    dut.resp_valid.value = 0


async def issue_read(dut, addr, keep_core_en=False, keep_read_en=False):
    dut.core_en.value = 1
    dut.mem_read_en.value = 1
    dut.mem_write_en.value = 0
    dut.mem_data_address.value = u32(addr)
    dut.resp_valid.value = 0
    await step(dut)

    assert bit(dut.req_valid) == 1, f"read req_valid expected 1, got {dut.req_valid.value}"
    assert val(dut.req_addr) == u32(addr), (
        f"read req_addr expected 0x{u32(addr):08x}, got 0x{val(dut.req_addr):08x}"
    )
    assert bit(dut.read_write_switch) == 1, (
        f"read read_write_switch expected 1, got {dut.read_write_switch.value}"
    )
    assert bit(dut.done) == 0, f"read request done expected 0, got {dut.done.value}"

    if not keep_core_en:
        dut.core_en.value = 0
    if not keep_read_en:
        dut.mem_read_en.value = 0
    await Timer(1, unit="ns")


async def issue_write(dut, addr, data, keep_core_en=False, keep_write_en=False):
    dut.core_en.value = 1
    dut.mem_read_en.value = 0
    dut.mem_write_en.value = 1
    dut.mem_data_address.value = u32(addr)
    dut.mem_write_data.value = u32(data)
    dut.resp_valid.value = 0
    await step(dut)

    assert bit(dut.req_valid) == 1, f"write req_valid expected 1, got {dut.req_valid.value}"
    assert val(dut.req_addr) == u32(addr), (
        f"write req_addr expected 0x{u32(addr):08x}, got 0x{val(dut.req_addr):08x}"
    )
    assert val(dut.write_data) == u32(data), (
        f"write_data expected 0x{u32(data):08x}, got 0x{val(dut.write_data):08x}"
    )
    assert bit(dut.read_write_switch) == 0, (
        f"write read_write_switch expected 0, got {dut.read_write_switch.value}"
    )
    assert bit(dut.done) == 0, f"write request done expected 0, got {dut.done.value}"

    if not keep_core_en:
        dut.core_en.value = 0
    if not keep_write_en:
        dut.mem_write_en.value = 0
    await Timer(1, unit="ns")


async def wait_no_response(dut, cycles=1):
    dut.resp_valid.value = 0

    for i in range(cycles):
        await step(dut)
        assert bit(dut.req_valid) == 0, f"waiting req_valid expected 0 at cycle {i}, got {dut.req_valid.value}"
        assert bit(dut.done) == 0, f"waiting done expected 0 at cycle {i}, got {dut.done.value}"


async def complete_read_response(dut, data):
    dut.resp_valid.value = 1
    dut.resp_data.value = u32(data)
    await step(dut)

    assert bit(dut.done) == 1, f"read response done expected 1, got {dut.done.value}"
    assert val(dut.mem_read_data) == u32(data), (
        f"mem_read_data expected 0x{u32(data):08x}, got 0x{val(dut.mem_read_data):08x}"
    )

    dut.resp_valid.value = 0
    await Timer(1, unit="ns")


async def complete_write_response(dut):
    dut.resp_valid.value = 1
    await step(dut)

    assert bit(dut.done) == 1, f"write response done expected 1, got {dut.done.value}"

    dut.resp_valid.value = 0
    await Timer(1, unit="ns")


def assert_lsu_outputs(
    dut,
    req_valid=None,
    done=None,
    req_addr=None,
    write_data=None,
    mem_read_data=None,
    read_write_switch=None,
    msg="",
):
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
            f"{msg} req_addr expected 0x{u32(req_addr):08x}, got 0x{val(dut.req_addr):08x}"
        )

    if write_data is not None:
        assert val(dut.write_data) == u32(write_data), (
            f"{msg} write_data expected 0x{u32(write_data):08x}, got 0x{val(dut.write_data):08x}"
        )

    if mem_read_data is not None:
        assert val(dut.mem_read_data) == u32(mem_read_data), (
            f"{msg} mem_read_data expected 0x{u32(mem_read_data):08x}, "
            f"got 0x{val(dut.mem_read_data):08x}"
        )

    if read_write_switch is not None:
        assert bit(dut.read_write_switch) == read_write_switch, (
            f"{msg} read_write_switch expected {read_write_switch}, got {dut.read_write_switch.value}"
        )