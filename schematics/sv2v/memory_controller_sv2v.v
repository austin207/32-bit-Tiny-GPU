module mem_controller (
	clk,
	rst,
	req_valid,
	req_addr,
	req_rw,
	req_data,
	resp_valid,
	resp_data,
	mem_req_valid,
	mem_req_addr,
	mem_req_rw,
	mem_req_data,
	mem_resp_valid,
	mem_resp_data
);
	reg _sv2v_0;
	parameter THREADS_PER_CORE = 4;
	input wire clk;
	input wire rst;
	input wire [THREADS_PER_CORE - 1:0] req_valid;
	input wire [(THREADS_PER_CORE * 32) - 1:0] req_addr;
	input wire [THREADS_PER_CORE - 1:0] req_rw;
	input wire [(THREADS_PER_CORE * 32) - 1:0] req_data;
	output reg [THREADS_PER_CORE - 1:0] resp_valid;
	output reg [(THREADS_PER_CORE * 32) - 1:0] resp_data;
	output reg mem_req_valid;
	output reg [31:0] mem_req_addr;
	output reg mem_req_rw;
	output reg [31:0] mem_req_data;
	input wire mem_resp_valid;
	input wire [31:0] mem_resp_data;
	localparam PTR_W = (THREADS_PER_CORE <= 1 ? 1 : $clog2(THREADS_PER_CORE));
	reg state;
	reg [PTR_W - 1:0] rr_ptr;
	reg [PTR_W - 1:0] in_flight;
	reg [THREADS_PER_CORE - 1:0] pending;
	reg [31:0] pending_addr [THREADS_PER_CORE - 1:0];
	reg [THREADS_PER_CORE - 1:0] pending_rw;
	reg [31:0] pending_data [THREADS_PER_CORE - 1:0];
	always @(posedge clk or posedge rst)
		if (rst) begin
			pending <= 1'sb0;
			pending_rw <= 1'sb0;
			begin : sv2v_autoblock_1
				reg signed [31:0] i;
				for (i = 0; i < THREADS_PER_CORE; i = i + 1)
					begin
						pending_addr[i] <= 32'b00000000000000000000000000000000;
						pending_data[i] <= 32'b00000000000000000000000000000000;
					end
			end
		end
		else begin
			begin : sv2v_autoblock_2
				reg signed [31:0] i;
				for (i = 0; i < THREADS_PER_CORE; i = i + 1)
					if (req_valid[i]) begin
						pending[i] <= 1'b1;
						pending_addr[i] <= req_addr[i * 32+:32];
						pending_rw[i] <= req_rw[i];
						pending_data[i] <= req_data[i * 32+:32];
					end
			end
			if ((state == 1'b1) && mem_resp_valid)
				pending[in_flight] <= 1'b0;
		end
	wire [THREADS_PER_CORE - 1:0] scan_valid;
	assign scan_valid = pending | req_valid;
	reg [PTR_W - 1:0] next_thread;
	reg found;
	function automatic [PTR_W - 1:0] sv2v_cast_E310E;
		input reg [PTR_W - 1:0] inp;
		sv2v_cast_E310E = inp;
	endfunction
	always @(*) begin
		if (_sv2v_0)
			;
		next_thread = 1'sb0;
		found = 1'b0;
		begin : sv2v_autoblock_3
			reg signed [31:0] j;
			for (j = 0; j < THREADS_PER_CORE; j = j + 1)
				if (!found && scan_valid[sv2v_cast_E310E(rr_ptr + j)]) begin
					next_thread = sv2v_cast_E310E(rr_ptr + j);
					found = 1'b1;
				end
		end
	end
	reg [31:0] sel_addr;
	reg sel_rw;
	reg [31:0] sel_data;
	always @(*) begin
		if (_sv2v_0)
			;
		if (req_valid[next_thread]) begin
			sel_addr = req_addr[next_thread * 32+:32];
			sel_rw = req_rw[next_thread];
			sel_data = req_data[next_thread * 32+:32];
		end
		else begin
			sel_addr = pending_addr[next_thread];
			sel_rw = pending_rw[next_thread];
			sel_data = pending_data[next_thread];
		end
	end
	always @(posedge clk or posedge rst)
		if (rst) begin
			state <= 1'b0;
			rr_ptr <= 1'sb0;
			in_flight <= 1'sb0;
			mem_req_valid <= 1'b0;
			mem_req_addr <= 32'b00000000000000000000000000000000;
			mem_req_rw <= 1'b0;
			mem_req_data <= 32'b00000000000000000000000000000000;
			resp_valid <= 1'sb0;
			begin : sv2v_autoblock_4
				reg signed [31:0] i;
				for (i = 0; i < THREADS_PER_CORE; i = i + 1)
					resp_data[i * 32+:32] <= 32'b00000000000000000000000000000000;
			end
		end
		else begin
			resp_valid <= 1'sb0;
			case (state)
				1'b0:
					if (found) begin
						in_flight <= next_thread;
						mem_req_valid <= 1'b1;
						mem_req_addr <= sel_addr;
						mem_req_rw <= sel_rw;
						mem_req_data <= sel_data;
						state <= 1'b1;
					end
					else
						mem_req_valid <= 1'b0;
				1'b1:
					if (mem_resp_valid) begin
						resp_valid[in_flight] <= 1'b1;
						resp_data[in_flight * 32+:32] <= mem_resp_data;
						rr_ptr <= sv2v_cast_E310E(in_flight + 1);
						mem_req_valid <= 1'b0;
						state <= 1'b0;
					end
				default: begin
					state <= 1'b0;
					mem_req_valid <= 1'b0;
					resp_valid <= 1'sb0;
				end
			endcase
		end
	initial _sv2v_0 = 0;
endmodule
