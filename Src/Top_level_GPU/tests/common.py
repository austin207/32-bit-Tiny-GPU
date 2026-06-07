import os
import sys

from cocotb.triggers import RisingEdge, Timer


_TOOLS_PATH = os.path.join(os.path.dirname(__file__), "../../../assembler/tools")
if _TOOLS_PATH not in sys.path:
    sys.path.insert(0, _TOOLS_PATH)

from axelbin import load_axelbin


NUM_CORES = 4
THREADS_PER_CORE = 4
TIMEOUT_CYCLES = 100000


SCHED_STATES = {
    0: "IDLE",
    1: "FETCH",
    2: "DECODE",
    3: "REQUEST",
    4: "WAIT",
    5: "EXECUTE",
    6: "UPDATE",
    7: "DIVERGE",
    8: "SYNC_POP",
    9: "RECONVERGE",
}


def safe_int(sig, default=0):
    try:
        return int(sig.value)
    except Exception:
        return default


def safe_bit(signal, bit, default=0):
    try:
        return (int(signal.value) >> bit) & 1
    except Exception:
        return default


def u32_to_signed(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v >= 0x80000000 else v


def init_bus(dut):
    dut.rst.value = 1
    dut.dcr_write_en.value = 0

    dut.prog_mem_resp_valid.value = 0
    for i in range(NUM_CORES):
        dut.prog_mem_resp_data[i].value = 0

    dut.data_mem_resp_valid.value = 0
    dut.data_mem_resp_data.value = 0


async def reset_gpu(dut):
    dut.rst.value = 1
    dut.dcr_write_en.value = 0

    for _ in range(3):
        await RisingEdge(dut.clk)

    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def run_kernel(dut, kernel, *, timeout_cycles=TIMEOUT_CYCLES):
    await reset_gpu(dut)

    dut.dcr_write_en.value = 1

    dut.dcr_addr.value = 0b00
    dut.dcr_data.value = kernel["num_blocks"]
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.dcr_addr.value = 0b01
    dut.dcr_data.value = kernel["blockDim"]
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.dcr_addr.value = 0b10
    dut.dcr_data.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.dcr_write_en.value = 0

    for cycle in range(timeout_cycles):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        if dut.kernel_done.value == 1:
            return safe_int(dut.kernel_cycles), cycle + 1

    return None, timeout_cycles


async def print_core_debug(dut):
    print("\n── Core debug snapshot ──")

    try:
        disp = dut.dispatcher_inst
        print("\n── Dispatcher debug ──")
        for name in [
            "dispatch_en",
            "num_blocks",
            "blockDim",
            "kernel_done",
            "current_state",
            "state",
            "block_counter",
            "blocks_dispatched",
            "blocks_completed",
            "core_start",
            "block_done",
        ]:
            try:
                print(f"{name} = {safe_int(getattr(disp, name))}")
            except Exception:
                pass
    except Exception as e:
        print(f"dispatcher debug unavailable: {e}")

    print("\n── Per-core debug ──")
    for core_id in range(NUM_CORES):
        try:
            core = dut.core_gen[core_id].core_inst
            state = safe_int(core.current_state)
            pc = safe_int(core.active_pc)
            instr = safe_int(core.instruction)
            active_mask = safe_int(core.active_mask)

            print(
                f"core{core_id}: "
                f"state={SCHED_STATES.get(state, state)} "
                f"pc={pc} instr=0x{instr:08x} "
                f"active_mask=0b{active_mask:04b}"
            )
        except Exception as e:
            print(f"core{core_id}: debug unavailable: {e}")