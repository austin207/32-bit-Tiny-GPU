import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import os
import json
import csv

from tests.common import (
    load_axelbin,
    safe_int,
    safe_bit,
    u32_to_signed,
    reset_gpu,
    init_bus,
    NUM_CORES,
    TIMEOUT_CYCLES,
    SCHED_STATES,
)

from tests.memory_models import (
    program_memory_model,
    data_memory_model,
)


FORWARD_HEX = "../../assembler/builds/hex/phase4_forward.hex"
BACKWARD_HEX = "../../assembler/builds/hex/phase5_weight_update.hex"
WEIGHTS_FILE = "../../assembler/builds/weights.json"
N_EPOCHS = 20

W_INIT = [
    [256, 0, 0, 0],
    [0, 256, 0, 0],
    [0, 0, 256, 0],
    [0, 0, 0, 256],
]

X = [256, 512, 768, 1024]
T = [512, 1024, 1536, 2048]


def q8_to_real(v):
    if v >= 0x80000000:
        v -= 0x100000000
    return v / 256.0


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


async def dispatch_kernel_legacy(dut):
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

    base = os.path.dirname(__file__)
    fwd = load_hex_file(os.path.join(base, FORWARD_HEX))
    bwd = load_hex_file(os.path.join(base, BACKWARD_HEX))
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
        print("Using initial Q8 identity weights")

    for j in range(4):
        data_memory[16 + j] = X[j]

    for i in range(4):
        data_memory[24 + i] = T[i]

    init_bus(dut)

    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    x_real = [q8_to_real(v) for v in X]
    t_real = [q8_to_real(v) for v in T]

    print(f"x (real) = {x_real}")
    print(f"t (real) = {t_real}")

    for epoch in range(N_EPOCHS):
        instructions_ref[0] = fwd
        await reset_gpu(dut)
        await dispatch_kernel_legacy(dut)

        y_q8 = [data_memory.get(20 + i, 0) for i in range(4)]
        y_real = [q8_to_real(v) for v in y_q8]

        instructions_ref[0] = bwd
        await reset_gpu(dut)
        await dispatch_kernel_legacy(dut)

        e_real = [round(y_real[i] - t_real[i], 4) for i in range(4)]
        w_diag = [q8_to_real(data_memory.get(i * 4 + i, 0)) for i in range(4)]

        print(
            f"Epoch {epoch + 1:2d}/{N_EPOCHS} | "
            f"y={[round(v, 2) for v in y_real]} | "
            f"err={e_real} | "
            f"W_diag={[round(v, 4) for v in w_diag]}"
        )

    save_weights(data_memory, wfile)

    print("\n── Final weights ──")
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
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base = os.path.dirname(__file__)
    axelbin_path = os.path.join(
        base,
        "../../assembler/builds/bin/phase6_simt_relu.axelbin",
    )

    trace_csv = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "trace_simt_relu.csv",
    )

    kernel = load_axelbin(axelbin_path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    print(f"\n── axelbin loaded: {os.path.basename(axelbin_path)} ──")
    print(f"  num_blocks  : {kernel['num_blocks']}")
    print(f"  blockDim    : {kernel['blockDim']}")
    print(f"  instructions: {kernel['text_words']}")
    print(f"  data words  : {kernel['data_words']}")

    init_bus(dut)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

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

    try:
        core0 = dut.core_gen[0].core_inst
        trace_ok = True
    except Exception as e:
        cocotb.log.warning(f"trace disabled: {e}")
        trace_ok = False

    trace_rows = []

    for cyc in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        if trace_ok:
            try:
                sched = safe_int(core0.current_state)
                amask = safe_int(core0.active_mask)

                row = {
                    "cycle": cyc + 1,
                    "state": SCHED_STATES.get(sched, str(sched)),
                    "state_num": sched,
                    "active_mask": f"{amask:04b}",
                    "active_pc": safe_int(core0.active_pc),
                    "instruction": f"0x{safe_int(core0.instruction):08x}",
                    "ws_empty": safe_int(core0.ws.stack_empty),
                    "kernel_done": safe_int(dut.kernel_done),
                }

                for j in range(4):
                    row[f"t{j}_active"] = (amask >> j) & 1
                    try:
                        row[f"t{j}_wr_data"] = safe_int(core0.write_data[j])
                    except Exception:
                        row[f"t{j}_wr_data"] = 0

                trace_rows.append(row)

            except Exception as e:
                cocotb.log.warning(f"trace row {cyc} skipped: {e}")

        if dut.kernel_done.value == 1:
            break

    if trace_rows:
        with open(trace_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=trace_rows[0].keys())
            writer.writeheader()
            writer.writerows(trace_rows)

        cocotb.log.info(f"trace: {len(trace_rows)} cycles -> {trace_csv}")

    assert dut.kernel_done.value == 1, "SIMT ReLU kernel hung"

    kc = safe_int(dut.kernel_cycles)
    assert kc > 0, "kernel_cycles is 0"
    assert abs(kc - len(trace_rows)) <= 2, (
        f"kernel_cycles {kc} too far from trace count {len(trace_rows)}"
    )

    assert data_memory.get(4) == 5
    assert data_memory.get(5) == 0
    assert data_memory.get(6) == 8
    assert data_memory.get(7) == 0

    print("\n── SIMT ReLU Results ──")
    print(f"  mem[4] = {data_memory.get(4)}")
    print(f"  mem[5] = {data_memory.get(5)}")
    print(f"  mem[6] = {data_memory.get(6)}")
    print(f"  mem[7] = {data_memory.get(7)}")


@cocotb.test()
async def test_dot4_kernel(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base = os.path.dirname(__file__)
    axelbin_path = os.path.join(
        base,
        "../../assembler/builds/bin/phase7_dot4_test.axelbin",
    )

    kernel = load_axelbin(axelbin_path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    def unpack_int8x4(word):
        lanes = []
        for shift in [0, 8, 16, 24]:
            byte = (word >> shift) & 0xFF
            lanes.append(byte - 256 if byte >= 128 else byte)
        return lanes

    vec_a = unpack_int8x4(data_memory[0])
    vec_b = unpack_int8x4(data_memory[1])
    expected = sum(a * b for a, b in zip(vec_a, vec_b))

    print("\n── Phase 7: DOT4 kernel ──")
    print(f"  vec A = {vec_a}")
    print(f"  vec B = {vec_b}")
    print(f"  golden = {expected}")

    init_bus(dut)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

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

    for _ in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        if dut.kernel_done.value == 1:
            break

    assert dut.kernel_done.value == 1, "DOT4 kernel hung"

    result = u32_to_signed(data_memory.get(2, 0))

    print(f"  hardware result = {result}")
    print(f"  kernel_cycles   = {safe_int(dut.kernel_cycles)}")

    assert result == expected, f"DOT4 expected {expected}, got {result}"


@cocotb.test()
async def test_pyaxel_runner(dut):
    import json as _json

    kernel_path = os.environ.get("PYAXEL_KERNEL")
    result_path = os.environ.get("PYAXEL_RESULT")
    overrides_path = os.environ.get("PYAXEL_OVERRIDES")
    timeout_cycles = int(os.environ.get("PYAXEL_TIMEOUT", "10000"))

    if not kernel_path or not result_path:
        return

    kernel = load_axelbin(kernel_path)
    instructions = {i: v for i, v in enumerate(kernel["instructions"])}
    data_memory = {i: v for i, v in enumerate(kernel["data_mem_raw"])}

    if overrides_path and os.path.isfile(overrides_path):
        with open(overrides_path) as f:
            overrides = _json.load(f)
        data_memory.update({int(k): v for k, v in overrides.items()})

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    init_bus(dut)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

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

    elapsed = 0

    for elapsed in range(timeout_cycles):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        if dut.kernel_done.value == 1:
            break

    assert dut.kernel_done.value == 1, (
        f"pyaxel timed out after {timeout_cycles} cycles"
    )

    result = {str(k): v for k, v in data_memory.items()}
    result["__cycles__"] = elapsed + 1

    with open(result_path, "w") as f:
        _json.dump(result, f)