import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


THREADS_PER_CORE = 4
WORD_W = 32
MASK32 = 0xFFFFFFFF


def u32(v: int) -> int:
    return int(v) & MASK32


def bit(signal) -> int:
    return int(signal.value) & 1


def vec(signal) -> int:
    return int(signal.value)


def val(signal) -> int:
    return int(signal.value) & MASK32


def resp_word(dut, thread_id: int) -> int:
    """
    resp_data is packed:
        logic [THREADS_PER_CORE-1:0][31:0] resp_data

    Thread N occupies:
        bits [N*32 + 31 : N*32]
    """
    packed = int(dut.resp_data.value)
    return (packed >> (thread_id * WORD_W)) & MASK32


def resp_valid_bit(dut, thread_id: int) -> int:
    return (int(dut.resp_valid.value) >> thread_id) & 1


async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())


def init_inputs(dut):
    dut.rst.value = 0
    dut.req_valid.value = 0
    dut.req_rw.value = 0

    for i in range(THREADS_PER_CORE):
        dut.req_addr[i].value = 0
        dut.req_data[i].value = 0

    dut.mem_resp_valid.value = 0
    dut.mem_resp_data.value = 0


async def step(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def reset_dut(dut):
    dut.rst.value = 1
    await step(dut)

    assert bit(dut.mem_req_valid) == 0, f"reset mem_req_valid expected 0, got {dut.mem_req_valid.value}"
    assert val(dut.mem_req_addr) == 0, f"reset mem_req_addr expected 0, got {dut.mem_req_addr.value}"
    assert bit(dut.mem_req_rw) == 0, f"reset mem_req_rw expected 0, got {dut.mem_req_rw.value}"
    assert val(dut.mem_req_data) == 0, f"reset mem_req_data expected 0, got {dut.mem_req_data.value}"
    assert int(dut.resp_valid.value) == 0, f"reset resp_valid expected 0, got {dut.resp_valid.value}"

    for t in range(THREADS_PER_CORE):
        assert resp_word(dut, t) == 0, f"reset resp_data[{t}] expected 0, got 0x{resp_word(dut, t):08x}"

    dut.rst.value = 0
    await step(dut)


async def setup_dut(dut):
    await start_clock(dut)
    init_inputs(dut)
    await reset_dut(dut)


def clear_reqs(dut):
    dut.req_valid.value = 0
    dut.req_rw.value = 0

    for i in range(THREADS_PER_CORE):
        dut.req_addr[i].value = 0
        dut.req_data[i].value = 0


def set_thread_req(dut, thread_id: int, addr: int, rw: int, data: int = 0):
    """
    Single-thread request helper.

    For multi-thread simultaneous requests, use pulse_requests().
    """
    dut.req_valid.value = (1 << thread_id)
    dut.req_rw.value = (1 << thread_id) if rw else 0
    dut.req_addr[thread_id].value = u32(addr)
    dut.req_data[thread_id].value = u32(data)


async def pulse_requests(dut, requests):
    """
    requests: list of dicts:
      {"thread": int, "addr": int, "rw": 0/1, "data": int}

    rw convention:
      1 = read
      0 = write

    IMPORTANT:
      Build req_valid/req_rw masks locally and assign once.
      Do not repeatedly read dut.req_valid.value after assigning it,
      because cocotb signal writes may not be visible immediately in the
      same delta cycle.
    """
    clear_reqs(dut)

    valid_mask = 0
    rw_mask = 0

    for req in requests:
        t = req["thread"]
        rw = req["rw"]

        valid_mask |= (1 << t)

        if rw:
            rw_mask |= (1 << t)

        dut.req_addr[t].value = u32(req["addr"])
        dut.req_data[t].value = u32(req.get("data", 0))

    dut.req_valid.value = valid_mask
    dut.req_rw.value = rw_mask

    await step(dut)

    clear_reqs(dut)
    await Timer(1, unit="ns")


async def issue_single_request(dut, thread_id: int, addr: int, rw: int, data: int = 0):
    await pulse_requests(dut, [{"thread": thread_id, "addr": addr, "rw": rw, "data": data}])


async def memory_response(dut, data: int):
    dut.mem_resp_valid.value = 1
    dut.mem_resp_data.value = u32(data)
    await step(dut)
    dut.mem_resp_valid.value = 0
    await Timer(1, unit="ns")


async def wait_cycles(dut, cycles: int):
    dut.mem_resp_valid.value = 0

    for _ in range(cycles):
        await step(dut)


def assert_mem_req(dut, valid=None, addr=None, rw=None, data=None, msg=""):
    if valid is not None:
        assert bit(dut.mem_req_valid) == valid, (
            f"{msg} mem_req_valid expected {valid}, got {dut.mem_req_valid.value}"
        )

    if addr is not None:
        assert val(dut.mem_req_addr) == u32(addr), (
            f"{msg} mem_req_addr expected 0x{u32(addr):08x}, "
            f"got 0x{val(dut.mem_req_addr):08x}"
        )

    if rw is not None:
        assert bit(dut.mem_req_rw) == (rw & 1), (
            f"{msg} mem_req_rw expected {rw & 1}, got {dut.mem_req_rw.value}"
        )

    if data is not None:
        assert val(dut.mem_req_data) == u32(data), (
            f"{msg} mem_req_data expected 0x{u32(data):08x}, "
            f"got 0x{val(dut.mem_req_data):08x}"
        )


def assert_thread_response(dut, thread_id: int, valid: int, data=None, msg=""):
    got_valid = resp_valid_bit(dut, thread_id)
    assert got_valid == valid, (
        f"{msg} resp_valid[{thread_id}] expected {valid}, got {got_valid}, "
        f"full resp_valid=0b{int(dut.resp_valid.value):04b}"
    )

    if data is not None:
        got_data = resp_word(dut, thread_id)
        assert got_data == u32(data), (
            f"{msg} resp_data[{thread_id}] expected 0x{u32(data):08x}, "
            f"got 0x{got_data:08x}"
        )


def assert_only_thread_response(dut, thread_id: int, data=None, msg=""):
    for t in range(THREADS_PER_CORE):
        exp = 1 if t == thread_id else 0
        assert_thread_response(
            dut,
            t,
            exp,
            data if t == thread_id else None,
            msg=msg,
        )