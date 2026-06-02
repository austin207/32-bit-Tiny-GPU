module fetcher (
	clk,
	rst,
	core_en,
	pc_value,
	instruction,
	done,
	req_valid,
	req_addr,
	resp_valid,
	resp_data
);
	input wire clk;
	input wire rst;
	input wire core_en;
	input wire [31:0] pc_value;
	output reg [31:0] instruction;
	output reg done;
	output reg req_valid;
	output reg [31:0] req_addr;
	input wire resp_valid;
	input wire [31:0] resp_data;
	reg state;
	always @(posedge clk or posedge rst)
		if (rst) begin
			state <= 1'b0;
			instruction <= 32'b00000000000000000000000000000000;
			req_valid <= 0;
			req_addr <= 32'b00000000000000000000000000000000;
			done <= 0;
		end
		else begin
			req_valid <= 0;
			done <= 0;
			case (state)
				1'b0:
					if (core_en) begin
						req_addr <= pc_value;
						req_valid <= 1;
						done <= 0;
						state <= 1'b1;
					end
				1'b1:
					if (resp_valid) begin
						instruction <= resp_data;
						done <= 1;
						state <= 1'b0;
					end
				default:
					;
			endcase
		end
endmodule
