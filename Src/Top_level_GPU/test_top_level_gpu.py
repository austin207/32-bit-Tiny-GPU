import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import os

# ─── Config ───────────────────────────────────────────────────────────────────
HEX_FILE         = "../../assembler/builds/vector_add.hex"
NUM_CORES        = 4
THREADS_PER_CORE = 4
TOTAL_THREADS    = NUM_CORES * THREADS_PER_CORE
TIMEOUT_CYCLES   = 2000
# ──────────────────────────────────────────────────────────────────────────────

def load_hex_file(path):
    instructions = {}
    try:
        with open(path, 'r') as f:
            for i, line in enumerate(f):
                line = line.strip()
                if line:
                    instructions[i] = int(line, 16)
        print(f"\nLoaded {len(instructions)} instructions from {path}")
        for addr, instr in instructions.items():
            print(f"  [{addr}] 0x{instr:08X}")
    except FileNotFoundError:
        print(f"ERROR: hex file not found: {path}")
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

async def program_memory_model(dut, instructions):
    RET_INSTR = 0x48000000
    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        resp_valid = 0
        for i in range(NUM_CORES):
            if safe_bit(dut.prog_mem_req_valid, i) == 0:
                continue
            try:
                addr  = safe_int(dut.core_gen[i].core_inst.fetch.req_addr, 0)
                instr = instructions.get(addr, RET_INSTR)
                dut.prog_mem_resp_data[i].value = instr
            except Exception:
                pass
            resp_valid |= (1 << i)
        dut.prog_mem_resp_valid.value = resp_valid

async def data_memory_model(dut, memory):
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
                    data = safe_int(lsu.mem_write_data,   0)
                except Exception:
                    continue
                if rw == 0:
                    memory[addr] = data
                    print(f"  [T{global_thread:02d}] STR  mem[{addr}] = {data}")
                else:
                    val = memory.get(addr, 0)
                    try:
                        dut.data_mem_resp_data[global_thread].value = val
                    except Exception:
                        pass
                    print(f"  [T{global_thread:02d}] LDR  mem[{addr}] -> {val}")
                resp_valid |= (1 << global_thread)
        dut.data_mem_resp_valid.value = resp_valid

@cocotb.test()
async def test_gpu_axel_program(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    hex_path     = os.path.join(os.path.dirname(__file__), HEX_FILE)
    instructions = load_hex_file(hex_path)
    data_memory  = {}

    dut.rst.value          = 1
    dut.dcr_write_en.value = 0
    dut.dcr_addr.value     = 0
    dut.dcr_data.value     = 0
    dut.prog_mem_resp_valid.value = 0
    for i in range(NUM_CORES):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    for i in range(TOTAL_THREADS):
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

    print("\n--- Execution ---")
    for cycle in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            cocotb.log.info(f"kernel_done in {cycle + 1} cycles")
            break

    assert dut.kernel_done.value == 1, \
        f"GPU timed out after {TIMEOUT_CYCLES} cycles — check your program has a RET"

    for _ in range(20):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

    print("\n--- Data Memory ---")
    if data_memory:
        for addr in sorted(data_memory.keys()):
            print(f"  mem[{addr:4d}] = {data_memory[addr]}")
    else:
        print("  (no data memory writes)")

    for _ in range(50):
        await RisingEdge(dut.clk)