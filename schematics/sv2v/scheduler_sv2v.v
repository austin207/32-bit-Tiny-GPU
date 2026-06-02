module scheduler (
	clk,
	rst,
	core_start,
	fetcher_done,
	lsu_done,
	mem_read_en,
	mem_write_en,
	ret,
	divergence_detected,
	taken_mask,
	sync_en,
	saved_mask,
	fetcher_en,
	lsu_en,
	execute_en,
	write_back_en,
	current_state,
	active_mask,
	block_done,
	pc_en
);
	parameter NUM_CORES = 1;
	parameter THREADS_PER_CORE = 4;
	parameter TOTAL_THREADS = NUM_CORES * THREADS_PER_CORE;
	input wire clk;
	input wire rst;
	input wire core_start;
	input wire fetcher_done;
	input wire [TOTAL_THREADS - 1:0] lsu_done;
	input wire mem_read_en;
	input wire mem_write_en;
	input wire ret;
	input wire divergence_detected;
	input wire [THREADS_PER_CORE - 1:0] taken_mask;
	input wire sync_en;
	input wire [THREADS_PER_CORE - 1:0] saved_mask;
	output reg fetcher_en;
	output reg lsu_en;
	output reg execute_en;
	output reg write_back_en;
	output wire [3:0] current_state;
	output reg [THREADS_PER_CORE - 1:0] active_mask;
	output reg block_done;
	output reg pc_en;
	reg [3:0] state;
	assign current_state = state;
	wire all_done;
	assign all_done = &lsu_done;
	always @(posedge clk or posedge rst)
		if (rst) begin
			state <= 4'b0000;
			fetcher_en <= 0;
			lsu_en <= 0;
			execute_en <= 0;
			write_back_en <= 0;
			block_done <= 0;
			pc_en <= 0;
			active_mask <= 1'sb1;
		end
		else begin
			fetcher_en <= 0;
			lsu_en <= 0;
			execute_en <= 0;
			write_back_en <= 0;
			block_done <= 0;
			pc_en <= 0;
			case (state)
				4'b0000:
					if (core_start) begin
						fetcher_en <= 1;
						active_mask <= 1'sb1;
						state <= 4'b0001;
					end
				4'b0001: begin
					fetcher_en <= 1;
					if (fetcher_done) begin
						fetcher_en <= 0;
						state <= 4'b0010;
					end
				end
				4'b0010:
					if (mem_read_en || mem_write_en)
						state <= 4'b0011;
					else
						state <= 4'b0101;
				4'b0011: begin
					lsu_en <= 1;
					state <= 4'b0100;
				end
				4'b0100:
					if (all_done)
						state <= 4'b0101;
				4'b0101: begin
					execute_en <= 1;
					state <= 4'b0110;
				end
				4'b0110: begin
					if (ret) begin
						block_done <= 1;
						state <= 4'b0000;
					end
					else if (divergence_detected) begin
						state <= 4'b0111;
						pc_en <= 1;
					end
					else if (sync_en) begin
						state <= 4'b1000;
						pc_en <= 1;
					end
					else begin
						state <= 4'b0001;
						pc_en <= 1;
					end
					write_back_en <= 1;
				end
				4'b0111: begin
					active_mask <= taken_mask;
					state <= 4'b0001;
				end
				4'b1000: begin
					active_mask <= saved_mask;
					state <= 4'b0001;
				end
				default:
					;
			endcase
		end
endmodule
