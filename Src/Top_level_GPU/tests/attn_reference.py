# Transcribed directly from alu.sv's EXP8 LUT (op 0x1B): operand1[7:0] as
# signed INT8 in Q6 (x/64.0), x in [-128,-1] -> table below, x>=0 -> 127
# (saturates). This is the same table the RTL uses, not a re-derivation of
# it, so comparing against it is a real independent check of the *kernel's*
# integer pipeline (addressing, rowmax, Q8->Q6 rescale, clamp, DIV
# normalization), not of the LUT's own math.
_EXP8_LUT = {
    -128: 17, -127: 17, -126: 18, -125: 18, -124: 18, -123: 19, -122: 19,
    -121: 19, -120: 19, -119: 20, -118: 20, -117: 20, -116: 21, -115: 21,
    -114: 21, -113: 22, -112: 22, -111: 22, -110: 23, -109: 23, -108: 23,
    -107: 24, -106: 24, -105: 25, -104: 25, -103: 25, -102: 26, -101: 26,
    -100: 27, -99: 27, -98: 27, -97: 28, -96: 28, -95: 29, -94: 29, -93: 30,
    -92: 30, -91: 31, -90: 31, -89: 32, -88: 32, -87: 33, -86: 33, -85: 34,
    -84: 34, -83: 35, -82: 35, -81: 36, -80: 36, -79: 37, -78: 38, -77: 38,
    -76: 39, -75: 39, -74: 40, -73: 41, -72: 41, -71: 42, -70: 43, -69: 43,
    -68: 44, -67: 45, -66: 45, -65: 46, -64: 47, -63: 47, -62: 48, -61: 49,
    -60: 50, -59: 51, -58: 51, -57: 52, -56: 53, -55: 54, -54: 55, -53: 55,
    -52: 56, -51: 57, -50: 58, -49: 59, -48: 60, -47: 61, -46: 62, -45: 63,
    -44: 64, -43: 65, -42: 66, -41: 67, -40: 68, -39: 69, -38: 70, -37: 71,
    -36: 72, -35: 74, -34: 75, -33: 76, -32: 77, -31: 78, -30: 79, -29: 81,
    -28: 82, -27: 83, -26: 85, -25: 86, -24: 87, -23: 89, -22: 90, -21: 91,
    -20: 93, -19: 94, -18: 96, -17: 97, -16: 99, -15: 100, -14: 102,
    -13: 104, -12: 105, -11: 107, -10: 109, -9: 110, -8: 112, -7: 114,
    -6: 116, -5: 117, -4: 119, -3: 121, -2: 123, -1: 125,
}


def exp8(x):
    if x >= 0:
        return 127
    return _EXP8_LUT[max(x, -128)]


def reference_attention(Q_real, K_real, V_real):
    n = len(Q_real)
    scores_q8 = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            raw = sum(Q_real[i][k] * 256 * (K_real[j][k] * 256) for k in range(n))
            scores_q8[i][j] = raw >> 8

    weights_q8 = [[0] * n for _ in range(n)]
    for i in range(n):
        m = max(scores_q8[i])
        exps = []
        for j in range(n):
            d = (scores_q8[i][j] - m) >> 2
            if d < -128:
                d = -128
            exps.append(exp8(d))
        s = sum(exps)
        for j in range(n):
            weights_q8[i][j] = (exps[j] * 256) // s

    out_q8 = [[0] * n for _ in range(n)]
    for i in range(n):
        for k in range(n):
            raw = sum(weights_q8[i][j] * (V_real[j][k] * 256) for j in range(n))
            out_q8[i][k] = raw >> 8

    return scores_q8, weights_q8, out_q8
