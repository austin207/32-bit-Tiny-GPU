#!/usr/bin/env python3
"""
Golden-output tests for axelcc: compare compiled .hex instruction words
against a hardcoded expected sequence, catching codegen regressions without
needing a full RTL simulation. Run after `make examples` (build/ +
test_binaries/ must already exist).

Nothing here exercises cocotb/RTL -- functional correctness of these exact
kernels is separately proven by Src/Top_level_GPU/tests/test_axelcc_*.py
and test_phase5_attn_*.py running the compiled .hex through real GPU RTL
simulation. This file only pins down *which instructions* axelcc emits, so
a codegen change that alters output unexpectedly is caught immediately
instead of only showing up as a mystifying RTL test failure (or, worse,
not showing up at all if the change happens to preserve final results by
coincidence).
"""
import os
import sys

TEST_BINARIES = os.path.join(os.path.dirname(__file__), "..", "test_binaries")

OPS = {
    0x00: ("NOP", "N"), 0x01: ("ADD", "R"), 0x02: ("SUB", "R"),
    0x04: ("DIV", "R"), 0x05: ("MOD", "R"), 0x06: ("SHL", "R"),
    0x07: ("SHR", "R"), 0x08: ("AND", "R"), 0x09: ("OR", "R"),
    0x0A: ("XOR", "R"), 0x0B: ("NOT", "R"), 0x0C: ("FMA", "R4"),
    0x0D: ("CMP", "R"), 0x0E: ("BRnzp", "B"), 0x0F: ("LDR", "I"),
    0x10: ("STR", "I"), 0x11: ("CONST", "I"), 0x12: ("RET", "N"),
    0x13: ("IMUL", "R"), 0x14: ("SAR", "R"), 0x15: ("SYNC", "N"),
    0x16: ("DOT4", "R4"), 0x17: ("RELU", "R"), 0x1B: ("EXP8", "R"),
}


def decode(word_hex):
    w = int(word_hex, 16)
    op = (w >> 26) & 0x3F
    name, fmt = OPS.get(op, (f"OP_0x{op:02x}?", "?"))
    if fmt == "N":
        return name
    if fmt == "R":
        rd, rs1, rs2 = (w >> 21) & 0x1F, (w >> 16) & 0x1F, (w >> 11) & 0x1F
        return f"{name} R{rd}, R{rs1}, R{rs2}"
    if fmt == "R4":
        rd, rs1, rs2, rs3 = (w >> 21) & 0x1F, (w >> 16) & 0x1F, (w >> 11) & 0x1F, (w >> 6) & 0x1F
        return f"{name} R{rd}, R{rs1}, R{rs2}, R{rs3}"
    if fmt == "I":
        rd, rs, imm = (w >> 21) & 0x1F, (w >> 16) & 0x1F, w & 0xFFFF
        return f"{name} R{rd}, R{rs}, {hex(imm)}"
    if fmt == "B":
        nzp, sync, br = (w >> 23) & 0x7, (w >> 12) & 0x7FF, w & 0xFFF
        if br & 0x800:
            br -= 0x1000
        return f"{name} {nzp:03b}, sync={sync}, br={br}"
    return f"?0x{w:08x}"


# ── Golden instruction sequences ────────────────────────────────────────
# Captured as the pre-quality-pass baseline. Update deliberately (never by
# blind regeneration) whenever codegen intentionally changes output, and
# re-verify the new sequence by hand before checking it in.
GOLDEN = {
    # Register-reuse rework (step 4 of the compiler quality pass): [12] is
    # now `ADD R20, R20, R1` instead of `ADD R21, R20, R1` -- dst reuses the
    # literal-4 temp's slot (rd == rs1), the same aliasing shape already
    # proven safe by STMT_FOR's loop-increment (codegen.c). Hand-traced
    # instruction-by-instruction against the AST before checking in.
    "relu": [
        "043d0000",  # [ 0] ADD R1, R29, R0
        "3e810000",  # [ 1] LDR R20, R1, 0x0
        "04540000",  # [ 2] ADD R2, R20, R0
        "46800000",  # [ 3] CONST R20, R0, 0x0
        "3402a000",  # [ 4] CMP R0, R2, R20
        "38804004",  # [ 5] BRnzp 001, sync=4, br=4
        "46800000",  # [ 6] CONST R20, R0, 0x0
        "04540000",  # [ 7] ADD R2, R20, R0
        "3b802002",  # [ 8] BRnzp 111, sync=2, br=2
        "00000000",  # [ 9] NOP
        "54000000",  # [10] SYNC
        "46800004",  # [11] CONST R20, R0, 0x4
        "06940800",  # [12] ADD R20, R20, R1   -- rd == rs1 (proven) aliasing
        "40540000",  # [13] STR R2, R20, 0x0
        "48000000",  # [14] RET
    ],
    "test_loopsum": [
        "46800000",  # [ 0] CONST R20, R0, 0x0
        "04340000",  # [ 1] ADD R1, R20, R0
        "46800000",  # [ 2] CONST R20, R0, 0x0
        "04540000",  # [ 3] ADD R2, R20, R0
        "47800001",  # [ 4] CONST R28, R0, 0x1
        "46800004",  # [ 5] CONST R20, R0, 0x4
        "3402a000",  # [ 6] CMP R0, R2, R20
        "39805005",  # [ 7] BRnzp 011, sync=5, br=5
        "06811000",  # [ 8] ADD R20, R1, R2
        "04340000",  # [ 9] ADD R1, R20, R0
        "0442e000",  # [10] ADD R2, R2, R28
        "3bffaffa",  # [11] BRnzp 111, sync=2042, br=-6
        "46800000",  # [12] CONST R20, R0, 0x0
        "40340000",  # [13] STR R1, R20, 0x0
        "48000000",  # [14] RET
    ],
    "test_params": [
        "3c200100",  # [ 0] LDR R1, R0, 0x100
        "3c400101",  # [ 1] LDR R2, R0, 0x101
        "06811000",  # [ 2] ADD R20, R1, R2
        "46a00000",  # [ 3] CONST R21, R0, 0x0
        "42950000",  # [ 4] STR R20, R21, 0x0
        "48000000",  # [ 5] RET
    ],
    # Register-reuse rework: address-expression temps now collapse onto a
    # single reused slot (R20, occasionally R21) instead of climbing R21-R25
    # -- e.g. [19]-[21] alias rd==rs2 repeatedly (`IMUL R20,R4,R20`, then
    # `ADD R20,R1,R20`), a shape not covered by the for-loop-increment
    # precedent alone; empirically proven correct via full RTL regression
    # (attn_scores/softmax/weighted_v/multihead all assert exact numeric
    # results against an independent Python reference).
    "attn_scores": [
        "3c200100",  # [ 0] LDR R1, R0, 0x100
        "3c400101",  # [ 1] LDR R2, R0, 0x101
        "3c600102",  # [ 2] LDR R3, R0, 0x102
        "049d0000",  # [ 3] ADD R4, R29, R0
        "46800000",  # [ 4] CONST R20, R0, 0x0
        "04b40000",  # [ 5] ADD R5, R20, R0
        "47800001",  # [ 6] CONST R28, R0, 0x1
        "46800004",  # [ 7] CONST R20, R0, 0x4
        "3405a000",  # [ 8] CMP R0, R5, R20
        "39823023",  # [ 9] BRnzp 011, sync=35, br=35
        "46800000",  # [10] CONST R20, R0, 0x0
        "04d40000",  # [11] ADD R6, R20, R0
        "46800000",  # [12] CONST R20, R0, 0x0
        "04f40000",  # [13] ADD R7, R20, R0
        "47800001",  # [14] CONST R28, R0, 0x1
        "46800004",  # [15] CONST R20, R0, 0x4
        "3407a000",  # [16] CMP R0, R7, R20
        "39812012",  # [17] BRnzp 011, sync=18, br=18
        "46800004",  # [18] CONST R20, R0, 0x4
        "4e84a000",  # [19] IMUL R20, R4, R20   -- rd == rs2 aliasing
        "0681a000",  # [20] ADD R20, R1, R20    -- rd == rs2 aliasing
        "06943800",  # [21] ADD R20, R20, R7    -- rd == rs1 aliasing
        "3eb40000",  # [22] LDR R21, R20, 0x0
        "05150000",  # [23] ADD R8, R21, R0
        "46800004",  # [24] CONST R20, R0, 0x4
        "4e85a000",  # [25] IMUL R20, R5, R20
        "0682a000",  # [26] ADD R20, R2, R20
        "06943800",  # [27] ADD R20, R20, R7
        "3eb40000",  # [28] LDR R21, R20, 0x0
        "05350000",  # [29] ADD R9, R21, R0
        "4e884800",  # [30] IMUL R20, R8, R9
        "0686a000",  # [31] ADD R20, R6, R20
        "04d40000",  # [32] ADD R6, R20, R0
        "04e7e000",  # [33] ADD R7, R7, R28
        "3bfedfed",  # [34] BRnzp 111, sync=2029, br=-19
        "46800008",  # [35] CONST R20, R0, 0x8
        "5286a000",  # [36] SAR R20, R6, R20
        "46a00004",  # [37] CONST R21, R0, 0x4
        "4ea4a800",  # [38] IMUL R21, R4, R21
        "06a3a800",  # [39] ADD R21, R3, R21
        "06b52800",  # [40] ADD R21, R21, R5
        "42950000",  # [41] STR R20, R21, 0x0
        "04a5e000",  # [42] ADD R5, R5, R28
        "3bfdcfdc",  # [43] BRnzp 111, sync=2012, br=-36
        "48000000",  # [44] RET
    ],
    "test_relu_builtin": [
        "043d0000",  # [0] ADD R1, R29, R0
        "3e810000",  # [1] LDR R20, R1, 0x0
        "04540000",  # [2] ADD R2, R20, R0
        "5e820000",  # [3] RELU R20, R2, R0
        "46a00004",  # [4] CONST R21, R0, 0x4
        "06b50800",  # [5] ADD R21, R21, R1   -- rd == rs1 aliasing
        "42950000",  # [6] STR R20, R21, 0x0
        "48000000",  # [7] RET
    ],
    "test_constfold": [
        "4680000e",  # [0] CONST R20, R0, 0xe    -- 2+3*4 folded to 14
        "04340000",  # [1] ADD R1, R20, R0
        "46800003",  # [2] CONST R20, R0, 0x3    -- inner (1+2) folds to 3
        "0a80a000",  # [3] SUB R20, R0, R20       -- outer negation stays runtime, rd == rs2 aliasing
        "04540000",  # [4] ADD R2, R20, R0
        "46800000",  # [5] CONST R20, R0, 0x0
        "40340000",  # [6] STR R1, R20, 0x0
        "46800001",  # [7] CONST R20, R0, 0x1
        "40540000",  # [8] STR R2, R20, 0x0
        "48000000",  # [9] RET
    ],
    "test_fma_alias": [
        "3c200100",  # [0] LDR R1, R0, 0x100
        "3c400101",  # [1] LDR R2, R0, 0x101
        "3c600102",  # [2] LDR R3, R0, 0x102
        "3c800103",  # [3] LDR R4, R0, 0x103
        "06832000",  # [4] ADD R20, R3, R4
        "32811500",  # [5] FMA R20, R1, R2, R20  -- rd == rs3 (accumulate) aliasing
        "04b40000",  # [6] ADD R5, R20, R0
        "46800000",  # [7] CONST R20, R0, 0x0
        "40b40000",  # [8] STR R5, R20, 0x0
        "48000000",  # [9] RET
    ],
    "test_regreuse_stress": [
        "46800000",  # [ 0] CONST R20, R0, 0x0
        "3eb40000",  # [ 1] LDR R21, R20, 0x0
        "46c00001",  # [ 2] CONST R22, R0, 0x1
        "3ef60000",  # [ 3] LDR R23, R22, 0x0
        "0695b800",  # [ 4] ADD R20, R21, R23
        "46a00002",  # [ 5] CONST R21, R0, 0x2
        "3ed50000",  # [ 6] LDR R22, R21, 0x0
        "0694b000",  # [ 7] ADD R20, R20, R22   -- rd == rs1 aliasing (accumulator)
        "46a00003",  # [ 8] CONST R21, R0, 0x3
        "3ed50000",  # [ 9] LDR R22, R21, 0x0
        "0694b000",  # [10] ADD R20, R20, R22
        "46a00004",  # [11] CONST R21, R0, 0x4
        "3ed50000",  # [12] LDR R22, R21, 0x0
        "0694b000",  # [13] ADD R20, R20, R22
        "46a00005",  # [14] CONST R21, R0, 0x5
        "3ed50000",  # [15] LDR R22, R21, 0x0
        "0694b000",  # [16] ADD R20, R20, R22
        "46a00006",  # [17] CONST R21, R0, 0x6
        "3ed50000",  # [18] LDR R22, R21, 0x0
        "0694b000",  # [19] ADD R20, R20, R22
        "46a00007",  # [20] CONST R21, R0, 0x7
        "3ed50000",  # [21] LDR R22, R21, 0x0
        "0694b000",  # [22] ADD R20, R20, R22
        "46a00008",  # [23] CONST R21, R0, 0x8
        "3ed50000",  # [24] LDR R22, R21, 0x0
        "0694b000",  # [25] ADD R20, R20, R22
        "46a00009",  # [26] CONST R21, R0, 0x9
        "42950000",  # [27] STR R20, R21, 0x0
        "48000000",  # [28] RET
    ],
}


def load_hex(path):
    with open(path) as f:
        return [line.strip() for line in f if line.strip()]


def run():
    failures = 0
    for name, expected in GOLDEN.items():
        path = os.path.join(TEST_BINARIES, f"{name}.hex")
        if not os.path.exists(path):
            print(f"FAIL {name}: {path} not found (did `make examples` run?)")
            failures += 1
            continue

        got = load_hex(path)
        if got == expected:
            print(f"PASS {name}: {len(got)} instructions match")
            continue

        failures += 1
        print(f"FAIL {name}: instruction sequence mismatch")
        n = max(len(got), len(expected))
        for i in range(n):
            g = got[i] if i < len(got) else None
            e = expected[i] if i < len(expected) else None
            if g == e:
                continue
            g_dis = decode(g) if g else "<missing>"
            e_dis = decode(e) if e else "<missing>"
            print(f"  [{i:2d}] expected: {e} ({e_dis})")
            print(f"       got:      {g} ({g_dis})")

    print()
    if failures:
        print(f"GOLDEN: {len(GOLDEN) - failures}/{len(GOLDEN)} passed, {failures} FAILED")
        return 1
    print(f"GOLDEN: {len(GOLDEN)}/{len(GOLDEN)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
