import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import os

# ─── Config — change these two things between phases ─────────────────────────

HEX_FILE = "../../assembler/builds/phase5_weight_update.hex"

#
# Pre-load data memory before the GPU starts.
# The GPU reads these values via LDR instructions.
# The GPU writes results back via STR instructions.
#
# Phase 1 — LDR test
W = [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
x = [16, 32, 48, 64]
y = [16, 32, 48, 64]   # identity W * x = x
t = [32, 64, 96, 128]  # targets (each double)
INITIAL_MEMORY = {i*4+j: W[i][j] for i in range(4) for j in range(4)}
INITIAL_MEMORY.update({16+j: x[j] for j in range(4)})
INITIAL_MEMORY.update({20+i: y[i] for i in range(4)})
INITIAL_MEMORY.update({24+i: t[i] for i in range(4)})
# Expected output: mem[4]=20, mem[5]=40, mem[6]=60, mem[7]=80

# ── Phase 2 — matmul ─────────────────────────────────────────────────────────
# W = identity matrix (y should equal x)
# HEX_FILE = "../../assembler/builds/phase2_matmul.hex"
# W = [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
# x = [5, 10, 15, 20]
# INITIAL_MEMORY = {i*4+j: W[i][j] for i in range(4) for j in range(4)}
# INITIAL_MEMORY.update({16+j: x[j] for j in range(4)})
# Expected output: mem[20]=5, mem[21]=10, mem[22]=15, mem[23]=20

# ── Phase 3 — branchless ReLU ────────────────────────────────────────────────
# HEX_FILE = "../../assembler/builds/phase3_relu.hex"
# INITIAL_MEMORY = {0: 5, 1: 0xFFFFFFFC, 2: 10, 3: 0xFFFFFFF8}
# Expected output: mem[4]=5, mem[5]=0, mem[6]=10, mem[7]=0

# ── Phase 4 — forward pass (matmul + ReLU) ───────────────────────────────────
# HEX_FILE = "../../assembler/builds/phase4_forward.hex"
# W = [[2,0,0,0],[0,2,0,0],[0,0,2,0],[0,0,0,2]]  # scale-by-2 matrix
# x = [3, 5, 7, 9]
# INITIAL_MEMORY = {i*4+j: W[i][j] for i in range(4) for j in range(4)}
# INITIAL_MEMORY.update({16+j: x[j] for j in range(4)})
# Expected output: mem[20]=6, mem[21]=10, mem[22]=14, mem[23]=18

# ── Phase 5 — weight update ──────────────────────────────────────────────────
# Run Phase 4 first to populate mem[20..23] with predictions, then:
# HEX_FILE = "../../assembler/builds/phase5_weight_update.hex"
# W  = [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
# x  = [1, 2, 3, 4]
# y  = [1, 2, 3, 4]  (predictions from Phase 4, same as x with identity W)
# t  = [2, 3, 4, 5]  (targets)
# INITIAL_MEMORY = {i*4+j: W[i][j] for i in range(4) for j in range(4)}
# INITIAL_MEMORY.update({16+j: x[j] for j in range(4)})
# INITIAL_MEMORY.update({20+i: y[i] for i in range(4)})
# INITIAL_MEMORY.update({24+i: t[i] for i in range(4)})
# Expected: W updated by one gradient step

# ─────────────────────────────────────────────────────────────────────────────

NUM_CORES        = 4
THREADS_PER_CORE = 4
TOTAL_THREADS    = NUM_CORES * THREADS_PER_CORE
TIMEOUT_CYCLES   = 2000

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
                if rw == 0:                          # STR — write
                    memory[addr] = data
                    print(f"  [T{global_thread:02d}] STR  mem[{addr}] = {data}")
                else:                                # LDR — read
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
    data_memory  = dict(INITIAL_MEMORY)       # pre-load memory for LDR

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

    print("\n--- Data Memory (final state) ---")
    if data_memory:
        for addr in sorted(data_memory.keys()):
            print(f"  mem[{addr:4d}] = {data_memory[addr]}")
    else:
        print("  (no writes)")

    for _ in range(50):
        await RisingEdge(dut.clk)