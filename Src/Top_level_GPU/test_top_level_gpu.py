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
    if v >= 0x80000000:
        return v - 0x100000000
    return v


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
                mc   = dut.core_gen[core_id].core_inst.mc
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
    Collects a cycle-accurate execution trace inline (no concurrent task).
    Writes trace_simt_relu.csv alongside this file.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base         = os.path.dirname(__file__)
    axelbin_path = os.path.join(base, "../../assembler/builds/bin/phase6_simt_relu.axelbin")
    _trace_csv   = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "trace_simt_relu.csv")

    # ── Load kernel binary ────────────────────────────────────────────────────
    kernel       = load_axelbin(axelbin_path)
    instructions = {i: v for i, v in enumerate(kernel['instructions'])}
    data_memory  = {i: v for i, v in enumerate(kernel['data_mem_raw'])}

    print(f"\n── axelbin loaded: {os.path.basename(axelbin_path)} ──")
    print(f"  num_blocks  : {kernel['num_blocks']}")
    print(f"  blockDim    : {kernel['blockDim']}")
    print(f"  instructions: {kernel['text_words']}")
    print(f"  data words  : {kernel['data_words']}")
    print("  Initial data memory:")
    for i, (raw, signed) in enumerate(zip(kernel['data_mem_raw'], kernel['data_mem'])):
        print(f"    mem[{i}] = {raw:#010x}  ({signed})")

    # ── Init DUT signals ──────────────────────────────────────────────────────
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

    # ── Reset ─────────────────────────────────────────────────────────────────
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    # ── DCR dispatch ──────────────────────────────────────────────────────────
    dut.dcr_write_en.value = 1

    dut.dcr_addr.value = 0b00
    dut.dcr_data.value = kernel['num_blocks']
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.dcr_addr.value = 0b01
    dut.dcr_data.value = kernel['blockDim']
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.dcr_addr.value = 0b10
    dut.dcr_data.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.dcr_write_en.value = 0

    # ── Grab core0 handle once — fail early with a clear message ─────────────
    try:
        _core0    = dut.core_gen[0].core_inst
        _trace_ok = True
    except Exception as e:
        cocotb.log.warning(f"trace: core0 hierarchy failed ({e}), tracing disabled")
        _trace_ok = False

    # ── Wait for kernel completion and collect trace inline ───────────────────
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

    # ── Write CSV ─────────────────────────────────────────────────────────────
    if trace_rows:
        with open(_trace_csv, "w", newline="") as _f:
            _w = csv.DictWriter(_f, fieldnames=trace_rows[0].keys())
            _w.writeheader()
            _w.writerows(trace_rows)
        cocotb.log.info(f"trace: {len(trace_rows)} cycles -> {_trace_csv}")
    else:
        cocotb.log.error("trace: no rows collected")

    # ── Assertions ────────────────────────────────────────────────────────────
    assert dut.kernel_done.value == 1, "Kernel never completed — hung"

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
async def test_pyaxel_runner(dut):
    """
    PyAXEL runtime test runner.
    Not called during normal 'make test' — only via COCOTB_TEST_FILTER=test_pyaxel_runner.

    Environment variables (set by pyaxel/gpu.py):
      PYAXEL_KERNEL    — absolute path to .axelbin file
      PYAXEL_RESULT    — path to write result JSON after kernel_done
      PYAXEL_OVERRIDES — path to data_mem override JSON (optional)
      PYAXEL_TIMEOUT   — max simulation cycles (default 10000)

    Result JSON format:
      { "addr": value, ..., "__cycles__": N }
    """
    import json as _json

    kernel_path    = os.environ.get('PYAXEL_KERNEL')
    result_path    = os.environ.get('PYAXEL_RESULT')
    overrides_path = os.environ.get('PYAXEL_OVERRIDES')
    timeout_cycles = int(os.environ.get('PYAXEL_TIMEOUT', '10000'))

    if not kernel_path or not result_path:
        return  # Not invoked by PyAXEL runtime — skip gracefully

    kernel       = load_axelbin(kernel_path)
    instructions = {i: v for i, v in enumerate(kernel['instructions'])}
    data_memory  = {i: v for i, v in enumerate(kernel['data_mem_raw'])}

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
    dut.dcr_data.value = kernel['num_blocks']
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.dcr_addr.value = 0b01
    dut.dcr_data.value = kernel['blockDim']
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
    result['__cycles__'] = elapsed + 1

    with open(result_path, 'w') as f:
        _json.dump(result, f)