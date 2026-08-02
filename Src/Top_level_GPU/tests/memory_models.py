from cocotb.triggers import RisingEdge, Timer

from tests.common import NUM_CORES, safe_int, safe_bit

# ACCEL_CTRL_BASE..ACCEL_CTRL_TOP are ctrl registers handled by the RTL mux
# (top_level_gpu.sv's accel_sel decode: addr >= 0x1F0 && addr <= 0x1FF, a
# 16-word window, narrowed from an earlier open-ended `>= 0x1F0` that used
# to claim the entire rest of the address space -- see project memory
# project_accel_ctrl_address_ceiling.md). The data_memory_model must skip
# only that window to avoid polluting the Python dict and asserting
# spurious resp_valid for those cores; everything >= 0x200 is real data
# memory again.
ACCEL_CTRL_BASE = 0x1F0
ACCEL_CTRL_TOP = 0x1FF


async def program_memory_model(
    dut,
    instructions_ref,
    *,
    debug=False,
    debug_pc_limit=None,
):
    """
    Program memory model.

    instructions_ref must be a list:
        instructions_ref = [instructions]

    This lets chained tests switch kernels by:
        instructions_ref[0] = next_instructions
    """
    RET_INSTR = 0x48000000

    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        resp_valid = 0

        for core_id in range(NUM_CORES):
            if safe_bit(dut.prog_mem_req_valid, core_id) == 0:
                continue

            try:
                addr = safe_int(dut.core_gen[core_id].core_inst.fetch.req_addr, 0)
                instr = instructions_ref[0].get(addr, RET_INSTR)

                dut.prog_mem_resp_data[core_id].value = instr
                resp_valid |= (1 << core_id)

                if debug:
                    if debug_pc_limit is None or addr <= debug_pc_limit:
                        print(
                            f"[PMEM] core={core_id} "
                            f"pc={addr} instr=0x{instr:08x}"
                        )

            except Exception as e:
                if debug:
                    print(f"[PMEM] core={core_id} error: {e}")

        dut.prog_mem_resp_valid.value = resp_valid


async def data_memory_model(
    dut,
    memory,
    *,
    debug=False,
    debug_addr_min=None,
    debug_addr_max=None,
    debug_writes=True,
    debug_reads=True,
):
    """
    Data memory model with optional debug.

    Addresses in [ACCEL_CTRL_BASE, ACCEL_CTRL_TOP] (0x1F0-0x1FF) are
    skipped: the RTL address-decode mux in top_level_gpu intercepts those
    requests and serves them from the matmul_accelerator ctrl registers
    directly. Everything >= 0x200 is real data memory.

    debug=True enables memory transaction prints.
    Filter with:
        debug_addr_min=0
        debug_addr_max=64
    """
    resp_data_per_core = [0] * NUM_CORES

    def addr_in_debug_range(addr):
        if debug_addr_min is not None and addr < debug_addr_min:
            return False
        if debug_addr_max is not None and addr > debug_addr_max:
            return False
        return True

    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        resp_valid = 0

        for core_id in range(NUM_CORES):
            try:
                mc = dut.core_gen[core_id].core_inst.mc

                if safe_int(mc.mem_req_valid, 0) == 0:
                    continue

                addr = safe_int(mc.mem_req_addr, 0)
                rw   = safe_int(mc.mem_req_rw, 0)      # 1=read, 0=write
                data = safe_int(mc.mem_req_data, 0)

                try:
                    thread_id = safe_int(mc.in_flight, -1)
                except Exception:
                    thread_id = -1

            except Exception as e:
                if debug:
                    print(f"[DMEM] core={core_id} error: {e}")
                continue

            # ── Phase 4: skip ctrl reg space — RTL handles these internally ──
            if ACCEL_CTRL_BASE <= addr <= ACCEL_CTRL_TOP:
                if debug:
                    op = "READ" if rw else "WRITE"
                    print(
                        f"[DMEM] core={core_id} thread={thread_id} "
                        f"{op} ctrl_reg[0x{addr:03X}] — skipped (RTL mux)"
                    )
                continue  # do NOT write dict; do NOT assert resp_valid

            if rw == 0:
                memory[addr] = data & 0xFFFFFFFF
                resp_data_per_core[core_id] = 0

                if debug and debug_writes and addr_in_debug_range(addr):
                    print(
                        f"[DMEM] core={core_id} thread={thread_id} "
                        f"WRITE mem[{addr}] <= 0x{data & 0xFFFFFFFF:08x}"
                    )

            else:
                val = memory.get(addr, 0) & 0xFFFFFFFF
                resp_data_per_core[core_id] = val

                if debug and debug_reads and addr_in_debug_range(addr):
                    print(
                        f"[DMEM] core={core_id} thread={thread_id} "
                        f"READ  mem[{addr}] => 0x{val:08x}"
                    )

            resp_valid |= (1 << core_id)

        dut.data_mem_resp_valid.value = resp_valid

        packed = 0
        for core_id in range(NUM_CORES):
            packed |= (resp_data_per_core[core_id] & 0xFFFFFFFF) << (core_id * 32)

        dut.data_mem_resp_data.value = packed


async def accel_data_memory_model(
    dut,
    memory,
    *,
    debug=False,
):
    """
    Data memory model for the matmul accelerator's dedicated matrix I/O port.

    Serves dut.accel_data_req_* / drives dut.accel_data_resp_*.
    Shares the same Python dict as data_memory_model so the accelerator
    reads A/B from the same memory the GPU kernel set up, and writes C
    back to the same memory the test verifies.
    """
    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        dut.accel_data_resp_valid.value = 0
        dut.accel_data_resp_data.value  = 0

        if safe_int(dut.accel_data_req_valid, 0) == 0:
            continue

        addr = safe_int(dut.accel_data_req_addr, 0)
        rw   = safe_int(dut.accel_data_req_rw,   0)   # 1=read, 0=write
        data = safe_int(dut.accel_data_req_data,  0)

        if rw == 0:   # write
            memory[addr] = data & 0xFFFFFFFF
            dut.accel_data_resp_data.value = 0
            if debug:
                print(f"[ACCEL_DMEM] WRITE mem[{addr}] <= 0x{data & 0xFFFFFFFF:08x}")
        else:         # read
            val = memory.get(addr, 0) & 0xFFFFFFFF
            dut.accel_data_resp_data.value = val
            if debug:
                print(f"[ACCEL_DMEM] READ  mem[{addr}] => 0x{val:08x}")

        dut.accel_data_resp_valid.value = 1