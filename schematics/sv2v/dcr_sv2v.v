module dcr (
	clk,
	rst,
	dcr_write_en,
	dcr_addr,
	dcr_data,
	num_blocks,
	blockDim,
	start
);
	input wire clk;
	input wire rst;
	input wire dcr_write_en;
	input wire [1:0] dcr_addr;
	input wire [31:0] dcr_data;
	output reg [31:0] num_blocks;
	output reg [31:0] blockDim;
	output reg start;
	always @(posedge clk or posedge rst)
		if (rst) begin
			num_blocks <= 0;
			blockDim <= 0;
			start <= 0;
		end
		else begin
			start <= 0;
			if (dcr_write_en)
				case (dcr_addr)
					2'b00: num_blocks <= dcr_data;
					2'b01: blockDim <= dcr_data;
					2'b10: start <= 1;
				endcase
		end
endmodule
