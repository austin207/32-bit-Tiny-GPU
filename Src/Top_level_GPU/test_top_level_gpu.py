import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import os
import json

# ─── Training config ──────────────────────────────────────────────────────────
FORWARD_HEX  = "../../assembler/builds/phase4_forward.hex"
BACKWARD_HEX = "../../assembler/builds/phase5_weight_update.hex"
WEIGHTS_FILE = "../../assembler/builds/weights.json"
N_EPOCHS     = 20
TIMEOUT_CYCLES = 2000

# Q8 encoding: real value v → int(v * 256)
# W = identity (1.0 on diagonal)
# x = [1.0, 2.0, 3.0, 4.0]
# t = [2.0, 4.0, 6.0, 8.0]  (want W*x ≈ t, so W should converge toward 2*I)
W_INIT = [[256,0,0,0],[0,256,0,0],[0,0,256,0],[0,0,0,256]]
X      = [256, 512, 768, 1024]
T      = [512, 1024, 1536, 2048]

NUM_CORES        = 4
THREADS_PER_CORE = 4
TOTAL_THREADS    = NUM_CORES * THREADS_PER_CORE
# ──────────────────────────────────────────────────────────────────────────────

def q8_to_real(v):
    """Convert Q8 unsigned int to signed real (for display only)."""
    if v >= 0x80000000:
        v -= 0x100000000
    return v / 256.0

def load_hex_file(path):
    instructions = {}
    try:
        with open(path, 'r') as f:
            for i, line in enumerate(f):
                line = line.strip()
                if line:
                    instructions[i] = int(line, 16)
    except FileNotFoundError:
        print(f"ERROR: hex not found: {path}")
    return instructions

def save_weights(data_memory, path):
    weights = {str(addr): data_memory[addr] for addr in range(16) if addr in data_memory}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(weights, f, indent=2)
    print(f"Weights saved → {path}")

def load_weights(path):
    try:
        with open(path, 'r') as f:
            raw = json.load(f)
        weights = {int(k): v for k, v in raw.items()}
        # Sanity check: diagonal should be positive
        diag = [weights.get(i*4+i, 0) for i in range(4)]
        if any(v > 0x80000000 for v in diag):   # negative in unsigned
            print("WARNING: corrupted weights detected, using initial weights")
            return {}
        return weights
    except FileNotFoundError:
        return {}

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

async def program_memory_model(dut, instructions_ref):
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
                instr = instructions_ref[0].get(addr, RET_INSTR)
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

async def reset_gpu(dut):
    dut.rst.value = 1
    dut.dcr_write_en.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

async def dispatch_kernel(dut):
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
    for cycle in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            return cycle + 1
    return -1

@cocotb.test()
async def test_gpu_axel_program(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base  = os.path.dirname(__file__)
    fwd   = load_hex_file(os.path.join(base, FORWARD_HEX))
    bwd   = load_hex_file(os.path.join(base, BACKWARD_HEX))
    wfile = os.path.join(base, WEIGHTS_FILE)

    instructions_ref = [fwd]
    data_memory = {}

    saved = load_weights(wfile)
    if saved:
        data_memory.update(saved)
        print("Loaded existing weights")
    else:
        for i in range(4):
            for j in range(4):
                data_memory[i*4+j] = W_INIT[i][j]
        print("Using initial Q8 identity weights (W = I, diagonal=256)")

    for j in range(4):
        data_memory[16+j] = X[j]
    for i in range(4):
        data_memory[24+i] = T[i]

    dut.prog_mem_resp_valid.value = 0
    for i in range(NUM_CORES):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    for i in range(TOTAL_THREADS):
        dut.data_mem_resp_data[i].value = 0

    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    x_real = [q8_to_real(v) for v in X]
    t_real = [q8_to_real(v) for v in T]
    print(f"x (real) = {x_real}")
    print(f"t (real) = {t_real}")

    for epoch in range(N_EPOCHS):
        # Forward pass
        instructions_ref[0] = fwd
        await reset_gpu(dut)
        await dispatch_kernel(dut)
        y_q8   = [data_memory.get(20+i, 0) for i in range(4)]
        y_real = [q8_to_real(v) for v in y_q8]

        # Backward pass
        instructions_ref[0] = bwd
        await reset_gpu(dut)
        await dispatch_kernel(dut)

        e_real = [round(y_real[i] - t_real[i], 4) for i in range(4)]
        w_diag = [q8_to_real(data_memory.get(i*4+i, 0)) for i in range(4)]

        print(f"Epoch {epoch+1:2d}/{N_EPOCHS} | "
              f"y={[round(v,2) for v in y_real]} | "
              f"err={e_real} | "
              f"W_diag={[round(v,4) for v in w_diag]}")

    save_weights(data_memory, wfile)

    print("\n── Final weights (real values) ──")
    for i in range(4):
        row = [round(q8_to_real(data_memory.get(i*4+j, 0)), 4) for j in range(4)]
        print(f"  W[{i}] = {row}")

    for _ in range(50):
        await RisingEdge(dut.clk)

@cocotb.test()
async def test_simt_relu(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base = os.path.dirname(__file__)
    RELU_HEX = "../../assembler/builds/phase6_simt_relu.hex"
    instructions = load_hex_file(os.path.join(base, RELU_HEX))

    # Pre-load: T0=+5, T1=-3, T2=+8, T3=-1
    data_memory = {
        0: 5,
        1: 0xFFFFFFFD,
        2: 8,
        3: 0xFFFFFFFF
    }

    dut.rst.value          = 1
    dut.dcr_write_en.value = 0
    dut.prog_mem_resp_valid.value = 0
    for i in range(NUM_CORES):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    for i in range(TOTAL_THREADS):
        dut.data_mem_resp_data[i].value = 0

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    # Dispatch: 1 block, blockDim=4
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
    for _ in range(5000):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            break

    assert dut.kernel_done.value == 1, "Kernel never completed — hung"

    # Verify ReLU results
    assert data_memory.get(4, None) == 5,          f"T0: expected 5,  got {data_memory.get(4)}"
    assert data_memory.get(5, None) == 0,          f"T1: expected 0,  got {data_memory.get(5)}"
    assert data_memory.get(6, None) == 8,          f"T2: expected 8,  got {data_memory.get(6)}"
    assert data_memory.get(7, None) == 0,          f"T3: expected 0,  got {data_memory.get(7)}"

    print("\n── SIMT ReLU Results ──")
    print(f"  mem[4] = {data_memory.get(4)}  (T0: +5 → kept)  ✓")
    print(f"  mem[5] = {data_memory.get(5)}  (T1: -3 → zeroed) ✓")
    print(f"  mem[6] = {data_memory.get(6)}  (T2: +8 → kept)  ✓")
    print(f"  mem[7] = {data_memory.get(7)}  (T3: -1 → zeroed) ✓")