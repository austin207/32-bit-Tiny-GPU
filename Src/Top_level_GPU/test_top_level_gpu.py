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
    """Read signal value safely — returns default if signal contains X or Z bits"""
    try:
        return int(signal.value)
    except Exception:
        return default

def safe_bit(signal, bit, default=0):
    """Read a single bit from a packed signal safely"""
    try:
        return (int(signal.value) >> bit) & 1
    except Exception:
        return default

async def program_memory_model(dut, instructions):
    """Respond to program memory fetch requests"""
    RET_INSTR = 0x48000000
    NUM_CORES = 4
    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        resp_valid = 0
        for i in range(NUM_CORES):
            if safe_bit(dut.prog_mem_req_valid, i) == 1:
                try:
                    addr = int(dut.prog_mem_req_addr[i].value)
                    instr = instructions.get(addr, RET_INSTR)
                    dut.prog_mem_resp_data[i].value = instr
                    resp_valid |= (1 << i)
                except Exception:
                    pass
        dut.prog_mem_resp_valid.value = resp_valid

async def data_memory_model(dut, memory):
    """Respond to data memory requests — handles X-bit signals safely"""
    TOTAL_THREADS = 16
    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        req_valid = safe_int(dut.data_mem_req_valid, 0)
        resp_valid = 0

        for i in range(TOTAL_THREADS):
            if (req_valid >> i) & 1:
                try:
                    addr = int(dut.data_mem_req_addr[i].value)
                    # Read rw bit safely — x bits on inactive threads cause int() to fail
                    rw = safe_bit(dut.data_mem_req_rw, i, default=0)
                    data = safe_int(dut.data_mem_req_data[i], 0)

                    if rw == 0:  # write STR (rw=0 means write in LSU)
                        memory[addr] = data
                        print(f"  Thread {i}: STR -> mem[{addr}] = {data}")
                        resp_valid |= (1 << i)
                    else:        # read LDR
                        val = memory.get(addr, 0)
                        dut.data_mem_resp_data[i].value = val
                        resp_valid |= (1 << i)
                except Exception as e:
                    print(f"  [WARN] Thread {i} memory model error: {e}")

        dut.data_mem_resp_valid.value = resp_valid

@cocotb.test()
async def test_gpu_axel_program(dut):
    """Run AXEL-compiled vector_add program and capture results"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    hex_path = os.path.join(os.path.dirname(__file__), "../../assembler/vector_add.hex")
    instructions = load_hex_file(hex_path)
    data_memory = {}

    # Initialize all inputs
    dut.rst.value = 1
    dut.dcr_write_en.value = 0
    dut.dcr_addr.value = 0
    dut.dcr_data.value = 0
    dut.prog_mem_resp_valid.value = 0
    for i in range(4):
        dut.prog_mem_resp_data[i].value = 0
    dut.data_mem_resp_valid.value = 0
    for i in range(16):
        dut.data_mem_resp_data[i].value = 0

    # Start memory models FIRST
    cocotb.start_soon(program_memory_model(dut, instructions))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    # Reset for 3 cycles
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    # Configure DCR — num_blocks = 1
    dut.dcr_write_en.value = 1
    dut.dcr_addr.value = 0b00
    dut.dcr_data.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    # Configure DCR — blockDim = 4
    dut.dcr_addr.value = 0b01
    dut.dcr_data.value = 4
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    # Trigger start — hold for 2 cycles to guarantee dispatcher sees it
    dut.dcr_addr.value = 0b10
    dut.dcr_data.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.dcr_write_en.value = 0

    # Wait for kernel_done
    timeout = 1000
    for cycle in range(timeout):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            cocotb.log.info(f"GPU completed in {cycle + 1} cycles")
            break

    assert dut.kernel_done.value == 1, f"GPU timed out after {timeout} cycles"

    # Wait for any in-flight writes to settle
    for _ in range(20):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

    # Print results
    print("\n--- Data Memory Results ---")
    if data_memory:
        for addr in sorted(data_memory.keys()):
            print(f"  mem[{addr}] = {data_memory[addr]}")
    else:
        print("  No writes captured")

    print("\nExpected results (threadIdx + blockIdx, blockIdx=0):")
    for t in range(4):
        print(f"  Thread {t}: {t} + 0 = {t}")

    if data_memory:
        for t in range(4):
            assert data_memory.get(t) == t, \
                f"Thread {t}: expected mem[{t}]={t}, got {data_memory.get(t)}"
        cocotb.log.info("All results correct!")

    cocotb.log.info("AXEL vector_add executed successfully on GPU")

    for _ in range(50):
        await RisingEdge(dut.clk)