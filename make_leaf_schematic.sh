#!/usr/bin/env bash
set -euo pipefail

TOP="${1:-}"

if [ -z "$TOP" ]; then
    echo "Usage: ./make_leaf_schematic.sh <module|all>"
    echo "Example: ./make_leaf_schematic.sh pc"
    echo "Example: ./make_leaf_schematic.sh all"
    exit 1
fi

command -v yosys >/dev/null 2>&1 || {
    echo "ERROR: yosys not found"
    exit 1
}

command -v netlistsvg >/dev/null 2>&1 || {
    echo "ERROR: netlistsvg not found"
    exit 1
}

command -v sv2v >/dev/null 2>&1 || {
    echo "ERROR: sv2v not found"
    exit 1
}

command -v node >/dev/null 2>&1 || {
    echo "ERROR: node not found"
    exit 1
}

# ── Output folders ────────────────────────────────────────────────────────────
ROOT_DIR="schematics"
SVG_DIR="$ROOT_DIR/svg"
JSON_DIR="$ROOT_DIR/json"
LOG_DIR="$ROOT_DIR/logs"
SV2V_DIR="$ROOT_DIR/sv2v"

mkdir -p "$SVG_DIR"
mkdir -p "$JSON_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$SV2V_DIR"

COMMON_FILES="
Src/pc/pc.sv
Src/alu/alu.sv
Src/decoder/decoder.sv
Src/dispatcher/dispatcher.sv
Src/fetcher/fetcher.sv
Src/lsu/lsu.sv
Src/memory_controller/mem_controller.sv
Src/registers/register_file.sv
Src/scheduler/scheduler.sv
Src/device_control_register/dcr.sv
Src/warp_stack/warp_stack.sv
"

run_netlistsvg() {
    local JSON="$1"
    local SVG="$2"

    # Large modules such as registers/core/gpu can overflow Node's default stack.
    node --stack-size=65500 "$(command -v netlistsvg)" "$JSON" -o "$SVG"
}

print_tail() {
    local FILE="$1"

    if [ -f "$FILE" ]; then
        echo
        echo "---- Last 40 lines of $FILE ----"
        tail -n 40 "$FILE"
        echo "--------------------------------"
        echo
    fi
}

generate_schematic() {
    local MOD="$1"
    local TOPMOD="$1"
    local OUT="$1"
    local FILES=""

    case "$MOD" in
        pc)
            TOPMOD="pc"
            OUT="pc"
            FILES="Src/pc/pc.sv"
            ;;

        alu)
            TOPMOD="alu"
            OUT="alu"
            FILES="Src/alu/alu.sv"
            ;;

        decoder)
            TOPMOD="decoder"
            OUT="decoder"
            FILES="Src/decoder/decoder.sv"
            ;;

        dispatcher)
            TOPMOD="dispatcher"
            OUT="dispatcher"
            FILES="Src/dispatcher/dispatcher.sv"
            ;;

        fetcher)
            TOPMOD="fetcher"
            OUT="fetcher"
            FILES="Src/fetcher/fetcher.sv"
            ;;

        lsu)
            TOPMOD="lsu"
            OUT="lsu"
            FILES="Src/lsu/lsu.sv"
            ;;

        mem_controller|memory_controller)
            TOPMOD="mem_controller"
            OUT="memory_controller"
            FILES="Src/memory_controller/mem_controller.sv"
            ;;

        registers|register_file)
            TOPMOD="registers"
            OUT="registers"
            FILES="Src/registers/register_file.sv"
            ;;

        scheduler)
            TOPMOD="scheduler"
            OUT="scheduler"
            FILES="Src/scheduler/scheduler.sv"
            ;;

        dcr)
            TOPMOD="dcr"
            OUT="dcr"
            FILES="Src/device_control_register/dcr.sv"
            ;;

        warp_stack)
            TOPMOD="warp_stack"
            OUT="warp_stack"
            FILES="Src/warp_stack/warp_stack.sv"
            ;;

        core)
            TOPMOD="core"
            OUT="core"
            FILES="Src/core/core.sv $COMMON_FILES"
            ;;

        gpu)
            TOPMOD="gpu"
            OUT="gpu"
            FILES="Src/Top_level_GPU/top_level_gpu.sv Src/core/core.sv $COMMON_FILES"
            ;;

        *)
            echo "Unknown module: $MOD"
            return 1
            ;;
    esac

    local SV2V_OUT="$SV2V_DIR/${OUT}_sv2v.v"
    local JSON_OUT="$JSON_DIR/${OUT}.json"
    local SVG_OUT="$SVG_DIR/${OUT}.svg"

    local SV2V_LOG="$LOG_DIR/${OUT}.sv2v.log"
    local YOSYS_LOG="$LOG_DIR/${OUT}.yosys.log"
    local NETLISTSVG_LOG="$LOG_DIR/${OUT}.netlistsvg.log"

    echo "────────────────────────────────────────"
    echo "Generating schematic for: $OUT"
    echo "Top module: $TOPMOD"
    echo "SV2V:        $SV2V_OUT"
    echo "JSON:        $JSON_OUT"
    echo "SVG:         $SVG_OUT"
    echo "Logs:"
    echo "  $SV2V_LOG"
    echo "  $YOSYS_LOG"
    echo "  $NETLISTSVG_LOG"
    echo "────────────────────────────────────────"

    echo "$FILES" > "$LOG_DIR/${OUT}.files.log"

    if ! sv2v $FILES > "$SV2V_OUT" 2> "$SV2V_LOG"; then
        echo "FAILED during sv2v for: $OUT"
        print_tail "$SV2V_LOG"
        return 1
    fi

    if ! yosys -p "read_verilog $SV2V_OUT; prep -top $TOPMOD; write_json $JSON_OUT" > "$YOSYS_LOG" 2>&1; then
        echo "FAILED during Yosys for: $OUT"
        print_tail "$YOSYS_LOG"
        return 1
    fi

    if ! run_netlistsvg "$JSON_OUT" "$SVG_OUT" > "$NETLISTSVG_LOG" 2>&1; then
        echo "FAILED during netlistsvg for: $OUT"
        print_tail "$NETLISTSVG_LOG"
        return 1
    fi

    echo "Generated: $SVG_OUT"
    echo
}

if [ "$TOP" = "all" ]; then
    MODULES=(
        pc
        alu
        decoder
        dispatcher
        fetcher
        lsu
        memory_controller
        registers
        scheduler
        dcr
        warp_stack
        core
        gpu
    )

    FAILED=()

    for MOD in "${MODULES[@]}"; do
        if ! generate_schematic "$MOD"; then
            FAILED+=("$MOD")
            echo "Continuing after failure in: $MOD"
            echo
        fi
    done

    echo
    echo "────────────────────────────────────────"
    echo "Schematic generation summary"
    echo "────────────────────────────────────────"
    echo "SVG folder:  $SVG_DIR"
    echo "JSON folder: $JSON_DIR"
    echo "SV2V folder: $SV2V_DIR"
    echo "Logs folder: $LOG_DIR"
    echo

    if [ "${#FAILED[@]}" -ne 0 ]; then
        echo "Failed modules:"
        printf '  - %s\n' "${FAILED[@]}"
        exit 1
    fi

    echo "All schematics generated successfully."
else
    generate_schematic "$TOP"
fi