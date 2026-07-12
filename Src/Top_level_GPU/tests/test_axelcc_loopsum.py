import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from .common import init_bus
from .memory_models import program_memory_model, data_memory_model


def load_hex_file(path):
    instructions = {}
    with open(path) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if line:
                instructions[i] = int(line, 16)
    return instructions


@cocotb.test()
async def test_axelcc_loopsum(dut):
    """
    Verify axelcc-compiled for-loop kernel on full Top_level_GPU.
    Diagnostic version: traces branch_en, sync_en, divergence_detected,
    taken_mask, active_mask, current_state alongside PC/instruction.
    """
    hex_path = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "../../../assembler/builds/hex/test_loopsum.hex"
        )
    )

    instructions = load_hex_file(hex_path)
    cocotb.log.info(f"Loaded {len(instructions)} axelcc instructions from {hex_path}")

    data_memory = {}

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.rst.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    dut.dcr_write_en.value = 1
    dut.dcr_addr.value = 0
    dut.dcr_data.value = 1      # num_blocks = 1
    await RisingEdge(dut.clk)
    dut.dcr_addr.value = 1
    dut.dcr_data.value = 1      # blockDim = 1
    await RisingEdge(dut.clk)
    dut.dcr_addr.value = 2
    dut.dcr_data.value = 1      # start
    await RisingEdge(dut.clk)
    dut.dcr_write_en.value = 0

    try:
        core0 = dut.core_gen[0].core_inst
        trace_ok = True
    except Exception as e:
        cocotb.log.warning(f"trace disabled: {e}")
        trace_ok = False

    rows = []
    cycle_count = 0
    MAX_CYCLES = 600  # ~4 iterations x ~45 cycles + tail, with register tracing on

    for _ in range(MAX_CYCLES):
        await RisingEdge(dut.clk)
        cycle_count += 1

        if trace_ok:
            try:
                row = {
                    "cyc": cycle_count,
                    "state": int(core0.current_state.value),
                    "pc": int(core0.active_pc.value),
                    "instr": f"0x{int(core0.instruction.value):08x}",
                    "branch_en": int(core0.branch_en.value),
                    "nzp_en": int(core0.nzp_en.value),
                    "taken_mask": f"{int(core0.taken_mask.value):04b}",
                    "reg_data1_t0": int(core0.reg_data1[0].value),
                    "reg_data2_t0": int(core0.reg_data2[0].value),
                    "alu_result_t0": int(core0.alu_result[0].value),
                    "nzp_result_t0": f"{int(core0.nzp_result[0].value):03b}",
                    "nzp_stored_t0": f"{int(core0.nzp_stored[0].value):03b}",
                    "write_data_t0": int(core0.write_data[0].value),
                    "wb_en": int(core0.write_back_en_sched.value) & int(core0.write_back_en_dec.value),
                    "rd_addr": int(core0.rd_addr.value),
                }
                rows.append(row)
            except Exception as e:
                cocotb.log.warning(f"trace row {cycle_count} failed: {e}")

        if dut.kernel_done.value == 1:
            break
    else:
        cocotb.log.info("=== DIAGNOSTIC TRACE (timeout) ===")
        for r in rows:
            cocotb.log.info(str(r))
        assert False, "TIMEOUT: loopsum kernel did not finish (see trace above)"

    await Timer(1, unit="ns")

    cocotb.log.info("=== DIAGNOSTIC TRACE ===")
    for r in rows:
        cocotb.log.info(str(r))

    got = data_memory.get(0)
    assert got == 6, f"mem[0] = {got}, expected 6"

    cocotb.log.info(f"axelcc loopsum PASSED in {cycle_count} cycles, mem[0]={got}")