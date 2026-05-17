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

async def program_memory_model(dut, instructions):
    """Simulates program memory using correct packed signal handling"""
    RET_INSTR = 0x48000000
    NUM_CORES = 4
    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        try:
            req_valid = int(dut.prog_mem_req_valid.value)
            resp_valid = 0
            for i in range(NUM_CORES):
                if (req_valid >> i) & 1:
                    addr = int(dut.prog_mem_req_addr[i].value)
                    instr = instructions.get(addr, RET_INSTR)
                    dut.prog_mem_resp_data[i].value = instr
                    resp_valid |= (1 << i)
            dut.prog_mem_resp_valid.value = resp_valid
        except Exception as e:
            pass

async def data_memory_model(dut, memory):
    """Simulates data memory using correct packed signal handling"""
    TOTAL_THREADS = 16
    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        try:
            req_valid = int(dut.data_mem_req_valid.value)
            req_rw    = int(dut.data_mem_req_rw.value)
            resp_valid = 0
            for i in range(TOTAL_THREADS):
                if (req_valid >> i) & 1:
                    addr = int(dut.data_mem_req_addr[i].value)
                    rw   = (req_rw >> i) & 1
                    data = int(dut.data_mem_req_data[i].value)
                    if rw == 0:  # write STR
                        memory[addr] = data
                        print(f"  Thread {i}: STR -> mem[{addr}] = {data}")
                        resp_valid |= (1 << i)
                    else:        # read LDR
                        val = memory.get(addr, 0)
                        dut.data_mem_resp_data[i].value = val
                        resp_valid |= (1 << i)
            dut.data_mem_resp_valid.value = resp_valid
        except Exception as e:
            pass

@cocotb.test()
async def test_gpu_axel_program(dut):
    """Run AXEL-compiled vector_add program and capture results"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    # Load AXEL compiled hex file
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

    # Start memory models FIRST before any signals change
    cocotb.start_soon(program_memory_model(dut, instructions))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    # Reset for 3 cycles
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    # Configure DCR — write num_blocks = 1
    dut.dcr_write_en.value = 1
    dut.dcr_addr.value = 0b00
    dut.dcr_data.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    # Configure DCR — write blockDim = 4
    dut.dcr_addr.value = 0b01
    dut.dcr_data.value = 4
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    # Trigger start — keep high for 2 cycles to ensure dispatcher sees it
    dut.dcr_addr.value = 0b10
    dut.dcr_data.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.dcr_write_en.value = 0

    # Wait for kernel_done or timeout
    timeout = 1000
    for cycle in range(timeout):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            cocotb.log.info(f"GPU completed in {cycle + 1} cycles")
            break

    assert dut.kernel_done.value == 1, f"GPU timed out after {timeout} cycles"

    # Wait for any pending memory writes
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

    cocotb.log.info("AXEL program executed successfully")

    # Extra cycles for waveform capture
    for _ in range(50):
        await RisingEdge(dut.clk)