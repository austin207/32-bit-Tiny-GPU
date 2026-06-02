module dispatcher (
	clk,
	rst,
	num_blocks,
	blockDim,
	dispatch_en,
	block_done,
	core_start,
	blockIdx_out,
	kernel_done
);
	parameter NUM_CORES = 4;
	parameter THREADS_PER_CORE = 4;
	input wire clk;
	input wire rst;
	input wire [31:0] num_blocks;
	input wire [31:0] blockDim;
	input wire dispatch_en;
	input wire [NUM_CORES - 1:0] block_done;
	output reg [NUM_CORES - 1:0] core_start;
	output reg [(NUM_CORES * 32) - 1:0] blockIdx_out;
	output reg kernel_done;
	reg [31:0] next_block;
	reg [31:0] active_blocks;
	reg assigned;
	reg [31:0] done_count;
	reg signed [31:0] delta;
	always @(posedge clk or posedge rst)
		if (rst) begin
			next_block <= 0;
			active_blocks <= 0;
			kernel_done <= 0;
			begin : sv2v_autoblock_1
				reg signed [31:0] i;
				for (i = 0; i < NUM_CORES; i = i + 1)
					begin
						core_start[i] <= 0;
						blockIdx_out[i * 32+:32] <= 0;
					end
			end
		end
		else begin
			done_count = 0;
			delta = 0;
			begin : sv2v_autoblock_2
				reg signed [31:0] i;
				for (i = 0; i < NUM_CORES; i = i + 1)
					if (block_done[i]) begin
						core_start[i] <= 0;
						done_count = done_count + 1;
						delta = delta - 1;
					end
			end
			if (dispatch_en) begin
				assigned = 0;
				begin : sv2v_autoblock_3
					reg signed [31:0] i;
					for (i = 0; i < NUM_CORES; i = i + 1)
						if (((!assigned && (core_start[i] == 0)) && (block_done[i] == 0)) && (next_block < num_blocks)) begin
							core_start[i] <= 1;
							blockIdx_out[i * 32+:32] <= next_block;
							next_block <= next_block + 1;
							delta = delta + 1;
							assigned = 1;
						end
				end
			end
			active_blocks <= active_blocks + delta;
			if (((next_block == num_blocks) && ((active_blocks + delta) == 0)) && (num_blocks > 0))
				kernel_done <= 1;
		end
endmodule
