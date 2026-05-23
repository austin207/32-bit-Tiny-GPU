module alu (
    input logic [31:0] operand1,
    input logic [31:0] operand2,
    input logic [31:0] operand3, // For operations with 3 operands like FMA
    input logic [5:0] op_select,
    output logic [31:0] result,
    output logic [2:0] nzp_flag
);

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
       6'h0C : result = (operand1 * operand2) + operand3;
       6'h0D : begin
        result = 0;
        nzp_flag = ($signed(operand1) - $signed(operand2)) == 0 ? 3'b010 : ($signed(operand1) - $signed(operand2)) > 0 ? 3'b001 : 3'b100;
       end 
       6'h13 : result = $signed(operand1) * $signed(operand2); // IMUL
       6'h14 : result = $signed(operand1) >>> operand2; // SAR
       
        default:; //default vaule is already set to zero at top 
    endcase
end
    
endmodule