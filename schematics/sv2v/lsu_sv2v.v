module lsu (
	clk,
	rst,
	core_en,
	done,
	mem_data_address,
	req_valid,
	req_addr,
	write_data,
	resp_valid,
	resp_data,
	mem_write_en,
	mem_write_data,
	mem_read_en,
	mem_read_data,
	read_write_switch
);
	input wire clk;
	input wire rst;
	input wire core_en;
	output reg done;
	input wire [31:0] mem_data_address;
	output reg req_valid;
	output reg [31:0] req_addr;
	output reg [31:0] write_data;
	input wire resp_valid;
	input wire [31:0] resp_data;
	input wire mem_write_en;
	input wire [31:0] mem_write_data;
	input wire mem_read_en;
	output reg [31:0] mem_read_data;
	output reg read_write_switch;
	reg is_read;
	reg state;
	always @(posedge clk or posedge rst)
		if (rst) begin
			req_valid <= 0;
			req_addr <= 32'b00000000000000000000000000000000;
			mem_read_data <= 32'b00000000000000000000000000000000;
			done <= 0;
			is_read <= 0;
			state <= 1'b0;
		end
		else begin
			req_valid <= 0;
			req_addr <= 32'b00000000000000000000000000000000;
			done <= 0;
			case (state)
				1'b0:
					if (core_en) begin
						if (mem_read_en) begin
							is_read <= 1;
							req_addr <= mem_data_address;
							req_valid <= 1;
							read_write_switch <= 1;
							state <= 1'b1;
						end
						else if (mem_write_en) begin
							is_read <= 0;
							req_addr <= mem_data_address;
							req_valid <= 1;
							read_write_switch <= 0;
							write_data <= mem_write_data;
							state <= 1'b1;
						end
					end
				1'b1:
					if (is_read) begin
						if (resp_valid) begin
							mem_read_data <= resp_data;
							done <= 1;
							state <= 1'b0;
						end
					end
					else if (resp_valid) begin
						done <= 1;
						state <= 1'b0;
					end
				default: state <= 1'b0;
			endcase
		end
endmodule
