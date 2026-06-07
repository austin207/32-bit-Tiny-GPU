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
        default:; //default vaule is already set to zero at top 
    endcase
end
    
endmodule