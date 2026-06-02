(* syn_dont_touch = 1 *) module registers (
	clk,
	rst,
	r_addr1,
	r_addr2,
	r_addr3,
	w_addr,
	w_data,
	w_en,
	threadIdx,
	blockIdx,
	blockDim,
	r_data1,
	r_data2,
	r_data3
);
	reg _sv2v_0;
	input wire clk;
	input wire rst;
	input wire [4:0] r_addr1;
	input wire [4:0] r_addr2;
	input wire [4:0] r_addr3;
	input wire [4:0] w_addr;
	input wire [31:0] w_data;
	input wire w_en;
	input wire [31:0] threadIdx;
	input wire [31:0] blockIdx;
	input wire [31:0] blockDim;
	output reg [31:0] r_data1;
	output reg [31:0] r_data2;
	output reg [31:0] r_data3;
	reg [31:0] reg_file [0:31];
	wire [31:0] r29_value;
	assign r29_value = (blockDim == 32'd1 ? blockIdx : threadIdx);
	always @(posedge clk or posedge rst)
		if (rst) begin : sv2v_autoblock_1
			reg signed [31:0] i;
			for (i = 1; i < 29; i = i + 1)
				reg_file[i] <= 32'b00000000000000000000000000000000;
		end
		else if (w_en) begin
			if ((w_addr >= 1) && (w_addr <= 28))
				reg_file[w_addr] <= w_data;
		end
	always @(*) begin : read_port_1
		if (_sv2v_0)
			;
		case (r_addr1)
			5'd0: r_data1 = 32'b00000000000000000000000000000000;
			5'd29: r_data1 = r29_value;
			5'd30: r_data1 = blockIdx;
			5'd31: r_data1 = blockDim;
			default: r_data1 = reg_file[r_addr1];
		endcase
	end
	always @(*) begin : read_port_2
		if (_sv2v_0)
			;
		case (r_addr2)
			5'd0: r_data2 = 32'b00000000000000000000000000000000;
			5'd29: r_data2 = r29_value;
			5'd30: r_data2 = blockIdx;
			5'd31: r_data2 = blockDim;
			default: r_data2 = reg_file[r_addr2];
		endcase
	end
	always @(*) begin : read_port_3
		if (_sv2v_0)
			;
		case (r_addr3)
			5'd0: r_data3 = 32'b00000000000000000000000000000000;
			5'd29: r_data3 = r29_value;
			5'd30: r_data3 = blockIdx;
			5'd31: r_data3 = blockDim;
			default: r_data3 = reg_file[r_addr3];
		endcase
	end
	initial _sv2v_0 = 0;
endmodule
