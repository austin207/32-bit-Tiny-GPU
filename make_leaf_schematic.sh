#!/usr/bin/env bash
set -e

TOP="$1"

if [ -z "$TOP" ]; then
    echo "Usage: ./make_leaf_schematic.sh <module>"
    echo "Example: ./make_leaf_schematic.sh pc"
    exit 1
fi

mkdir -p schematics

case "$TOP" in
    pc)
        FILES="Src/pc/pc.sv"
        ;;
    alu)
        FILES="Src/alu/alu.sv"
        ;;
    decoder)
        FILES="Src/decoder/decoder.sv"
        ;;
    dispatcher)
        FILES="Src/dispatcher/dispatcher.sv"
        ;;
    fetcher)
        FILES="Src/fetcher/fetcher.sv"
        ;;
    lsu)
        FILES="Src/lsu/lsu.sv"
        ;;
    memory_controller)
        FILES="Src/memory_controller/mem_controller.sv"
        ;;
    registers)
        FILES="Src/registers/register_file.sv"
        ;;
    scheduler)
        FILES="Src/scheduler/scheduler.sv"
        ;;
    dcr)
        FILES="Src/device_control_register/dcr.sv"
        ;;
    core)
        FILES="Src/core/core.sv Src/pc/pc.sv Src/alu/alu.sv Src/decoder/decoder.sv Src/dispatcher/dispatcher.sv Src/fetcher/fetcher.sv Src/lsu/lsu.sv Src/memory_controller/mem_controller.sv Src/registers/register_file.sv Src/scheduler/scheduler.sv Src/device_control_register/dcr.sv"
        ;;
    gpu)
        FILES="Src/Top_level_GPU/top_level_gpu.sv Src/core/core.sv Src/pc/pc.sv Src/alu/alu.sv Src/decoder/decoder.sv Src/dispatcher/dispatcher.sv Src/fetcher/fetcher.sv Src/lsu/lsu.sv Src/memory_controller/mem_controller.sv Src/registers/register_file.sv Src/scheduler/scheduler.sv Src/device_control_register/dcr.sv"
        ;;
    *)
        echo "Unknown module: $TOP"
        echo "Valid: pc alu decoder dispatcher fetcher lsu memory_controller registers scheduler dcr core gpu"
        exit 1
        ;;
esac

echo "Generating schematic for: $TOP"
echo "Files: $FILES"

yosys -p "read_verilog -sv $FILES; prep -top $TOP; write_json schematics/$TOP.json"

netlistsvg "schematics/$TOP.json" -o "schematics/$TOP.svg"

echo "Generated: schematics/$TOP.svg"