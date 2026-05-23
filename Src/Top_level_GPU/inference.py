import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import os
import json

# ─── Inference config ─────────────────────────────────────────────────────────
FORWARD_HEX  = "../../assembler/builds/phase4_forward.hex"
WEIGHTS_FILE = "../../assembler/builds/weights.json"

# Q8 encoding: real value v → int(v * 256)
# Examples:
#   [1.0, 2.0, 3.0, 4.0]  → [256, 512, 768, 1024]
#   [0.5, 1.0, 1.5, 2.0]  → [128, 256, 384, 512]
X_INPUT = [256, 512, 768, 1024]   # change this to run on different inputs

NUM_CORES        = 4
THREADS_PER_CORE = 4
TOTAL_THREADS    = NUM_CORES * THREADS_PER_CORE
TIMEOUT_CYCLES   = 2000
# ──────────────────────────────────────────────────────────────────────────────

def q8_to_real(v):
    """Convert Q8 unsigned 32-bit int to signed real."""
    if v >= 0x80000000:
        v -= 0x100000000
    return round(v / 256.0, 4)

def load_hex_file(path):
    instructions = {}
    with open(path, 'r') as f:
        for i, line in enumerate(f):
            line = line.strip()
            if line:
                instructions[i] = int(line, 16)
    return instructions

def load_weights(path):
    with open(path, 'r') as f:
        raw = json.load(f)
    return {int(k): v for k, v in raw.items()}

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
                    data = safe_int(lsu.mem_write_data, 0)
                except Exception:
                    continue
                if rw == 0:
                    memory[addr] = data
                else:
                    val = memory.get(addr, 0)
                    try:
                        dut.data_mem_resp_data[global_thread].value = val
                    except Exception:
                        pass
                resp_valid |= (1 << global_thread)
        dut.data_mem_resp_valid.value = resp_valid

@cocotb.test()
async def test_gpu_inference(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base         = os.path.dirname(__file__)
    instructions = load_hex_file(os.path.join(base, FORWARD_HEX))
    weights      = load_weights(os.path.join(base, WEIGHTS_FILE))
    data_memory  = dict(weights)

    # Load input into mem[16..19]
    for j in range(4):
        data_memory[16+j] = X_INPUT[j]

    x_real = [q8_to_real(v) for v in X_INPUT]
    print(f"\n{'='*45}")
    print(f"  Input  (Q8 raw) : {X_INPUT}")
    print(f"  Input  (real)   : {x_real}")
    print(f"{'='*45}")

    # Init DUT
    dut.rst.value          = 1
    dut.dcr_write_en.value = 0
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

    # DCR: num_blocks=1, blockDim=4, start
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

    # Wait for kernel_done
    for cycle in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            break

    # Read output from mem[20..23]
    y_q8  = [data_memory.get(20+i, 0) for i in range(4)]
    y_real = [q8_to_real(v) for v in y_q8]

    print(f"  Output (Q8 raw) : {y_q8}")
    print(f"  Output (real)   : {y_real}")
    print(f"{'='*45}\n")

    for _ in range(50):
        await RisingEdge(dut.clk)