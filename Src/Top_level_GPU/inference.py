import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import os
import json

# ─── Inference config ─────────────────────────────────────────────────────────
FORWARD_HEX  = "../../assembler/builds/phase4_forward.hex"
WEIGHTS_FILE = "../../assembler/builds/weights.json"

X_INPUT = [256, 512, 768, 1024]

NUM_CORES        = 4
THREADS_PER_CORE = 4
TIMEOUT_CYCLES   = 10000
# ──────────────────────────────────────────────────────────────────────────────


def q8_to_real(v):
    if v >= 0x80000000:
        v -= 0x100000000
    return round(v / 256.0, 4)


def load_hex_file(path):
    instructions = {}

    try:
        with open(path, "r") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if line:
                    instructions[i] = int(line, 16)
    except FileNotFoundError:
        raise FileNotFoundError(f"Hex file not found: {path}")

    return instructions


def load_weights(path):
    try:
        with open(path, "r") as f:
            raw = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Weights file not found: {path}. "
            "Run the training/top-level test first to generate weights.json."
        )

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
                addr = safe_int(dut.core_gen[i].core_inst.fetch.req_addr, 0)
                instr = instructions.get(addr, RET_INSTR)
                dut.prog_mem_resp_data[i].value = instr
                resp_valid |= (1 << i)
            except Exception:
                pass

        dut.prog_mem_resp_valid.value = resp_valid


async def data_memory_model(dut, memory):
    """
    data_mem_resp_data is packed:
        logic [NUM_CORES-1:0][31:0] data_mem_resp_data

    Core N gets bits:
        [N*32 + 31 : N*32]

    So cocotb drives the whole response-data port as one integer.
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
                rw   = safe_int(mc.mem_req_rw,   0)  # 1 = read, 0 = write
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

    # num_blocks = 1
    dut.dcr_addr.value = 0b00
    dut.dcr_data.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    # blockDim = 4
    dut.dcr_addr.value = 0b01
    dut.dcr_data.value = 4
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    # start pulse
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
async def test_gpu_inference(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    base = os.path.dirname(__file__)

    instructions = load_hex_file(os.path.join(base, FORWARD_HEX))
    weights      = load_weights(os.path.join(base, WEIGHTS_FILE))
    data_memory  = dict(weights)

    for j in range(4):
        data_memory[16 + j] = X_INPUT[j]

    x_real = [q8_to_real(v) for v in X_INPUT]

    print(f"\n{'=' * 45}")
    print(f"  Input  (Q8 raw) : {X_INPUT}")
    print(f"  Input  (real)   : {x_real}")
    print(f"{'=' * 45}")

    dut.rst.value = 1
    dut.dcr_write_en.value = 0

    dut.prog_mem_resp_valid.value = 0

    for i in range(NUM_CORES):
        # prog_mem_resp_data is still unpacked at top level.
        dut.prog_mem_resp_data[i].value = 0

    dut.data_mem_resp_valid.value = 0

    # data_mem_resp_data is packed, so assign the whole bus at once.
    dut.data_mem_resp_data.value = 0

    cocotb.start_soon(program_memory_model(dut, instructions))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    await reset_gpu(dut)

    cycles = await dispatch_kernel(dut)
    assert cycles != -1, "Inference kernel never completed — hung"

    y_q8 = [data_memory.get(20 + i, 0) for i in range(4)]
    y_real = [q8_to_real(v) for v in y_q8]

    print(f"  Output (Q8 raw) : {y_q8}")
    print(f"  Output (real)   : {y_real}")
    print(f"  Cycles          : {cycles}")
    print(f"{'=' * 45}\n")

    for _ in range(50):
        await RisingEdge(dut.clk)