(* syn_dont_touch = 1 *) module alu (
	operand1,
	operand2,
	operand3,
	op_select,
	result,
	nzp_flag
);
	reg _sv2v_0;
	input wire [31:0] operand1;
	input wire [31:0] operand2;
	input wire [31:0] operand3;
	input wire [5:0] op_select;
	output reg [31:0] result;
	output reg [2:0] nzp_flag;
	always @(*) begin
		if (_sv2v_0)
			;
		result = 32'b00000000000000000000000000000000;
		nzp_flag = 3'b000;
		case (op_select)
			6'h01: result = operand1 + operand2;
			6'h02: result = operand1 - operand2;
			6'h03: result = operand1 * operand2;
			6'h04: result = operand1 / operand2;
			6'h05: result = operand1 % operand2;
			6'h06: result = operand1 << operand2;
			6'h07: result = operand1 >> operand2;
			6'h08: result = operand1 & operand2;
			6'h09: result = operand1 | operand2;
			6'h0a: result = operand1 ^ operand2;
			6'h0b: result = ~operand1;
			6'h0c: result = (operand1 * operand2) + operand3;
			6'h0d: begin
				result = 0;
				nzp_flag = (($signed(operand1) - $signed(operand2)) == 0 ? 3'b010 : (($signed(operand1) - $signed(operand2)) > 0 ? 3'b001 : 3'b100));
			end
			6'h13: result = $signed(operand1) * $signed(operand2);
			6'h14: result = $signed(operand1) >>> operand2;
			default:
				;
		endcase
	end
	initial _sv2v_0 = 0;
endmodule
