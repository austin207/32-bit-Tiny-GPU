module decoder (
	instruction,
	opcode,
	rd_addr,
	rs1_addr,
	rs2_addr,
	rs3_addr,
	imm,
	nzp_mask,
	sync_offset,
	branch_offset,
	sync_en,
	ret,
	write_back_en,
	mem_read_en,
	mem_write_en,
	branch_en,
	nzp_en
);
	reg _sv2v_0;
	input wire [31:0] instruction;
	output wire [5:0] opcode;
	output wire [4:0] rd_addr;
	output wire [4:0] rs1_addr;
	output wire [4:0] rs2_addr;
	output wire [4:0] rs3_addr;
	output wire [15:0] imm;
	output wire [2:0] nzp_mask;
	output wire [10:0] sync_offset;
	output wire [11:0] branch_offset;
	output reg sync_en;
	output reg ret;
	output reg write_back_en;
	output reg mem_read_en;
	output reg mem_write_en;
	output reg branch_en;
	output reg nzp_en;
	assign opcode = instruction[31:26];
	assign rd_addr = instruction[25:21];
	assign rs1_addr = instruction[20:16];
	assign rs2_addr = instruction[15:11];
	assign rs3_addr = instruction[10:6];
	assign imm = instruction[15:0];
	assign nzp_mask = instruction[25:23];
	assign sync_offset = instruction[22:12];
	assign branch_offset = instruction[11:0];
	always @(*) begin
		if (_sv2v_0)
			;
		ret = 1'b0;
		write_back_en = 1'b0;
		mem_read_en = 1'b0;
		mem_write_en = 1'b0;
		branch_en = 1'b0;
		nzp_en = 1'b0;
		sync_en = 1'b0;
		case (opcode)
			6'h00:
				;
			6'h01, 6'h02, 6'h03, 6'h04, 6'h05, 6'h06, 6'h07, 6'h08, 6'h09, 6'h0a, 6'h0b, 6'h0c, 6'h13, 6'h14: write_back_en = 1'b1;
			6'h0d: nzp_en = 1'b1;
			6'h0e: branch_en = 1'b1;
			6'h0f: begin
				mem_read_en = 1'b1;
				write_back_en = 1'b1;
			end
			6'h10: mem_write_en = 1'b1;
			6'h11: write_back_en = 1'b1;
			6'h12: ret = 1'b1;
			6'h15: sync_en = 1'b1;
			default:
				;
		endcase
	end
	initial _sv2v_0 = 0;
endmodule
