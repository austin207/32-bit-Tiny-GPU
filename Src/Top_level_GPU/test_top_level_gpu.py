import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import os, sys
import json
import csv


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


SCHED_STATES = {
    0: "IDLE", 1: "FETCH", 2: "DECODE", 3: "REQUEST",
    4: "WAIT",  5: "EXECUTE", 6: "UPDATE", 7: "DIVERGE",
    8: "SYNC_POP", 9: "RECONVERGE",
}


# ─── axelbin loader ───────────────────────────────────────────────────────────
_TOOLS_PATH = os.path.join(os.path.dirname(__file__), '../../assembler/tools')
if _TOOLS_PATH not in sys.path:
    sys.path.insert(0, _TOOLS_PATH)
from axelbin import load_axelbin

# ─── Training config ──────────────────────────────────────────────────────────
FORWARD_HEX    = "../../assembler/builds/hex/phase4_forward.hex"
BACKWARD_HEX   = "../../assembler/builds/hex/phase5_weight_update.hex"
WEIGHTS_FILE   = "../../assembler/builds/weights.json"
N_EPOCHS       = 20
TIMEOUT_CYCLES = 10000

W_INIT = [
    [256, 0,   0,   0],
    [0,   256, 0,   0],
    [0,   0,   256, 0],
    [0,   0,   0,   256],
]

X = [256, 512, 768, 1024]
T = [512, 1024, 1536, 2048]

NUM_CORES        = 4
THREADS_PER_CORE = 4
# ──────────────────────────────────────────────────────────────────────────────


def q8_to_real(v):
    if v >= 0x80000000:
        v -= 0x100000000
    return v / 256.0


def u32_to_signed(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v >= 0x80000000 else v


def load_hex_file(path):
    instructions = {}
    try:
        with open(path, "r") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if line:
                    instructions[i] = int(line, 16)
    except FileNotFoundError:
        print(f"ERROR: hex not found: {path}")
    return instructions


def save_weights(data_memory, path):
    weights = {
        str(addr): data_memory[addr]
        for addr in range(16)
        if addr in data_memory
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(weights, f, indent=2)
    print(f"Weights saved -> {path}")


def load_weights(path):
    try:
        with open(path, "r") as f:
            raw = json.load(f)
        weights = {int(k): v for k, v in raw.items()}
        diag = [weights.get(i * 4 + i, 0) for i in range(4)]
        if any(v > 0x80000000 for v in diag):
            print("WARNING: corrupted weights detected, using initial weights")
            return {}
        return weights
    except FileNotFoundError:
        return {}


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
                addr = safe_int(dut.core_gen[i].core_inst.fetch.req_addr, 0)
                dut.prog_mem_resp_data[i].value = instructions_ref[0].get(
                    addr, RET_INSTR,
                )
                resp_valid |= (1 << i)
            except Exception:
                pass
        dut.prog_mem_resp_valid.value = resp_valid


async def data_memory_model(dut, memory):
    """
    data_mem_resp_data is packed:
        logic [NUM_CORES-1:0][31:0] data_mem_resp_data
    Core N gets bits [N*32+31 : N*32].
    """
    resp_data_per_core = [0] * NUM_CORES

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
                rw   = safe_int(mc.mem_req_rw,   0)  # 1=read  0=write
                data = safe_int(mc.mem_req_data,  0)
            except Exception:
                continue

            if rw == 0:
                memory[addr] = data
                resp_data_per_core[core_id] = 0
            else:
                resp_data_per_core[core_id] = memory.get(addr, 0) & 0xFFFFFFFF

            resp_valid |= (1 << core_id)

        dut.data_mem_resp_valid.value = resp_valid

        packed = 0
        for c in range(NUM_CORES):
            packed |= (resp_data_per_core[c] & 0xFFFFFFFF) << (c * 32)
        dut.data_mem_resp_data.value = packed


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

    dut.dcr_addr.value = 0b00
    dut.dcr_data.value = 1
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
                data_memory[i * 4 + j] = W_INIT[i][j]
        print("Using initial Q8 identity weights (W = I, diagonal=256)")

    for j in range(4):
        data_memory[16 + j] = X[j]
    for i in range(4):
        data_memory[24 + i] = T[i]

    dut.prog_mem_resp_valid.value = 0
    for i in range(NUM_CORES):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    dut.data_mem_resp_data.value  = 0

    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    x_real = [q8_to_real(v) for v in X]
    t_real = [q8_to_real(v) for v in T]
    print(f"x (real) = {x_real}")
    print(f"t (real) = {t_real}")

    for epoch in range(N_EPOCHS):
        instructions_ref[0] = fwd
        await reset_gpu(dut)
        await dispatch_kernel(dut)

        y_q8  = [data_memory.get(20 + i, 0) for i in range(4)]
        y_real = [q8_to_real(v) for v in y_q8]

        instructions_ref[0] = bwd
        await reset_gpu(dut)
        await dispatch_kernel(dut)

        e_real = [round(y_real[i] - t_real[i], 4) for i in range(4)]
        w_diag = [q8_to_real(data_memory.get(i * 4 + i, 0)) for i in range(4)]
        print(
            f"Epoch {epoch + 1:2d}/{N_EPOCHS} | "
            f"y={[round(v, 2) for v in y_real]} | "
            f"err={e_real} | "
            f"W_diag={[round(v, 4) for v in w_diag]}"
        )

    save_weights(data_memory, wfile)

    print("\n── Final weights (real values) ──")
    for i in range(4):
        row = [
            round(q8_to_real(data_memory.get(i * 4 + j, 0)), 4)
            for j in range(4)
        ]
        print(f"  W[{i}] = {row}")

    for _ in range(50):
        await RisingEdge(dut.clk)


@cocotb.test()
async def test_simt_relu(dut):
    """
    SIMT ReLU loaded from .axelbin binary.
    Collects a cycle-accurate execution trace inline.
    Writes trace_simt_relu.csv alongside this file.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base         = os.path.dirname(__file__)
    axelbin_path = os.path.join(base, "../../assembler/builds/bin/phase6_simt_relu.axelbin")
    _trace_csv   = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "trace_simt_relu.csv",
    )

    kernel       = load_axelbin(axelbin_path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory  = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    print(f"\n── axelbin loaded: {os.path.basename(axelbin_path)} ──")
    print(f"  num_blocks  : {kernel['num_blocks']}")
    print(f"  blockDim    : {kernel['blockDim']}")
    print(f"  instructions: {kernel['text_words']}")
    print(f"  data words  : {kernel['data_words']}")
    print("  Initial data memory:")
    for i, (raw, signed) in enumerate(zip(kernel["data_mem_raw"], kernel["data_mem"])):
        print(f"    mem[{i}] = {raw:#010x}  ({signed})")

    dut.rst.value          = 1
    dut.dcr_write_en.value = 0
    dut.prog_mem_resp_valid.value = 0
    for i in range(NUM_CORES):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    dut.data_mem_resp_data.value  = 0

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

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

    try:
        _core0    = dut.core_gen[0].core_inst
        _trace_ok = True
    except Exception as e:
        cocotb.log.warning(f"trace: core0 hierarchy failed ({e}), tracing disabled")
        _trace_ok = False

    trace_rows = []

    for _cyc in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        if _trace_ok:
            try:
                _sched = safe_int(_core0.current_state)
                _amask = safe_int(_core0.active_mask)
                _row = {
                    "cycle":       _cyc + 1,
                    "state":       SCHED_STATES.get(_sched, str(_sched)),
                    "state_num":   _sched,
                    "active_mask": f"{_amask:04b}",
                    "active_pc":   safe_int(_core0.active_pc),
                    "instruction": f"0x{safe_int(_core0.instruction):08x}",
                    "ws_empty":    safe_int(_core0.ws.stack_empty),
                    "kernel_done": safe_int(dut.kernel_done),
                }
                for _j in range(4):
                    _row[f"t{_j}_active"] = (_amask >> _j) & 1
                    try:
                        _row[f"t{_j}_wr_data"] = safe_int(_core0.write_data[_j])
                    except Exception:
                        _row[f"t{_j}_wr_data"] = 0
                trace_rows.append(_row)
            except Exception as _e:
                cocotb.log.warning(f"trace: row {_cyc} skipped: {_e}")

        if dut.kernel_done.value == 1:
            break

    if trace_rows:
        with open(_trace_csv, "w", newline="") as _f:
            _w = csv.DictWriter(_f, fieldnames=trace_rows[0].keys())
            _w.writeheader()
            _w.writerows(trace_rows)
        cocotb.log.info(f"trace: {len(trace_rows)} cycles -> {_trace_csv}")
    else:
        cocotb.log.error("trace: no rows collected")

    assert dut.kernel_done.value == 1, "Kernel never completed — hung"

    kc = safe_int(dut.kernel_cycles)
    cocotb.log.info(f"kernel_cycles = {kc}  (trace captured {len(trace_rows)} rows)")
    assert kc > 0, "kernel_cycles is 0 — counter not running"
    assert abs(kc - len(trace_rows)) <= 2, \
        f"kernel_cycles {kc} too far from trace row count {len(trace_rows)}"

    assert data_memory.get(4, None) == 5,  f"T0: expected 5, got {data_memory.get(4)}"
    assert data_memory.get(5, None) == 0,  f"T1: expected 0, got {data_memory.get(5)}"
    assert data_memory.get(6, None) == 8,  f"T2: expected 8, got {data_memory.get(6)}"
    assert data_memory.get(7, None) == 0,  f"T3: expected 0, got {data_memory.get(7)}"

    print("\n── SIMT ReLU Results ──")
    print(f"  mem[4] = {data_memory.get(4)}  (T0: +5 -> kept)   v")
    print(f"  mem[5] = {data_memory.get(5)}  (T1: -3 -> zeroed) v")
    print(f"  mem[6] = {data_memory.get(6)}  (T2: +8 -> kept)   v")
    print(f"  mem[7] = {data_memory.get(7)}  (T3: -1 -> zeroed) v")


@cocotb.test()
async def test_dot4_kernel(dut):
    """
    DOT4 end-to-end kernel test.
    Verifies DOT4 through the full GPU pipeline.
    Kernel: single thread computes dot([1,2,3,4], [1,2,3,4]) = 30.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base         = os.path.dirname(__file__)
    axelbin_path = os.path.join(base, "../../assembler/builds/bin/phase7_dot4_test.axelbin")

    kernel       = load_axelbin(axelbin_path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory  = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    def unpack_int8x4(word):
        lanes = []
        for shift in [0, 8, 16, 24]:
            byte = (word >> shift) & 0xFF
            lanes.append(byte - 256 if byte >= 128 else byte)
        return lanes

    vec_a    = unpack_int8x4(data_memory[0])
    vec_b    = unpack_int8x4(data_memory[1])
    expected = sum(a * b for a, b in zip(vec_a, vec_b))

    print("\n── DOT4 kernel ──")
    print(f"  vec A = {vec_a}")
    print(f"  vec B = {vec_b}")
    print(f"  golden dot product = {expected}")

    dut.rst.value          = 1
    dut.dcr_write_en.value = 0
    dut.prog_mem_resp_valid.value = 0
    for i in range(NUM_CORES):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    dut.data_mem_resp_data.value  = 0

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

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

    for _ in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            break

    assert dut.kernel_done.value == 1, "DOT4 kernel never completed — hung"

    result = u32_to_signed(data_memory.get(2, 0))
    print(f"  hardware result  = {result}")
    print(f"  kernel_cycles    = {safe_int(dut.kernel_cycles)}")

    assert result == expected, \
        f"DOT4 kernel: expected {expected}, got {result}"

    print(f"  DOT4 end-to-end: PASS (dot([1,2,3,4],[1,2,3,4]) = {result})")


@cocotb.test()
async def test_mlp_inference(dut):
    """
    Q8 MLP inference kernel — first real neural-network workload on the GPU.

    4 threads run in parallel, one per output neuron, with no divergence.
    Each thread computes: y[i] = CLAMP(RELU(SAR(DOT4(W_row_i, x), 8)))

    Memory layout:
      mem[0..3]  = W_row_0..3  packed INT8x4
      mem[4..7]  = x replicated
      mem[8..11] = y[0..3] INT32 output
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base         = os.path.dirname(__file__)
    axelbin_path = os.path.join(base, "../../assembler/builds/bin/phase8_mlp_inference.axelbin")

    kernel       = load_axelbin(axelbin_path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory  = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    EXPECTED = {8: 20, 9: 48, 10: 25, 11: 8}

    print("\n── Q8 MLP inference kernel ──")
    print("  4 threads, 1 block, no divergence")
    print(f"  expected y[0..3] at mem[8..11] = {[EXPECTED[k] for k in sorted(EXPECTED)]}")

    dut.rst.value          = 1
    dut.dcr_write_en.value = 0
    dut.prog_mem_resp_valid.value = 0
    for i in range(NUM_CORES):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    dut.data_mem_resp_data.value  = 0

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

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

    for _ in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            break

    assert dut.kernel_done.value == 1, "MLP inference kernel never completed — hung"

    kc = safe_int(dut.kernel_cycles)
    cocotb.log.info(f"kernel_cycles = {kc}")

    print("\n── MLP inference results ──")
    all_pass = True
    for addr, exp in sorted(EXPECTED.items()):
        got = u32_to_signed(data_memory.get(addr, 0))
        status = "v" if got == exp else "FAIL"
        print(f"  y[{addr-8}] mem[{addr}] = {got:4d}  (expected {exp:4d})  {status}")
        if got != exp:
            all_pass = False

    assert all_pass, "MLP inference: one or more outputs do not match golden reference"
    print(f"  kernel_cycles = {kc}")
    print("  MLP inference end-to-end: PASS")

# ─── Append these two functions to the bottom of test_top_level_gpu.py ───────


@cocotb.test()
async def test_ldr_regbase_single(dut):
    """
    Single-thread LDR with general-purpose register base.

    Verifies that R6 (a general-purpose register) can be used as
    the base address for LDR after the lsu_done_latch fix.

    Config  : 1 block, 1 thread (blockDim = 1)
    Kernel  : CONST R6=4 | LDR R1, R6, 0 | STR R1, THREAD_IDX, 8 | RET
    Pre-load: mem[4] = 0x12345678
    Expected: mem[8] = 0x12345678
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base         = os.path.dirname(__file__)
    axelbin_path = os.path.join(
        base, "../../assembler/builds/bin/phase9_ldr_regbase_single.axelbin"
    )

    kernel       = load_axelbin(axelbin_path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory  = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    EXPECTED = {8: 0x12345678}

    print("\n── LDR general-register base (single thread) ──")
    print(f"  num_blocks={kernel['num_blocks']}  blockDim={kernel['blockDim']}")
    print(f"  pre-load: mem[4] = {data_memory.get(4, 0):#010x}")
    print(f"  expected: mem[8] = {EXPECTED[8]:#010x}")

    dut.rst.value          = 1
    dut.dcr_write_en.value = 0
    dut.prog_mem_resp_valid.value = 0
    for i in range(NUM_CORES):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    dut.data_mem_resp_data.value  = 0

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

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

    for _ in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            break

    assert dut.kernel_done.value == 1, \
        "test_ldr_regbase_single: kernel never completed — hung"

    print("\n── Results ──")
    all_pass = True
    for addr, exp in sorted(EXPECTED.items()):
        got = data_memory.get(addr, 0) & 0xFFFFFFFF
        status = "PASS" if got == exp else "FAIL"
        print(f"  mem[{addr}] = {got:#010x}  (expected {exp:#010x})  {status}")
        if got != exp:
            all_pass = False

    kc = safe_int(dut.kernel_cycles)
    print(f"  kernel_cycles = {kc}")
    assert all_pass, "test_ldr_regbase_single: R6-base LDR gave wrong result"
    print("  R6-base LDR single-thread: PASS")


@cocotb.test()
async def test_ldr_regbase_broadcast(dut):
    """
    Multi-thread broadcast LDR with general-purpose register base.

    All 4 SIMT threads load from the SAME address using R6 as base.
    This is the critical case: 4 simultaneous requests to one address,
    serialized by the round-robin memory controller, each thread must
    get the correct resp_valid and correct data.

    If this passes, the old R29/R30/R31-only LDR constraint is confirmed
    stale — it was a symptom of the lsu_done_latch bug, now fixed.

    Config  : 1 block, 4 threads (blockDim = 4)
    Kernel  : CONST R6=4 | LDR R1, R6, 0 | STR R1, THREAD_IDX, 8 | RET
    Pre-load: mem[4] = 0x12345678
    Expected: mem[8..11] = 0x12345678  (one per thread)
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base         = os.path.dirname(__file__)
    axelbin_path = os.path.join(
        base, "../../assembler/builds/bin/phase9_ldr_regbase_broadcast.axelbin"
    )

    kernel       = load_axelbin(axelbin_path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory  = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    EXPECTED = {8: 0x12345678, 9: 0x12345678, 10: 0x12345678, 11: 0x12345678}

    print("\n── LDR general-register base (4-thread broadcast) ──")
    print(f"  num_blocks={kernel['num_blocks']}  blockDim={kernel['blockDim']}")
    print(f"  pre-load: mem[4] = {data_memory.get(4, 0):#010x}")
    print(f"  expected: mem[8..11] = 0x12345678 (all 4 threads)")

    dut.rst.value          = 1
    dut.dcr_write_en.value = 0
    dut.prog_mem_resp_valid.value = 0
    for i in range(NUM_CORES):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    dut.data_mem_resp_data.value  = 0

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

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

    for _ in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            break

    assert dut.kernel_done.value == 1, \
        "test_ldr_regbase_broadcast: kernel never completed — hung"

    print("\n── Results ──")
    all_pass = True
    for addr, exp in sorted(EXPECTED.items()):
        got = data_memory.get(addr, 0) & 0xFFFFFFFF
        status = "PASS" if got == exp else "FAIL"
        thread = addr - 8
        print(f"  thread {thread} | mem[{addr}] = {got:#010x}  (expected {exp:#010x})  {status}")
        if got != exp:
            all_pass = False

    kc = safe_int(dut.kernel_cycles)
    print(f"  kernel_cycles = {kc}")

    if all_pass:
        print("  R6-base broadcast LDR across 4 threads: PASS")
        print("  Confirms: old R29/R30/R31-only constraint is STALE.")
        print("  Root cause was lsu_done_latch bug. Now fixed.")
    else:
        print("  FAIL — general-register LDR base still broken after latch fix.")
        print("  Investigate: mem_controller same-address arbitration, writeback timing.")

    assert all_pass, "test_ldr_regbase_broadcast: one or more threads got wrong data"

# ─── Append these three functions to the bottom of test_top_level_gpu.py ─────


@cocotb.test()
async def test_mlp_8out(dut):
    """
    Config B: 4-in -> 8-out MLP layer.

    First multi-block kernel exercising correctness (not just completion).
    Two blocks dispatch: block 0 -> neurons 0-3, block 1 -> neurons 4-7.
    neuron_id = BLOCK_IDX * 4 + THREAD_IDX

    Also exercises GP-register base LDR (R9 = 8, x loaded via R9+0).

    Expected at mem[12..19]: [16, 37, 36, 15, 30, 0, 41, 0]
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base         = os.path.dirname(__file__)
    axelbin_path = os.path.join(
        base, "../../assembler/builds/bin/phase10_mlp_8out.axelbin"
    )

    kernel       = load_axelbin(axelbin_path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory  = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    EXPECTED = {
        12: 16, 13: 37, 14: 36, 15: 15,
        16: 30, 17:  0, 18: 41, 19:  0,
    }

    print("\n── Config B: 4-in -> 8-out, 2 blocks ──")
    print(f"  num_blocks={kernel['num_blocks']}  blockDim={kernel['blockDim']}")
    print(f"  expected y[0..7] = {[EXPECTED[k] for k in sorted(EXPECTED)]}")

    dut.rst.value          = 1
    dut.dcr_write_en.value = 0
    dut.prog_mem_resp_valid.value = 0
    for i in range(NUM_CORES):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    dut.data_mem_resp_data.value  = 0

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

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

    for _ in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            break

    assert dut.kernel_done.value == 1, \
        "test_mlp_8out: kernel never completed — hung"

    print("\n── Results ──")
    all_pass = True
    for addr, exp in sorted(EXPECTED.items()):
        got    = u32_to_signed(data_memory.get(addr, 0))
        status = "PASS" if got == exp else "FAIL"
        neuron = addr - 12
        print(f"  y[{neuron}] mem[{addr}] = {got:4d}  (expected {exp:4d})  {status}")
        if got != exp:
            all_pass = False

    kc = safe_int(dut.kernel_cycles)
    print(f"  kernel_cycles = {kc}")
    assert all_pass, "test_mlp_8out: one or more neuron outputs do not match golden"
    print("  Config B (4-in -> 8-out, 2 blocks): PASS")


@cocotb.test()
async def test_mlp_8in(dut):
    """
    Config C: 8-in -> 4-out MLP layer.

    First kernel to use double-DOT4 accumulation per thread.
    Thread computes 8-element dot product via two DOT4 instructions.
    DOT4 uses rs3=rd as accumulator, so second call adds onto first result.

    x = [85, 42, 127, 17, 60, -30, 10, -5]
    Expected at mem[10..13]: [20, 15, 28, 6]
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base         = os.path.dirname(__file__)
    axelbin_path = os.path.join(
        base, "../../assembler/builds/bin/phase11_mlp_8in.axelbin"
    )

    kernel       = load_axelbin(axelbin_path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory  = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    EXPECTED = {10: 20, 11: 15, 12: 28, 13: 6}

    print("\n── Config C: 8-in -> 4-out, 2x DOT4 accumulation ──")
    print(f"  num_blocks={kernel['num_blocks']}  blockDim={kernel['blockDim']}")
    print(f"  expected y[0..3] = {[EXPECTED[k] for k in sorted(EXPECTED)]}")

    dut.rst.value          = 1
    dut.dcr_write_en.value = 0
    dut.prog_mem_resp_valid.value = 0
    for i in range(NUM_CORES):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    dut.data_mem_resp_data.value  = 0

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

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

    for _ in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            break

    assert dut.kernel_done.value == 1, \
        "test_mlp_8in: kernel never completed — hung"

    print("\n── Results ──")
    all_pass = True
    for addr, exp in sorted(EXPECTED.items()):
        got    = u32_to_signed(data_memory.get(addr, 0))
        status = "PASS" if got == exp else "FAIL"
        neuron = addr - 10
        print(f"  y[{neuron}] mem[{addr}] = {got:4d}  (expected {exp:4d})  {status}")
        if got != exp:
            all_pass = False

    kc = safe_int(dut.kernel_cycles)
    print(f"  kernel_cycles = {kc}")
    assert all_pass, "test_mlp_8in: one or more neuron outputs do not match golden"
    print("  Config C (8-in -> 4-out, 2x DOT4): PASS")


@cocotb.test()
async def test_mlp_q6(dut):
    """
    Config D: 4-in -> 4-out, Q6 quantization scale (SAR 6).

    Same topology as phase8 but scale factor = 64 (not 256).
    Demonstrates that quantization granularity is a kernel-level choice,
    not a hardware constraint. Only the CONST shift value changes.

    Expected at mem[8..11]: [35, 89, 79, 49]
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base         = os.path.dirname(__file__)
    axelbin_path = os.path.join(
        base, "../../assembler/builds/bin/phase12_mlp_q6.axelbin"
    )

    kernel       = load_axelbin(axelbin_path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory  = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    EXPECTED = {8: 35, 9: 89, 10: 79, 11: 49}

    print("\n── Config D: 4-in -> 4-out, Q6 scale (SAR 6) ──")
    print(f"  num_blocks={kernel['num_blocks']}  blockDim={kernel['blockDim']}")
    print(f"  expected y[0..3] = {[EXPECTED[k] for k in sorted(EXPECTED)]}")

    dut.rst.value          = 1
    dut.dcr_write_en.value = 0
    dut.prog_mem_resp_valid.value = 0
    for i in range(NUM_CORES):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    dut.data_mem_resp_data.value  = 0

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

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

    for _ in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            break

    assert dut.kernel_done.value == 1, \
        "test_mlp_q6: kernel never completed — hung"

    print("\n── Results ──")
    all_pass = True
    for addr, exp in sorted(EXPECTED.items()):
        got    = u32_to_signed(data_memory.get(addr, 0))
        status = "PASS" if got == exp else "FAIL"
        neuron = addr - 8
        print(f"  y[{neuron}] mem[{addr}] = {got:4d}  (expected {exp:4d})  {status}")
        if got != exp:
            all_pass = False

    kc = safe_int(dut.kernel_cycles)
    print(f"  kernel_cycles = {kc}")
    assert all_pass, "test_mlp_q6: one or more neuron outputs do not match golden"
    print("  Config D (Q6 scale, SAR 6): PASS")

@cocotb.test()
async def test_digit_hidden_phase13(dut):
    """
    Phase 13: digit classifier hidden layer.

    Computes hidden activations:
        h = CLAMP(RELU(SAR(W_h * x, 8)))

    Expected:
        mem[20..23] = [42, 37, 0, 6]
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base = os.path.dirname(__file__)
    axelbin_path = os.path.join(
        base, "../../assembler/builds/bin/phase13_digit_hidden.axelbin"
    )

    kernel = load_axelbin(axelbin_path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    EXPECTED = {
        20: 42,
        21: 37,
        22: 0,
        23: 6,
    }

    print("\n── Phase 13: digit classifier hidden layer ──")
    print(f"  num_blocks={kernel['num_blocks']}  blockDim={kernel['blockDim']}")
    print(f"  expected h[0..3] at mem[20..23] = {[EXPECTED[k] for k in sorted(EXPECTED)]}")

    dut.rst.value = 1
    dut.dcr_write_en.value = 0
    dut.prog_mem_resp_valid.value = 0
    for i in range(NUM_CORES):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    dut.data_mem_resp_data.value = 0

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

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

    for _ in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            break

    assert dut.kernel_done.value == 1, \
        "test_digit_hidden_phase13: kernel never completed — hung"

    print("\n── Hidden layer results ──")
    all_pass = True
    for addr, exp in sorted(EXPECTED.items()):
        got = u32_to_signed(data_memory.get(addr, 0))
        status = "PASS" if got == exp else "FAIL"
        hidden_idx = addr - 20
        print(f"  h[{hidden_idx}] mem[{addr}] = {got:4d}  (expected {exp:4d})  {status}")
        if got != exp:
            all_pass = False

    kc = safe_int(dut.kernel_cycles)
    print(f"  kernel_cycles = {kc}")

    assert all_pass, "test_digit_hidden_phase13: hidden activations mismatch"
    print("  Phase 13 hidden layer: PASS")

@cocotb.test()
async def test_digit_output_phase14(dut):
    """
    Phase 14: digit classifier output layer.

    Uses scalar IMUL + ADD because hidden values are INT32 scalars,
    not packed INT8x4.

    This test preloads the known Phase 13 hidden output:
        h[0..3] = [42, 37, 0, 6]

    Then Phase 14 computes:
        y = CLAMP(RELU(SAR(W_o * h, 8)))

    Expected:
        mem[40..43] = [7, 5, 2, 5]
        argmax = class 0
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base = os.path.dirname(__file__)
    axelbin_path = os.path.join(
        base, "../../assembler/builds/bin/phase14_digit_output.axelbin"
    )

    kernel = load_axelbin(axelbin_path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    # Preload hidden activations from Phase 13.
    data_memory[20] = 42
    data_memory[21] = 37
    data_memory[22] = 0
    data_memory[23] = 6

    EXPECTED = {
        40: 7,
        41: 5,
        42: 2,
        43: 5,
    }

    print("\n── Phase 14: digit classifier output layer ──")
    print(f"  num_blocks={kernel['num_blocks']}  blockDim={kernel['blockDim']}")
    print("  preloaded h[0..3] = [42, 37, 0, 6]")
    print(f"  expected y[0..3] at mem[40..43] = {[EXPECTED[k] for k in sorted(EXPECTED)]}")
    print("  expected argmax = class 0")

    dut.rst.value = 1
    dut.dcr_write_en.value = 0
    dut.prog_mem_resp_valid.value = 0
    for i in range(NUM_CORES):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    dut.data_mem_resp_data.value = 0

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

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

    for _ in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            break

    assert dut.kernel_done.value == 1, \
        "test_digit_output_phase14: kernel never completed — hung"

    print("\n── Output layer results ──")
    all_pass = True
    scores = []

    for addr, exp in sorted(EXPECTED.items()):
        got = u32_to_signed(data_memory.get(addr, 0))
        scores.append(got)
        status = "PASS" if got == exp else "FAIL"
        out_idx = addr - 40
        print(f"  y[{out_idx}] mem[{addr}] = {got:4d}  (expected {exp:4d})  {status}")
        if got != exp:
            all_pass = False

    pred = max(range(len(scores)), key=lambda i: scores[i])

    kc = safe_int(dut.kernel_cycles)
    print(f"  scores = {scores}")
    print(f"  argmax = class {pred}")
    print(f"  kernel_cycles = {kc}")

    assert all_pass, "test_digit_output_phase14: output scores mismatch"
    assert pred == 0, f"test_digit_output_phase14: expected argmax class 0, got class {pred}"

    print("  Phase 14 output layer: PASS")

@cocotb.test()
async def test_pyaxel_runner(dut):
    """
    PyAXEL runtime test runner.
    Not called during normal 'make test' — only via COCOTB_TEST_FILTER=test_pyaxel_runner.
    """
    import json as _json

    kernel_path    = os.environ.get("PYAXEL_KERNEL")
    result_path    = os.environ.get("PYAXEL_RESULT")
    overrides_path = os.environ.get("PYAXEL_OVERRIDES")
    timeout_cycles = int(os.environ.get("PYAXEL_TIMEOUT", "10000"))

    if not kernel_path or not result_path:
        return

    kernel       = load_axelbin(kernel_path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory  = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    if overrides_path and os.path.isfile(overrides_path):
        with open(overrides_path) as f:
            overrides = _json.load(f)
        data_memory.update({int(k): v for k, v in overrides.items()})

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.rst.value          = 1
    dut.dcr_write_en.value = 0
    dut.prog_mem_resp_valid.value = 0
    for i in range(NUM_CORES):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    dut.data_mem_resp_data.value  = 0

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

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

    elapsed = 0
    for elapsed in range(timeout_cycles):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            break

    assert dut.kernel_done.value == 1, \
        f"pyaxel: kernel timed out after {timeout_cycles} cycles"

    result = {str(k): v for k, v in data_memory.items()}
    result["__cycles__"] = elapsed + 1

    with open(result_path, "w") as f:
        _json.dump(result, f)

