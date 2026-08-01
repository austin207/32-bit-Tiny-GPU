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
    dut.data_mem_resp_data.value  = 0

    # Phase 4: accelerator matrix data port
    dut.accel_data_resp_valid.value = 0
    dut.accel_data_resp_data.value  = 0


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


async def launch_kernel(
    dut,
    instructions_ref,
    instructions,
    *,
    num_blocks=1,
    blockDim=1,
    timeout_cycles=TIMEOUT_CYCLES,
    reset=True,
):
    """
    Load `instructions` (an {addr: word} dict, same shape axelcc's raw
    .hex-based tests already build) as the next program and run it to
    completion. Call once per kernel in a sequential-launch chain.

    `instructions_ref` (the mutable [dict] cell passed to
    program_memory_model) and any data_memory_model coroutines must
    already be running -- this only drives the DCR/reset/poll sequence.
    The data_memory dict is owned by the caller and is *not* touched here,
    so it persists across launches: that's how kernels in this project
    communicate with each other (through mem[], not through registers),
    matching test_phase16_digit64_classifier's proven phase15->phase16
    chain (see run_kernel above, which this generalizes to not require an
    .axelbin-loaded `kernel` dict).

    reset=True (default) does a full DUT reset before launching, so every
    kernel gets a clean register file, warp-stack, and dispatcher state.
    reset=False skips it and just re-triggers DCR/dispatch, relying on the
    dispatcher's own running/kernel_done bookkeeping (it resets cleanly on
    the next dispatch_en pulse) -- only safe if you've confirmed the prior
    kernel left the warp stack empty. warp_stack.sv's `sp` is cleared only
    by `rst`, not by block_rst/core_start, so a kernel that somehow RETs
    mid-divergence (shouldn't happen in a well-formed kernel, but not
    hardware-enforced) would leave stale entries for the next kernel under
    reset=False. Default to reset=True unless you have a specific reason
    (e.g. timing/cycle-count measurement across a chain) not to.

    Returns the cycle count the kernel took, or None on timeout.
    """
    instructions_ref[0] = instructions

    if reset:
        await reset_gpu(dut)

    dut.dcr_write_en.value = 1

    dut.dcr_addr.value = 0b00
    dut.dcr_data.value = num_blocks
    await RisingEdge(dut.clk)

    dut.dcr_addr.value = 0b01
    dut.dcr_data.value = blockDim
    await RisingEdge(dut.clk)

    dut.dcr_addr.value = 0b10
    dut.dcr_data.value = 0
    await RisingEdge(dut.clk)

    dut.dcr_write_en.value = 0

    for cycle in range(timeout_cycles):
        await RisingEdge(dut.clk)
        if dut.kernel_done.value == 1:
            return cycle + 1

    return None


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