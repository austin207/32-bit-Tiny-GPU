import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import os

def load_hex_file(filename):
    instructions = {}
    try:
        with open(filename, 'r') as f:
            for i, line in enumerate(f):
                line = line.strip()
                if line:
                    instructions[i] = int(line, 16)
        print(f"Loaded {len(instructions)} instructions from {filename}")
        for addr, instr in instructions.items():
            print(f"  [{addr}] 0x{instr:08X}")
    except FileNotFoundError:
        print(f"ERROR: Could not find {filename}")
    return instructions

def safe_int(signal, default=0):
    try:
        return int(signal.value)
    except Exception:
        return default

def safe_bit(signal, bit, default=0):
    try:
        return (int(signal.value) >> bit) & 1
    except Exception:
        return default

def read_raw(signal):
    try:
        return str(signal.value)
    except Exception as e:
        return f"ERR:{e}"

async def program_memory_model(dut, instructions):
    RET_INSTR = 0x48000000
    NUM_CORES = 4
    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        resp_valid = 0
        for i in range(NUM_CORES):
            if safe_bit(dut.prog_mem_req_valid, i) == 0:
                continue
            try:
                addr = safe_int(dut.core_gen[i].core_inst.fetch.req_addr, 0)
                instr = instructions.get(addr, RET_INSTR)
                dut.prog_mem_resp_data[i].value = instr
            except Exception:
                pass
            resp_valid |= (1 << i)
        dut.prog_mem_resp_valid.value = resp_valid

async def data_memory_model(dut, memory):
    NUM_CORES        = 4
    THREADS_PER_CORE = 4
    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        resp_valid = 0
        for core_id in range(NUM_CORES):
            for thread_id in range(THREADS_PER_CORE):
                global_thread = core_id * THREADS_PER_CORE + thread_id
                try:
                    lsu = (dut.core_gen[core_id].core_inst
                               .thread_gen[thread_id].lsu_inst)
                    if safe_int(lsu.req_valid, 0) == 0:
                        continue
                    addr = safe_int(lsu.mem_data_address, 0)
                    rw   = safe_int(lsu.read_write_switch, 1)
                    data = safe_int(lsu.mem_write_data, 0)
                except Exception:
                    continue
                if rw == 0:
                    memory[addr] = data
                    print(f"  Thread {global_thread}: STR -> mem[{addr}] = {data}")
                else:
                    val = memory.get(addr, 0)
                    try:
                        dut.data_mem_resp_data[global_thread].value = val
                    except Exception:
                        pass
                resp_valid |= (1 << global_thread)
        dut.data_mem_resp_valid.value = resp_valid

@cocotb.test()
async def test_gpu_axel_program(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    hex_path = os.path.join(
        os.path.dirname(__file__), "../../assembler/vector_add.hex")
    instructions = load_hex_file(hex_path)
    data_memory = {}

    dut.rst.value          = 1
    dut.dcr_write_en.value = 0
    dut.dcr_addr.value     = 0
    dut.dcr_data.value     = 0
    dut.prog_mem_resp_valid.value = 0
    for i in range(4):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    for i in range(16):
        dut.data_mem_resp_data[i].value = 0

    cocotb.start_soon(program_memory_model(dut, instructions))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.dcr_write_en.value = 1
    dut.dcr_addr.value     = 0b00
    dut.dcr_data.value     = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.dcr_addr.value = 0b01
    dut.dcr_data.value = 4
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.dcr_addr.value = 0b10
    dut.dcr_data.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.dcr_write_en.value = 0

    # ── DIAGNOSE blockIdx BEFORE kernel starts executing ──────────────────
    print("\n[DIAG] Core 0 blockIdx value:")
    try:
        raw = read_raw(dut.core_gen[0].core_inst.blockIdx_in)
        print(f"  core_inst.blockIdx_in = {raw}")
    except Exception as e:
        print(f"  blockIdx_in ERR: {e}")
    try:
        raw = read_raw(dut.core_gen[0].core_inst.blockIdx)
        print(f"  core_inst.blockIdx    = {raw}")
    except Exception as e:
        print(f"  blockIdx ERR: {e}")
    # ──────────────────────────────────────────────────────────────────────

    timeout = 1000
    for cycle in range(timeout):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            cocotb.log.info(f"GPU completed in {cycle + 1} cycles")
            break

    assert dut.kernel_done.value == 1, "GPU timed out"

    for _ in range(20):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

    print("\n--- Data Memory Results ---")
    for addr in sorted(data_memory.keys()):
        print(f"  mem[{addr}] = {data_memory[addr]}")

    all_pass = True
    for t in range(4):
        expected = t
        actual   = data_memory.get(t)
        ok = (actual == expected)
        if not ok:
            all_pass = False
        print(f"  Thread {t}: mem[{t}] = {actual}  expected={expected}  {'✓' if ok else '✗'}")

    for _ in range(50):
        await RisingEdge(dut.clk)