(* syn_dont_touch = 1 *) module alu (
    input logic [31:0] operand1,
    input logic [31:0] operand2,
    input logic [31:0] operand3, 
    input logic [5:0] op_select,
    output logic [31:0] result,
    output logic [2:0] nzp_flag
);

logic signed [15:0] dot_p0, dot_p1, dot_p2, dot_p3;
assign dot_p0 = $signed(operand1[7:0])   * $signed(operand2[7:0]);
assign dot_p1 = $signed(operand1[15:8])  * $signed(operand2[15:8]);
assign dot_p2 = $signed(operand1[23:16]) * $signed(operand2[23:16]);
assign dot_p3 = $signed(operand1[31:24]) * $signed(operand2[31:24]);

always_comb begin
    result = 32'b0; 
    nzp_flag = 3'b000;

    case (op_select)
       6'h01 : result = operand1 + operand2; //ADD
       6'h02 : result = operand1 - operand2; //SUB
       6'h03 : result = operand1 * operand2; //MUL
       6'h04 : result = operand1 / operand2; //DIV
       6'h05 : result = operand1 % operand2; //MOD
       6'h06 : result = operand1 << operand2; //SHL
       6'h07 : result = operand1 >> operand2; //SHR
       6'h08 : result = operand1 & operand2; //AND
       6'h09 : result = operand1 | operand2; //OR
       6'h0A : result = operand1 ^ operand2; //XOR
       6'h0B : result = ~operand1; //NOT
       6'h0C : result = (operand1 * operand2) + operand3; //FMA
       6'h0D : begin
            result = 32'b0;
            if ($signed(operand1) == $signed(operand2))
                nzp_flag = 3'b010;
            else if ($signed(operand1) > $signed(operand2))
                nzp_flag = 3'b001;
            else
                nzp_flag = 3'b100;
        end //CMP
       6'h13 : result = $signed(operand1) * $signed(operand2); // IMUL
       6'h14 : result = $signed(operand1) >>> operand2; // SAR
       6'h16 : result = $signed(operand3) + dot_p0 + dot_p1 + dot_p2 + dot_p3; //DOT4
       6'h17 : result = ($signed(operand1) < 0) ? 32'b0 : operand1; //RELU
       6'h18 : begin
        if ($signed(operand1) > 127)       result = 32'd127;
        else if ($signed(operand1) < -128) result = -32'd128;
        else                               result = operand1;
       end //CLAMP
       6'h19 : result = ($signed(operand1) >= $signed(operand2)) ? operand1 : operand2; //MAX
       6'h1A : result = ($signed(operand1) <= $signed(operand2)) ? operand1 : operand2; //MIN
       6'h1B : result = {24'b0, exp8_result}; //EXP8
       default:; //default vaule is already set to zero at top 
    endcase
end

// ── EXP8 LUT ─────────────────────────────────────────────────────────────────
// Input:  operand1[7:0] as signed INT8 (2's complement)
// Output: round(min(127, max(0, exp(x/64.0) * 127)))
// Q6 scaling: INT8 range [-128,127] maps to real range [-2.0, 1.984]
// For x >= 0 (8'h00..8'h7F): exp >= 1.0, output saturates to 127
// For x <  0 (8'h80..8'hFF): output decreases monotonically from 125 to 17
logic [7:0] exp8_result;
always_comb begin
    case (operand1[7:0])
        8'h80: exp8_result = 8'd 17; // x=-128
        8'h81: exp8_result = 8'd 17; // x=-127
        8'h82: exp8_result = 8'd 18; // x=-126
        8'h83: exp8_result = 8'd 18; // x=-125
        8'h84: exp8_result = 8'd 18; // x=-124
        8'h85: exp8_result = 8'd 19; // x=-123
        8'h86: exp8_result = 8'd 19; // x=-122
        8'h87: exp8_result = 8'd 19; // x=-121
        8'h88: exp8_result = 8'd 19; // x=-120
        8'h89: exp8_result = 8'd 20; // x=-119
        8'h8A: exp8_result = 8'd 20; // x=-118
        8'h8B: exp8_result = 8'd 20; // x=-117
        8'h8C: exp8_result = 8'd 21; // x=-116
        8'h8D: exp8_result = 8'd 21; // x=-115
        8'h8E: exp8_result = 8'd 21; // x=-114
        8'h8F: exp8_result = 8'd 22; // x=-113
        8'h90: exp8_result = 8'd 22; // x=-112
        8'h91: exp8_result = 8'd 22; // x=-111
        8'h92: exp8_result = 8'd 23; // x=-110
        8'h93: exp8_result = 8'd 23; // x=-109
        8'h94: exp8_result = 8'd 23; // x=-108
        8'h95: exp8_result = 8'd 24; // x=-107
        8'h96: exp8_result = 8'd 24; // x=-106
        8'h97: exp8_result = 8'd 25; // x=-105
        8'h98: exp8_result = 8'd 25; // x=-104
        8'h99: exp8_result = 8'd 25; // x=-103
        8'h9A: exp8_result = 8'd 26; // x=-102
        8'h9B: exp8_result = 8'd 26; // x=-101
        8'h9C: exp8_result = 8'd 27; // x=-100
        8'h9D: exp8_result = 8'd 27; // x= -99
        8'h9E: exp8_result = 8'd 27; // x= -98
        8'h9F: exp8_result = 8'd 28; // x= -97
        8'hA0: exp8_result = 8'd 28; // x= -96
        8'hA1: exp8_result = 8'd 29; // x= -95
        8'hA2: exp8_result = 8'd 29; // x= -94
        8'hA3: exp8_result = 8'd 30; // x= -93
        8'hA4: exp8_result = 8'd 30; // x= -92
        8'hA5: exp8_result = 8'd 31; // x= -91
        8'hA6: exp8_result = 8'd 31; // x= -90
        8'hA7: exp8_result = 8'd 32; // x= -89
        8'hA8: exp8_result = 8'd 32; // x= -88
        8'hA9: exp8_result = 8'd 33; // x= -87
        8'hAA: exp8_result = 8'd 33; // x= -86
        8'hAB: exp8_result = 8'd 34; // x= -85
        8'hAC: exp8_result = 8'd 34; // x= -84
        8'hAD: exp8_result = 8'd 35; // x= -83
        8'hAE: exp8_result = 8'd 35; // x= -82
        8'hAF: exp8_result = 8'd 36; // x= -81
        8'hB0: exp8_result = 8'd 36; // x= -80
        8'hB1: exp8_result = 8'd 37; // x= -79
        8'hB2: exp8_result = 8'd 38; // x= -78
        8'hB3: exp8_result = 8'd 38; // x= -77
        8'hB4: exp8_result = 8'd 39; // x= -76
        8'hB5: exp8_result = 8'd 39; // x= -75
        8'hB6: exp8_result = 8'd 40; // x= -74
        8'hB7: exp8_result = 8'd 41; // x= -73
        8'hB8: exp8_result = 8'd 41; // x= -72
        8'hB9: exp8_result = 8'd 42; // x= -71
        8'hBA: exp8_result = 8'd 43; // x= -70
        8'hBB: exp8_result = 8'd 43; // x= -69
        8'hBC: exp8_result = 8'd 44; // x= -68
        8'hBD: exp8_result = 8'd 45; // x= -67
        8'hBE: exp8_result = 8'd 45; // x= -66
        8'hBF: exp8_result = 8'd 46; // x= -65
        8'hC0: exp8_result = 8'd 47; // x= -64
        8'hC1: exp8_result = 8'd 47; // x= -63
        8'hC2: exp8_result = 8'd 48; // x= -62
        8'hC3: exp8_result = 8'd 49; // x= -61
        8'hC4: exp8_result = 8'd 50; // x= -60
        8'hC5: exp8_result = 8'd 51; // x= -59
        8'hC6: exp8_result = 8'd 51; // x= -58
        8'hC7: exp8_result = 8'd 52; // x= -57
        8'hC8: exp8_result = 8'd 53; // x= -56
        8'hC9: exp8_result = 8'd 54; // x= -55
        8'hCA: exp8_result = 8'd 55; // x= -54
        8'hCB: exp8_result = 8'd 55; // x= -53
        8'hCC: exp8_result = 8'd 56; // x= -52
        8'hCD: exp8_result = 8'd 57; // x= -51
        8'hCE: exp8_result = 8'd 58; // x= -50
        8'hCF: exp8_result = 8'd 59; // x= -49
        8'hD0: exp8_result = 8'd 60; // x= -48
        8'hD1: exp8_result = 8'd 61; // x= -47
        8'hD2: exp8_result = 8'd 62; // x= -46
        8'hD3: exp8_result = 8'd 63; // x= -45
        8'hD4: exp8_result = 8'd 64; // x= -44
        8'hD5: exp8_result = 8'd 65; // x= -43
        8'hD6: exp8_result = 8'd 66; // x= -42
        8'hD7: exp8_result = 8'd 67; // x= -41
        8'hD8: exp8_result = 8'd 68; // x= -40
        8'hD9: exp8_result = 8'd 69; // x= -39
        8'hDA: exp8_result = 8'd 70; // x= -38
        8'hDB: exp8_result = 8'd 71; // x= -37
        8'hDC: exp8_result = 8'd 72; // x= -36
        8'hDD: exp8_result = 8'd 74; // x= -35
        8'hDE: exp8_result = 8'd 75; // x= -34
        8'hDF: exp8_result = 8'd 76; // x= -33
        8'hE0: exp8_result = 8'd 77; // x= -32
        8'hE1: exp8_result = 8'd 78; // x= -31
        8'hE2: exp8_result = 8'd 79; // x= -30
        8'hE3: exp8_result = 8'd 81; // x= -29
        8'hE4: exp8_result = 8'd 82; // x= -28
        8'hE5: exp8_result = 8'd 83; // x= -27
        8'hE6: exp8_result = 8'd 85; // x= -26
        8'hE7: exp8_result = 8'd 86; // x= -25
        8'hE8: exp8_result = 8'd 87; // x= -24
        8'hE9: exp8_result = 8'd 89; // x= -23
        8'hEA: exp8_result = 8'd 90; // x= -22
        8'hEB: exp8_result = 8'd 91; // x= -21
        8'hEC: exp8_result = 8'd 93; // x= -20
        8'hED: exp8_result = 8'd 94; // x= -19
        8'hEE: exp8_result = 8'd 96; // x= -18
        8'hEF: exp8_result = 8'd 97; // x= -17
        8'hF0: exp8_result = 8'd 99; // x= -16
        8'hF1: exp8_result = 8'd100; // x= -15
        8'hF2: exp8_result = 8'd102; // x= -14
        8'hF3: exp8_result = 8'd104; // x= -13
        8'hF4: exp8_result = 8'd105; // x= -12
        8'hF5: exp8_result = 8'd107; // x= -11
        8'hF6: exp8_result = 8'd109; // x= -10
        8'hF7: exp8_result = 8'd110; // x=  -9
        8'hF8: exp8_result = 8'd112; // x=  -8
        8'hF9: exp8_result = 8'd114; // x=  -7
        8'hFA: exp8_result = 8'd116; // x=  -6
        8'hFB: exp8_result = 8'd117; // x=  -5
        8'hFC: exp8_result = 8'd119; // x=  -4
        8'hFD: exp8_result = 8'd121; // x=  -3
        8'hFE: exp8_result = 8'd123; // x=  -2
        8'hFF: exp8_result = 8'd125; // x=  -1
        default: exp8_result = 8'd127; // x >= 0: saturate
    endcase
end
    
endmodule