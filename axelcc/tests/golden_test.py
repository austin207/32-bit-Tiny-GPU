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
    0x16: ("DOT4", "R4"), 0x17: ("RELU", "R"), 0x18: ("CLAMP", "R"),
    0x1B: ("EXP8", "R"), 0x1C: ("CALL", "B"), 0x1D: ("SRET", "N"),
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
    "test_clamp_builtin": [
        "043d0000",  # [0] ADD R1, R29, R0
        "3e810000",  # [1] LDR R20, R1, 0x0
        "04540000",  # [2] ADD R2, R20, R0
        "62820000",  # [3] CLAMP R20, R2, R0
        "46a00004",  # [4] CONST R21, R0, 0x4
        "06b50800",  # [5] ADD R21, R21, R1   -- rd == rs1 aliasing
        "42950000",  # [6] STR R20, R21, 0x0
        "48000000",  # [7] RET
    ],
    "test_blockidx": [
        "043d0000",  # [0] ADD R1, R29, R0    tid = threadIdx
        "045e0000",  # [1] ADD R2, R30, R0    bid = blockIdx
        "46800004",  # [2] CONST R20, R0, 0x4
        "4e82a000",  # [3] IMUL R20, R2, R20  -- rd == rs2 aliasing
        "06940800",  # [4] ADD R20, R20, R1   -- rd == rs1 aliasing
        "04740000",  # [5] ADD R3, R20, R0
        "40630000",  # [6] STR R3, R3, 0x0
        "48000000",  # [7] RET
    ],
    # First 3-level nested for-loop (row/col/tap) and first param-driven
    # (non-constant) loop bound in this codebase -- both compiled and ran
    # correctly on the first attempt, verified on real RTL by
    # test_dscnn_dwconv.py. Register budget is exactly 19/19 (razor-tight,
    # matching the plan's flagged risk): 12 params (R1-R12) + channel(R13)
    # + channel_in_base(R14) + channel_shift(R15) + row(R16) + col(R17)
    # + acc(R18) + tap(R19).
    #
    # mult_base/shift_base replace the original mult/shift/round_bias
    # scalar params: direct .tflite flatbuffer inspection revealed the real
    # model's conv/depthwise weight tensors use TFLite's per-channel
    # (per-axis) quantization -- one weight scale per output channel, not
    # one per tensor -- so M = in_scale*w_scale[oc]/out_scale genuinely
    # differs by channel within a single invocation. round_bias is derived
    # in-kernel as 1<<(shift-1) rather than a third array (host must never
    # choose shift=0 for any channel). channel_shift is hoisted (read
    # twice per pixel in the unhoisted form); mult is read once per pixel
    # inline since hoisting it too would have pushed the budget to 20/19.
    "dscnn_dwconv": [
        "3c200100",  # [ 0] LDR R1, R0, 0x100
        "3c400101",  # [ 1] LDR R2, R0, 0x101
        "3c600102",  # [ 2] LDR R3, R0, 0x102
        "3c800103",  # [ 3] LDR R4, R0, 0x103
        "3ca00104",  # [ 4] LDR R5, R0, 0x104
        "3cc00105",  # [ 5] LDR R6, R0, 0x105
        "3ce00106",  # [ 6] LDR R7, R0, 0x106
        "3d000107",  # [ 7] LDR R8, R0, 0x107
        "3d200108",  # [ 8] LDR R9, R0, 0x108
        "3d400109",  # [ 9] LDR R10, R0, 0x109
        "3d60010a",  # [10] LDR R11, R0, 0x10a
        "3d80010b",  # [11] LDR R12, R0, 0x10b
        "46800004",  # [12] CONST R20, R0, 0x4
        "4e9ea000",  # [13] IMUL R20, R30, R20
        "0694e800",  # [14] ADD R20, R20, R29
        "05b40000",  # [15] ADD R13, R20, R0                       channel = blockIdx*4+threadIdx
        "4e8d3800",  # [16] IMUL R20, R13, R7
        "4e944000",  # [17] IMUL R20, R20, R8
        "05d40000",  # [18] ADD R14, R20, R0                       channel_in_base
        "068b6800",  # [19] ADD R20, R11, R13
        "3eb40000",  # [20] LDR R21, R20, 0x0
        "05f50000",  # [21] ADD R15, R21, R0                       channel_shift = mem[shift_base+channel]
        "46800000",  # [22] CONST R20, R0, 0x0
        "06140000",  # [23] ADD R16, R20, R0                       row = 0
        "47800001",  # [24] CONST R28, R0, 0x1
        "34102800",  # [25] CMP R0, R16, R5
        "3983b03b",  # [26] BRnzp 011, sync=59, br=59
        "46800000",  # [27] CONST R20, R0, 0x0
        "06340000",  # [28] ADD R17, R20, R0                       col = 0
        "47800001",  # [29] CONST R28, R0, 0x1
        "34113000",  # [30] CMP R0, R17, R6
        "39834034",  # [31] BRnzp 011, sync=52, br=52
        "06846800",  # [32] ADD R20, R4, R13
        "3eb40000",  # [33] LDR R21, R20, 0x0
        "06550000",  # [34] ADD R18, R21, R0                       acc = bias_eff[channel]
        "46800000",  # [35] CONST R20, R0, 0x0
        "06740000",  # [36] ADD R19, R20, R0                       tap = 0
        "47800001",  # [37] CONST R28, R0, 0x1
        "46800009",  # [38] CONST R20, R0, 0x9
        "3413a000",  # [39] CMP R0, R19, R20
        "39817017",  # [40] BRnzp 011, sync=23, br=23
        "06817000",  # [41] ADD R20, R1, R14
        "4eb04800",  # [42] IMUL R21, R16, R9
        "46c00003",  # [43] CONST R22, R0, 0x3
        "12d3b000",  # [44] DIV R22, R19, R22                      kh = tap/3
        "06b5b000",  # [45] ADD R21, R21, R22
        "4eb54000",  # [46] IMUL R21, R21, R8
        "0694a800",  # [47] ADD R20, R20, R21
        "4eb14800",  # [48] IMUL R21, R17, R9
        "46c00003",  # [49] CONST R22, R0, 0x3
        "16d3b000",  # [50] MOD R22, R19, R22
        "06b5b000",  # [51] ADD R21, R21, R22                      kw = tap%3
        "0694a800",  # [52] ADD R20, R20, R21
        "3eb40000",  # [53] LDR R21, R20, 0x0                      input value
        "46c00009",  # [54] CONST R22, R0, 0x9
        "4ecdb000",  # [55] IMUL R22, R13, R22
        "06c3b000",  # [56] ADD R22, R3, R22
        "06d69800",  # [57] ADD R22, R22, R19
        "3ef60000",  # [58] LDR R23, R22, 0x0                      weight value
        "3295bc80",  # [59] FMA R20, R21, R23, R18                 -- rd == rs3 (accumulate) aliasing
        "06540000",  # [60] ADD R18, R20, R0
        "0673e000",  # [61] ADD R19, R19, R28
        "3bfe8fe8",  # [62] BRnzp 111, sync=2024, br=-24
        "068a6800",  # [63] ADD R20, R10, R13
        "3eb40000",  # [64] LDR R21, R20, 0x0                      mult = mem[mult_base+channel]
        "4e92a800",  # [65] IMUL R20, R18, R21                     acc*mult
        "46a00001",  # [66] CONST R21, R0, 0x1
        "46c00001",  # [67] CONST R22, R0, 0x1
        "0acfb000",  # [68] SUB R22, R15, R22                      channel_shift - 1
        "1ab5b000",  # [69] SHL R21, R21, R22                      1 << (channel_shift-1) = round_bias
        "0694a800",  # [70] ADD R20, R20, R21                      + round_bias
        "52947800",  # [71] SAR R20, R20, R15                      >> channel_shift
        "06946000",  # [72] ADD R20, R20, R12                      + out_zp
        "62940000",  # [73] CLAMP R20, R20, R0
        "4ead2800",  # [74] IMUL R21, R13, R5
        "4eb53000",  # [75] IMUL R21, R21, R6                      channel*H_out*W_out
        "06a2a800",  # [76] ADD R21, R2, R21
        "4ed03000",  # [77] IMUL R22, R16, R6
        "06b5b000",  # [78] ADD R21, R21, R22                      row*W_out
        "06b58800",  # [79] ADD R21, R21, R17                      + col
        "42950000",  # [80] STR R20, R21, 0x0
        "0631e000",  # [81] ADD R17, R17, R28                      col++
        "3bfccfcc",  # [82] BRnzp 111, sync=1996, br=-52
        "0610e000",  # [83] ADD R16, R16, R28                      row++
        "3bfc5fc5",  # [84] BRnzp 111, sync=1989, br=-59
        "48000000",  # [85] RET
    ],
    # 1x1 conv as a per-pixel dot4 channel-reduction: 4 planar LDRs packed
    # in-register (AND 0xff + SHL + OR) into dot4's raw-signed-int8-per-lane
    # layout, accumulated against a host-pre-packed weight word per chunk of
    # 4 input channels. Verified on real RTL by test_dscnn_pwconv.py.
    #
    # mult_base/shift_base per-output-channel arrays, same per-channel
    # quantization correction as dscnn_dwconv.axelc above -- both oc_mult
    # and oc_shift hoisted once per thread here (budget allows it: 9
    # params + 7 body vars = 16/19).
    "dscnn_pwconv": [
        "3c200100",  # [  0] LDR R1, R0, 0x100
        "3c400101",  # [  1] LDR R2, R0, 0x101
        "3c600102",  # [  2] LDR R3, R0, 0x102
        "3c800103",  # [  3] LDR R4, R0, 0x103
        "3ca00104",  # [  4] LDR R5, R0, 0x104
        "3cc00105",  # [  5] LDR R6, R0, 0x105
        "3ce00106",  # [  6] LDR R7, R0, 0x106
        "3d000107",  # [  7] LDR R8, R0, 0x107
        "3d200108",  # [  8] LDR R9, R0, 0x108
        "46800004",  # [  9] CONST R20, R0, 0x4
        "4e9ea000",  # [ 10] IMUL R20, R30, R20
        "0694e800",  # [ 11] ADD R20, R20, R29
        "05540000",  # [ 12] ADD R10, R20, R0                      oc = blockIdx*4+threadIdx
        "4e8a2800",  # [ 13] IMUL R20, R10, R5
        "05740000",  # [ 14] ADD R11, R20, R0                      w_oc_base = oc*Cin4
        "06875000",  # [ 15] ADD R20, R7, R10
        "3eb40000",  # [ 16] LDR R21, R20, 0x0
        "05950000",  # [ 17] ADD R12, R21, R0                      oc_mult = mem[mult_base+oc]
        "06885000",  # [ 18] ADD R20, R8, R10
        "3eb40000",  # [ 19] LDR R21, R20, 0x0
        "05b50000",  # [ 20] ADD R13, R21, R0                      oc_shift = mem[shift_base+oc]
        "46800000",  # [ 21] CONST R20, R0, 0x0
        "05d40000",  # [ 22] ADD R14, R20, R0                      pixel = 0
        "47800001",  # [ 23] CONST R28, R0, 0x1
        "340e3000",  # [ 24] CMP R0, R14, R6
        "39851051",  # [ 25] BRnzp 011, sync=81, br=81
        "06845000",  # [ 26] ADD R20, R4, R10
        "3eb40000",  # [ 27] LDR R21, R20, 0x0
        "05f50000",  # [ 28] ADD R15, R21, R0                      acc = bias_eff[oc]
        "46800000",  # [ 29] CONST R20, R0, 0x0
        "06140000",  # [ 30] ADD R16, R20, R0                      chunk = 0
        "47800001",  # [ 31] CONST R28, R0, 0x1
        "34102800",  # [ 32] CMP R0, R16, R5
        "3983a03a",  # [ 33] BRnzp 011, sync=58, br=58
        "46800004",  # [ 34] CONST R20, R0, 0x4
        "4e90a000",  # [ 35] IMUL R20, R16, R20
        "46a00000",  # [ 36] CONST R21, R0, 0x0
        "0694a800",  # [ 37] ADD R20, R20, R21
        "4e943000",  # [ 38] IMUL R20, R20, R6
        "0681a000",  # [ 39] ADD R20, R1, R20
        "06947000",  # [ 40] ADD R20, R20, R14
        "3eb40000",  # [ 41] LDR R21, R20, 0x0                     lane0 input
        "46c000ff",  # [ 42] CONST R22, R0, 0xff
        "2295b000",  # [ 43] AND R20, R21, R22
        "46a00004",  # [ 44] CONST R21, R0, 0x4
        "4eb0a800",  # [ 45] IMUL R21, R16, R21
        "46c00001",  # [ 46] CONST R22, R0, 0x1
        "06b5b000",  # [ 47] ADD R21, R21, R22
        "4eb53000",  # [ 48] IMUL R21, R21, R6
        "06a1a800",  # [ 49] ADD R21, R1, R21
        "06b57000",  # [ 50] ADD R21, R21, R14
        "3ed50000",  # [ 51] LDR R22, R21, 0x0                     lane1 input
        "46e000ff",  # [ 52] CONST R23, R0, 0xff
        "22b6b800",  # [ 53] AND R21, R22, R23
        "46c00008",  # [ 54] CONST R22, R0, 0x8
        "1ab5b000",  # [ 55] SHL R21, R21, R22
        "2694a800",  # [ 56] OR R20, R20, R21
        "46a00004",  # [ 57] CONST R21, R0, 0x4
        "4eb0a800",  # [ 58] IMUL R21, R16, R21
        "46c00002",  # [ 59] CONST R22, R0, 0x2
        "06b5b000",  # [ 60] ADD R21, R21, R22
        "4eb53000",  # [ 61] IMUL R21, R21, R6
        "06a1a800",  # [ 62] ADD R21, R1, R21
        "06b57000",  # [ 63] ADD R21, R21, R14
        "3ed50000",  # [ 64] LDR R22, R21, 0x0                     lane2 input
        "46e000ff",  # [ 65] CONST R23, R0, 0xff
        "22b6b800",  # [ 66] AND R21, R22, R23
        "46c00010",  # [ 67] CONST R22, R0, 0x10
        "1ab5b000",  # [ 68] SHL R21, R21, R22
        "2694a800",  # [ 69] OR R20, R20, R21
        "46a00004",  # [ 70] CONST R21, R0, 0x4
        "4eb0a800",  # [ 71] IMUL R21, R16, R21
        "46c00003",  # [ 72] CONST R22, R0, 0x3
        "06b5b000",  # [ 73] ADD R21, R21, R22
        "4eb53000",  # [ 74] IMUL R21, R21, R6
        "06a1a800",  # [ 75] ADD R21, R1, R21
        "06b57000",  # [ 76] ADD R21, R21, R14
        "3ed50000",  # [ 77] LDR R22, R21, 0x0                     lane3 input
        "46e000ff",  # [ 78] CONST R23, R0, 0xff
        "22b6b800",  # [ 79] AND R21, R22, R23
        "46c00018",  # [ 80] CONST R22, R0, 0x18
        "1ab5b000",  # [ 81] SHL R21, R21, R22
        "2694a800",  # [ 82] OR R20, R20, R21                      packed = 4 lanes
        "06a35800",  # [ 83] ADD R21, R3, R11
        "06b58000",  # [ 84] ADD R21, R21, R16
        "3ed50000",  # [ 85] LDR R22, R21, 0x0                     weight chunk
        "5a94b000",  # [ 86] DOT4 R20, R20, R22, R0
        "068fa000",  # [ 87] ADD R20, R15, R20
        "05f40000",  # [ 88] ADD R15, R20, R0                      acc += dot4(...)
        "0610e000",  # [ 89] ADD R16, R16, R28                     chunk++
        "3bfc6fc6",  # [ 90] BRnzp 111, sync=1990, br=-58
        "4e8f6000",  # [ 91] IMUL R20, R15, R12                    acc*oc_mult
        "46a00001",  # [ 92] CONST R21, R0, 0x1
        "46c00001",  # [ 93] CONST R22, R0, 0x1
        "0acdb000",  # [ 94] SUB R22, R13, R22                     oc_shift - 1
        "1ab5b000",  # [ 95] SHL R21, R21, R22                     1 << (oc_shift-1) = round_bias
        "0694a800",  # [ 96] ADD R20, R20, R21                     + round_bias
        "52946800",  # [ 97] SAR R20, R20, R13                     >> oc_shift
        "06944800",  # [ 98] ADD R20, R20, R9                      + out_zp
        "62940000",  # [ 99] CLAMP R20, R20, R0
        "4eaa3000",  # [100] IMUL R21, R10, R6
        "06a2a800",  # [101] ADD R21, R2, R21
        "06b57000",  # [102] ADD R21, R21, R14                     + pixel
        "42950000",  # [103] STR R20, R21, 0x0
        "05cee000",  # [104] ADD R14, R14, R28                     pixel++
        "3bfaffaf",  # [105] BRnzp 111, sync=1967, br=-81
        "48000000",  # [106] RET
    ],
    # Cin=1 special case of dscnn_dwconv.axelc's tap-flattening idiom (15
    # taps for the 5x3 stem kernel instead of 9), no per-channel input-plane
    # offset since every output channel reads the same single input plane.
    # Verified on real RTL by test_dscnn_stem_conv.py.
    #
    # mult_base/shift_base per-output-channel arrays, same per-channel
    # quantization correction as dscnn_dwconv.axelc above -- both oc_mult
    # and oc_shift hoisted once per thread (budget allows it here too).
    "dscnn_stem_conv": [
        "3c200100",  # [ 0] LDR R1, R0, 0x100
        "3c400101",  # [ 1] LDR R2, R0, 0x101
        "3c600102",  # [ 2] LDR R3, R0, 0x102
        "3c800103",  # [ 3] LDR R4, R0, 0x103
        "3ca00104",  # [ 4] LDR R5, R0, 0x104
        "3cc00105",  # [ 5] LDR R6, R0, 0x105
        "3ce00106",  # [ 6] LDR R7, R0, 0x106
        "3d000107",  # [ 7] LDR R8, R0, 0x107
        "3d200108",  # [ 8] LDR R9, R0, 0x108
        "3d400109",  # [ 9] LDR R10, R0, 0x109
        "3d60010a",  # [10] LDR R11, R0, 0x10a
        "46800004",  # [11] CONST R20, R0, 0x4
        "4e9ea000",  # [12] IMUL R20, R30, R20
        "0694e800",  # [13] ADD R20, R20, R29
        "05940000",  # [14] ADD R12, R20, R0
        "4680000f",  # [15] CONST R20, R0, 0xf                     oc = blockIdx*4+threadIdx
        "4e8ca000",  # [16] IMUL R20, R12, R20
        "05b40000",  # [17] ADD R13, R20, R0
        "06896000",  # [18] ADD R20, R9, R12                       w_oc_base = oc*15
        "3eb40000",  # [19] LDR R21, R20, 0x0
        "05d50000",  # [20] ADD R14, R21, R0                       oc_mult = mem[mult_base+oc]
        "068a6000",  # [21] ADD R20, R10, R12
        "3eb40000",  # [22] LDR R21, R20, 0x0
        "05f50000",  # [23] ADD R15, R21, R0                       oc_shift = mem[shift_base+oc]
        "46800000",  # [24] CONST R20, R0, 0x0
        "06140000",  # [25] ADD R16, R20, R0                       row = 0
        "47800001",  # [26] CONST R28, R0, 0x1
        "34102800",  # [27] CMP R0, R16, R5
        "39836036",  # [28] BRnzp 011, sync=54, br=54
        "46800000",  # [29] CONST R20, R0, 0x0
        "06340000",  # [30] ADD R17, R20, R0                       col = 0
        "47800001",  # [31] CONST R28, R0, 0x1
        "34113000",  # [32] CMP R0, R17, R6
        "3982f02f",  # [33] BRnzp 011, sync=47, br=47
        "06846000",  # [34] ADD R20, R4, R12
        "3eb40000",  # [35] LDR R21, R20, 0x0
        "06550000",  # [36] ADD R18, R21, R0                       acc = bias_eff[oc]
        "46800000",  # [37] CONST R20, R0, 0x0
        "06740000",  # [38] ADD R19, R20, R0                       tap = 0
        "47800001",  # [39] CONST R28, R0, 0x1
        "4680000f",  # [40] CONST R20, R0, 0xf
        "3413a000",  # [41] CMP R0, R19, R20
        "39814014",  # [42] BRnzp 011, sync=20, br=20
        "4e904000",  # [43] IMUL R20, R16, R8
        "46a00003",  # [44] CONST R21, R0, 0x3
        "12b3a800",  # [45] DIV R21, R19, R21
        "0694a800",  # [46] ADD R20, R20, R21                      kh = tap/3
        "4e943800",  # [47] IMUL R20, R20, R7
        "0681a000",  # [48] ADD R20, R1, R20
        "4eb14000",  # [49] IMUL R21, R17, R8
        "46c00003",  # [50] CONST R22, R0, 0x3
        "16d3b000",  # [51] MOD R22, R19, R22
        "06b5b000",  # [52] ADD R21, R21, R22                      kw = tap%3
        "0694a800",  # [53] ADD R20, R20, R21
        "3eb40000",  # [54] LDR R21, R20, 0x0                      input value
        "06c36800",  # [55] ADD R22, R3, R13
        "06d69800",  # [56] ADD R22, R22, R19
        "3ef60000",  # [57] LDR R23, R22, 0x0                      weight value
        "3295bc80",  # [58] FMA R20, R21, R23, R18                 -- rd == rs3 (accumulate) aliasing
        "06540000",  # [59] ADD R18, R20, R0
        "0673e000",  # [60] ADD R19, R19, R28
        "3bfebfeb",  # [61] BRnzp 111, sync=2027, br=-21
        "4e927000",  # [62] IMUL R20, R18, R14                     acc*oc_mult
        "46a00001",  # [63] CONST R21, R0, 0x1
        "46c00001",  # [64] CONST R22, R0, 0x1
        "0acfb000",  # [65] SUB R22, R15, R22                      oc_shift - 1
        "1ab5b000",  # [66] SHL R21, R21, R22                      1 << (oc_shift-1) = round_bias
        "0694a800",  # [67] ADD R20, R20, R21                      + round_bias
        "52947800",  # [68] SAR R20, R20, R15                      >> oc_shift
        "06945800",  # [69] ADD R20, R20, R11                      + out_zp
        "62940000",  # [70] CLAMP R20, R20, R0
        "4eac2800",  # [71] IMUL R21, R12, R5
        "4eb53000",  # [72] IMUL R21, R21, R6                      oc*H_out*W_out
        "06a2a800",  # [73] ADD R21, R2, R21
        "4ed03000",  # [74] IMUL R22, R16, R6
        "06b5b000",  # [75] ADD R21, R21, R22                      row*W_out
        "06b58800",  # [76] ADD R21, R21, R17                      + col
        "42950000",  # [77] STR R20, R21, 0x0
        "0631e000",  # [78] ADD R17, R17, R28                      col++
        "3bfd1fd1",  # [79] BRnzp 111, sync=2001, br=-47
        "0610e000",  # [80] ADD R16, R16, R28                      row++
        "3bfcafca",  # [81] BRnzp 111, sync=1994, br=-54
        "48000000",  # [82] RET
    ],
    # Generalizes attn_softmax.axelc's 4-term hand-unrolled row-max to a
    # real loop (HW=44 in the real model, too many terms to unroll). `if`
    # nested inside `for` was already proven by test_expif.axelc, so this
    # is a straightforward reuse, not new-pattern risk. Verified on real
    # RTL by test_dscnn_maxpool.py.
    "dscnn_maxpool": [
        "3c200100",  # [ 0] LDR R1, R0, 0x100
        "3c400101",  # [ 1] LDR R2, R0, 0x101
        "3c600102",  # [ 2] LDR R3, R0, 0x102
        "46800004",  # [ 3] CONST R20, R0, 0x4
        "4e9ea000",  # [ 4] IMUL R20, R30, R20
        "0694e800",  # [ 5] ADD R20, R20, R29
        "04940000",  # [ 6] ADD R4, R20, R0         channel = blockIdx*4+threadIdx
        "4e841800",  # [ 7] IMUL R20, R4, R3
        "0681a000",  # [ 8] ADD R20, R1, R20
        "04b40000",  # [ 9] ADD R5, R20, R0         base = in_base + channel*HW
        "3e850000",  # [10] LDR R20, R5, 0x0
        "04d40000",  # [11] ADD R6, R20, R0         best = mem[base]
        "46800001",  # [12] CONST R20, R0, 0x1
        "04f40000",  # [13] ADD R7, R20, R0         i = 1
        "47800001",  # [14] CONST R28, R0, 0x1
        "34071800",  # [15] CMP R0, R7, R3
        "3980d00d",  # [16] BRnzp 011, sync=13, br=13
        "06853800",  # [17] ADD R20, R5, R7
        "3eb40000",  # [18] LDR R21, R20, 0x0
        "34153000",  # [19] CMP R0, R21, R6
        "38802002",  # [20] BRnzp 001, sync=2, br=2
        "3b805005",  # [21] BRnzp 111, sync=5, br=5
        "00000000",  # [22] NOP
        "06853800",  # [23] ADD R20, R5, R7
        "3eb40000",  # [24] LDR R21, R20, 0x0
        "04d50000",  # [25] ADD R6, R21, R0         best = mem[base+i]
        "54000000",  # [26] SYNC
        "04e7e000",  # [27] ADD R7, R7, R28         i++
        "3bff3ff3",  # [28] BRnzp 111, sync=2035, br=-13
        "06822000",  # [29] ADD R20, R2, R4
        "40d40000",  # [30] STR R6, R20, 0x0
        "48000000",  # [31] RET
    ],
    # Degenerate HW=1 case of dscnn_pwconv.axelc's dot4 chunking, but with
    # blockDim=1/oc=blockIdx thread mapping instead of blockIdx*4+threadIdx
    # -- the real model's Cout=18 is not a multiple of 4, so the usual
    # mapping doesn't apply here. Verified on real RTL by test_dscnn_fc.py.
    #
    # mult_base/shift_base per-output-channel arrays, same per-channel
    # quantization correction as dscnn_dwconv.axelc above. Not hoisted here
    # (unlike the spatial kernels): each thread only reaches the requant
    # line once, so a single inline mem[] read is already optimal.
    "dscnn_fc": [
        "3c200100",  # [ 0] LDR R1, R0, 0x100
        "3c400101",  # [ 1] LDR R2, R0, 0x101
        "3c600102",  # [ 2] LDR R3, R0, 0x102
        "3c800103",  # [ 3] LDR R4, R0, 0x103
        "3ca00104",  # [ 4] LDR R5, R0, 0x104
        "3cc00105",  # [ 5] LDR R6, R0, 0x105
        "3ce00106",  # [ 6] LDR R7, R0, 0x106
        "3d000107",  # [ 7] LDR R8, R0, 0x107
        "053e0000",  # [ 8] ADD R9, R30, R0                        oc = blockIdx
        "4e892800",  # [ 9] IMUL R20, R9, R5
        "05540000",  # [10] ADD R10, R20, R0                       w_oc_base = oc*Cin4
        "06844800",  # [11] ADD R20, R4, R9
        "3eb40000",  # [12] LDR R21, R20, 0x0
        "05750000",  # [13] ADD R11, R21, R0                       acc = bias_eff[oc]
        "46800000",  # [14] CONST R20, R0, 0x0
        "05940000",  # [15] ADD R12, R20, R0                       chunk = 0
        "47800001",  # [16] CONST R28, R0, 0x1
        "340c2800",  # [17] CMP R0, R12, R5
        "39832032",  # [18] BRnzp 011, sync=50, br=50
        "46800004",  # [19] CONST R20, R0, 0x4
        "4e8ca000",  # [20] IMUL R20, R12, R20
        "0681a000",  # [21] ADD R20, R1, R20
        "46a00000",  # [22] CONST R21, R0, 0x0
        "0694a800",  # [23] ADD R20, R20, R21
        "3eb40000",  # [24] LDR R21, R20, 0x0                      lane0 input
        "46c000ff",  # [25] CONST R22, R0, 0xff
        "2295b000",  # [26] AND R20, R21, R22
        "46a00004",  # [27] CONST R21, R0, 0x4
        "4eaca800",  # [28] IMUL R21, R12, R21
        "06a1a800",  # [29] ADD R21, R1, R21
        "46c00001",  # [30] CONST R22, R0, 0x1
        "06b5b000",  # [31] ADD R21, R21, R22
        "3ed50000",  # [32] LDR R22, R21, 0x0                      lane1 input
        "46e000ff",  # [33] CONST R23, R0, 0xff
        "22b6b800",  # [34] AND R21, R22, R23
        "46c00008",  # [35] CONST R22, R0, 0x8
        "1ab5b000",  # [36] SHL R21, R21, R22
        "2694a800",  # [37] OR R20, R20, R21
        "46a00004",  # [38] CONST R21, R0, 0x4
        "4eaca800",  # [39] IMUL R21, R12, R21
        "06a1a800",  # [40] ADD R21, R1, R21
        "46c00002",  # [41] CONST R22, R0, 0x2
        "06b5b000",  # [42] ADD R21, R21, R22
        "3ed50000",  # [43] LDR R22, R21, 0x0                      lane2 input
        "46e000ff",  # [44] CONST R23, R0, 0xff
        "22b6b800",  # [45] AND R21, R22, R23
        "46c00010",  # [46] CONST R22, R0, 0x10
        "1ab5b000",  # [47] SHL R21, R21, R22
        "2694a800",  # [48] OR R20, R20, R21
        "46a00004",  # [49] CONST R21, R0, 0x4
        "4eaca800",  # [50] IMUL R21, R12, R21
        "06a1a800",  # [51] ADD R21, R1, R21
        "46c00003",  # [52] CONST R22, R0, 0x3
        "06b5b000",  # [53] ADD R21, R21, R22
        "3ed50000",  # [54] LDR R22, R21, 0x0                      lane3 input
        "46e000ff",  # [55] CONST R23, R0, 0xff
        "22b6b800",  # [56] AND R21, R22, R23
        "46c00018",  # [57] CONST R22, R0, 0x18
        "1ab5b000",  # [58] SHL R21, R21, R22
        "2694a800",  # [59] OR R20, R20, R21                       packed = 4 lanes
        "06a35000",  # [60] ADD R21, R3, R10
        "06b56000",  # [61] ADD R21, R21, R12
        "3ed50000",  # [62] LDR R22, R21, 0x0                      weight chunk
        "5a94b000",  # [63] DOT4 R20, R20, R22, R0
        "068ba000",  # [64] ADD R20, R11, R20
        "05740000",  # [65] ADD R11, R20, R0                       acc += dot4(...)
        "058ce000",  # [66] ADD R12, R12, R28                      chunk++
        "3bfcefce",  # [67] BRnzp 111, sync=1998, br=-50
        "06874800",  # [68] ADD R20, R7, R9
        "3eb40000",  # [69] LDR R21, R20, 0x0
        "05b50000",  # [70] ADD R13, R21, R0                       oc_shift = mem[shift_base+oc]
        "06864800",  # [71] ADD R20, R6, R9
        "3eb40000",  # [72] LDR R21, R20, 0x0                      mult = mem[mult_base+oc]
        "4e8ba800",  # [73] IMUL R20, R11, R21                     acc*mult
        "46a00001",  # [74] CONST R21, R0, 0x1
        "46c00001",  # [75] CONST R22, R0, 0x1
        "0acdb000",  # [76] SUB R22, R13, R22                      oc_shift - 1
        "1ab5b000",  # [77] SHL R21, R21, R22                      1 << (oc_shift-1) = round_bias
        "0694a800",  # [78] ADD R20, R20, R21                      + round_bias
        "52946800",  # [79] SAR R20, R20, R13                      >> oc_shift
        "06944000",  # [80] ADD R20, R20, R8                       + out_zp
        "62940000",  # [81] CLAMP R20, R20, R0
        "06a24800",  # [82] ADD R21, R2, R9
        "42950000",  # [83] STR R20, R21, 0x0
        "48000000",  # [84] RET
    ],
    # Generalizes attn_softmax.axelc from N=4 (hand-unrolled, row-parallel)
    # to a real N-length loop over a single vector (blockDim=1). The CLAMP
    # builtin replaces attn_softmax.axelc's explicit if-based floor-clamp
    # (correct here since score-max is always <=0, so only CLAMP's lower
    # bound ever triggers). Verified on real RTL by test_dscnn_softmax.py.
    "dscnn_softmax": [
        "3c200100",  # [ 0] LDR R1, R0, 0x100
        "3c400101",  # [ 1] LDR R2, R0, 0x101
        "3c600102",  # [ 2] LDR R3, R0, 0x102
        "3c800103",  # [ 3] LDR R4, R0, 0x103
        "3ca00104",  # [ 4] LDR R5, R0, 0x104
        "3e810000",  # [ 5] LDR R20, R1, 0x0
        "04d40000",  # [ 6] ADD R6, R20, R0         m = mem[in_base]
        "46800001",  # [ 7] CONST R20, R0, 0x1
        "04f40000",  # [ 8] ADD R7, R20, R0         i = 1
        "47800001",  # [ 9] CONST R28, R0, 0x1
        "34071800",  # [10] CMP R0, R7, R3
        "3980d00d",  # [11] BRnzp 011, sync=13, br=13
        "06813800",  # [12] ADD R20, R1, R7
        "3eb40000",  # [13] LDR R21, R20, 0x0
        "34153000",  # [14] CMP R0, R21, R6
        "38802002",  # [15] BRnzp 001, sync=2, br=2
        "3b805005",  # [16] BRnzp 111, sync=5, br=5
        "00000000",  # [17] NOP
        "06813800",  # [18] ADD R20, R1, R7
        "3eb40000",  # [19] LDR R21, R20, 0x0
        "04d50000",  # [20] ADD R6, R21, R0         m = mem[in_base+i]
        "54000000",  # [21] SYNC
        "04e7e000",  # [22] ADD R7, R7, R28         i++
        "3bff3ff3",  # [23] BRnzp 111, sync=2035, br=-13
        "46800000",  # [24] CONST R20, R0, 0x0
        "05140000",  # [25] ADD R8, R20, R0         sum = 0
        "46800000",  # [26] CONST R20, R0, 0x0
        "05340000",  # [27] ADD R9, R20, R0         j = 0
        "47800001",  # [28] CONST R28, R0, 0x1
        "34091800",  # [29] CMP R0, R9, R3
        "3980f00f",  # [30] BRnzp 011, sync=15, br=15
        "06814800",  # [31] ADD R20, R1, R9
        "3eb40000",  # [32] LDR R21, R20, 0x0
        "0a953000",  # [33] SUB R20, R21, R6         mem[j] - m
        "52942000",  # [34] SAR R20, R20, R4         >> exp_shift
        "62940000",  # [35] CLAMP R20, R20, R0
        "05540000",  # [36] ADD R10, R20, R0         d
        "6e8a0000",  # [37] EXP8 R20, R10, R0
        "05740000",  # [38] ADD R11, R20, R0         e
        "06824800",  # [39] ADD R20, R2, R9
        "41740000",  # [40] STR R11, R20, 0x0
        "06885800",  # [41] ADD R20, R8, R11
        "05140000",  # [42] ADD R8, R20, R0          sum += e
        "0529e000",  # [43] ADD R9, R9, R28          j++
        "3bff1ff1",  # [44] BRnzp 111, sync=2033, br=-15
        "46800000",  # [45] CONST R20, R0, 0x0
        "05940000",  # [46] ADD R12, R20, R0         k = 0
        "47800001",  # [47] CONST R28, R0, 0x1
        "340c1800",  # [48] CMP R0, R12, R3
        "3980c00c",  # [49] BRnzp 011, sync=12, br=12
        "06826000",  # [50] ADD R20, R2, R12
        "3eb40000",  # [51] LDR R21, R20, 0x0
        "05b50000",  # [52] ADD R13, R21, R0         e2 = mem[out_base+k]
        "46800100",  # [53] CONST R20, R0, 0x100
        "4e8da000",  # [54] IMUL R20, R13, R20        e2*256
        "12944000",  # [55] DIV R20, R20, R8          / sum
        "06942800",  # [56] ADD R20, R20, R5          + out_zp
        "06a26000",  # [57] ADD R21, R2, R12
        "42950000",  # [58] STR R20, R21, 0x0
        "058ce000",  # [59] ADD R12, R12, R28         k++
        "3bff4ff4",  # [60] BRnzp 111, sync=2036, br=-12
        "48000000",  # [61] RET
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
    # First use of the func/CALL/SRET subroutine mechanism added this
    # session: a trivial add3(a,b,c) subroutine called twice from the
    # kernel body. Proves the two-pass backpatch (func bodies emitted after
    # the kernel's own RET, CALL offsets patched once every func's start PC
    # is known) and the R14-R19 register-window convention (params in
    # R14/R15/R16, declared local `s` in R17, return value moved through
    # R19) -- hand-traced instruction-by-instruction against the AST
    # before checking in, same discipline as every other golden entry here.
    # CALL at [7] targets [24] (offset 17 = 24-7); CALL at [16] targets the
    # SAME [24] (offset 8 = 24-16) -- one func body, two call sites, no
    # inlining. Verified on real RTL deferred until call_stack.sv/pc.sv's
    # CALL/SRET support lands (see plan task #30) -- this is a codegen-only
    # (no RTL simulation) check, same as every golden test.
    "test_func_basic": [
        "3c200100",  # [ 0] LDR R1, R0, 0x100
        "46800001",  # [ 1] CONST R20, R0, 0x1
        "46a00002",  # [ 2] CONST R21, R0, 0x2
        "46c00003",  # [ 3] CONST R22, R0, 0x3
        "05d40000",  # [ 4] ADD R14, R20, R0             a = 1
        "05f50000",  # [ 5] ADD R15, R21, R0             b = 2
        "06160000",  # [ 6] ADD R16, R22, R0             c = 3
        "73811011",  # [ 7] CALL 111, sync=17, br=17     -> [24]
        "06930000",  # [ 8] ADD R20, R19, R0             copy return value
        "04540000",  # [ 9] ADD R2, R20, R0              x = add3(1,2,3)
        "4680000a",  # [10] CONST R20, R0, 0xa
        "46a00014",  # [11] CONST R21, R0, 0x14
        "46c0001e",  # [12] CONST R22, R0, 0x1e
        "05d40000",  # [13] ADD R14, R20, R0             a = 10
        "05f50000",  # [14] ADD R15, R21, R0             b = 20
        "06160000",  # [15] ADD R16, R22, R0             c = 30
        "73808008",  # [16] CALL 111, sync=8, br=8       -> [24]
        "06930000",  # [17] ADD R20, R19, R0             copy return value
        "04740000",  # [18] ADD R3, R20, R0              y = add3(10,20,30)
        "40410000",  # [19] STR R2, R1, 0x0              mem[base] = x
        "46800001",  # [20] CONST R20, R0, 0x1
        "0681a000",  # [21] ADD R20, R1, R20
        "40740000",  # [22] STR R3, R20, 0x0             mem[base+1] = y
        "48000000",  # [23] RET                          kernel ends; never falls into func body below
        "068e7800",  # [24] ADD R20, R14, R15            a+b -- func add3's body starts here
        "06948000",  # [25] ADD R20, R20, R16            + c
        "06340000",  # [26] ADD R17, R20, R0             s = a+b+c
        "06710000",  # [27] ADD R19, R17, R0             move s into return register
        "74000000",  # [28] SRET
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
