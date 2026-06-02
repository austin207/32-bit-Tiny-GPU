(* syn_dont_touch = 1 *) module pc (
	clk,
	rst,
	block_rst,
	pc_en,
	branch_en,
	branch_offset,
	nzp_en,
	nzp_flag,
	nzp_mask,
	pc_out,
	nzp_out
);
	input wire clk;
	input wire rst;
	input wire block_rst;
	input wire pc_en;
	input wire branch_en;
	input wire [11:0] branch_offset;
	input wire nzp_en;
	input wire [2:0] nzp_flag;
	input wire [2:0] nzp_mask;
	output reg [31:0] pc_out;
	output wire [2:0] nzp_out;
	reg [2:0] nzp_reg;
	always @(posedge clk or posedge rst)
		if (rst) begin
			pc_out <= 32'b00000000000000000000000000000000;
			nzp_reg <= 3'b000;
		end
		else if (block_rst) begin
			pc_out <= 32'b00000000000000000000000000000000;
			nzp_reg <= 3'b000;
		end
		else begin
			if (nzp_en)
				nzp_reg <= nzp_flag;
			if (pc_en) begin
				if (branch_en && ((nzp_reg & nzp_mask) != 0))
					pc_out <= pc_out + branch_offset;
				else
					pc_out <= pc_out + 1;
			end
		end
	assign nzp_out = nzp_reg;
endmodule
