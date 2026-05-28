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
(* syn_dont_touch = 1 *) module pc (
	clk,
	rst,
	pc_en,
	branch_en,
	branch_offset,
	nzp_en,
	nzp_flag,
	nzp_mask,
	pc_out
);
	input wire clk;
	input wire rst;
	input wire pc_en;
	input wire branch_en;
	input wire [22:0] branch_offset;
	input wire nzp_en;
	input wire [2:0] nzp_flag;
	input wire [2:0] nzp_mask;
	output reg [31:0] pc_out;
	reg [2:0] nzp_reg;
	always @(posedge clk or posedge rst)
		if (rst) begin
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
endmodule
module decoder (
	instruction,
	opcode,
	rd_addr,
	rs1_addr,
	rs2_addr,
	rs3_addr,
	imm,
	nzp_mask,
	branch_offset,
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
	output wire [22:0] branch_offset;
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
	assign branch_offset = instruction[22:0];
	always @(*) begin
		if (_sv2v_0)
			;
		ret = 1'b0;
		write_back_en = 1'b0;
		mem_read_en = 1'b0;
		mem_write_en = 1'b0;
		branch_en = 1'b0;
		nzp_en = 1'b0;
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
			default:
				;
		endcase
	end
	initial _sv2v_0 = 0;
endmodule
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
module memory_controller (
	req_avail,
	req_addr,
	read_write_switch,
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
	parameter NUM_CORES = 1;
	parameter THREADS_PER_CORE = 4;
	parameter TOTAL_THREADS = NUM_CORES * THREADS_PER_CORE;
	input wire [TOTAL_THREADS - 1:0] req_avail;
	input wire [(TOTAL_THREADS * 32) - 1:0] req_addr;
	input wire [TOTAL_THREADS - 1:0] read_write_switch;
	input wire [(TOTAL_THREADS * 32) - 1:0] req_data;
	output wire [TOTAL_THREADS - 1:0] resp_valid;
	output wire [(TOTAL_THREADS * 32) - 1:0] resp_data;
	output wire [TOTAL_THREADS - 1:0] mem_req_valid;
	output wire [(TOTAL_THREADS * 32) - 1:0] mem_req_addr;
	output wire [TOTAL_THREADS - 1:0] mem_req_rw;
	output wire [(TOTAL_THREADS * 32) - 1:0] mem_req_data;
	input wire [TOTAL_THREADS - 1:0] mem_resp_valid;
	input wire [(TOTAL_THREADS * 32) - 1:0] mem_resp_data;
	genvar _gv_i_1;
	generate
		for (_gv_i_1 = 0; _gv_i_1 < TOTAL_THREADS; _gv_i_1 = _gv_i_1 + 1) begin : request_response_forwarding
			localparam i = _gv_i_1;
			assign mem_req_valid[i] = req_avail[i];
			assign mem_req_addr[i * 32+:32] = req_addr[i * 32+:32];
			assign mem_req_rw[i] = read_write_switch[i];
			assign mem_req_data[i * 32+:32] = req_data[i * 32+:32];
			assign resp_valid[i] = mem_resp_valid[i];
			assign resp_data[i * 32+:32] = mem_resp_data[i * 32+:32];
		end
	endgenerate
endmodule
module scheduler (
	clk,
	rst,
	core_start,
	fetcher_done,
	lsu_done,
	mem_read_en,
	mem_write_en,
	ret,
	fetcher_en,
	lsu_en,
	execute_en,
	write_back_en,
	current_state,
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
	output reg fetcher_en;
	output reg lsu_en;
	output reg execute_en;
	output reg write_back_en;
	output wire [2:0] current_state;
	output reg block_done;
	output reg pc_en;
	reg [2:0] state;
	assign current_state = state;
	wire all_done;
	assign all_done = &lsu_done;
	always @(posedge clk or posedge rst)
		if (rst) begin
			state <= 3'b000;
			fetcher_en <= 0;
			lsu_en <= 0;
			execute_en <= 0;
			write_back_en <= 0;
			block_done <= 0;
			pc_en <= 0;
		end
		else begin
			fetcher_en <= 0;
			lsu_en <= 0;
			execute_en <= 0;
			write_back_en <= 0;
			block_done <= 0;
			pc_en <= 0;
			case (state)
				3'b000:
					if (core_start) begin
						fetcher_en <= 1;
						state <= 3'b001;
					end
				3'b001: begin
					fetcher_en <= 1;
					if (fetcher_done) begin
						fetcher_en <= 0;
						state <= 3'b010;
					end
				end
				3'b010:
					if (mem_read_en || mem_write_en)
						state <= 3'b011;
					else
						state <= 3'b101;
				3'b011: begin
					lsu_en <= 1;
					state <= 3'b100;
				end
				3'b100:
					if (all_done)
						state <= 3'b101;
				3'b101: begin
					execute_en <= 1;
					state <= 3'b110;
				end
				3'b110: begin
					if (ret) begin
						block_done <= 1;
						state <= 3'b000;
					end
					else begin
						state <= 3'b001;
						pc_en <= 1;
					end
					write_back_en <= 1;
				end
				default:
					;
			endcase
		end
endmodule
module core (
	clk,
	rst,
	core_start,
	blockIdx,
	blockDim,
	block_done,
	thread_keep_alive,
	prog_mem_req_valid,
	prog_mem_req_addr,
	prog_mem_resp_valid,
	prog_mem_resp_data,
	data_mem_req_valid,
	data_mem_req_addr,
	data_mem_req_rw,
	data_mem_req_data,
	data_mem_resp_valid,
	data_mem_resp_data
);
	parameter THREADS_PER_CORE = 4;
	input wire clk;
	input wire rst;
	input wire core_start;
	input wire [31:0] blockIdx;
	input wire [31:0] blockDim;
	output wire block_done;
	output wire [31:0] thread_keep_alive;
	output wire prog_mem_req_valid;
	output wire [31:0] prog_mem_req_addr;
	input wire prog_mem_resp_valid;
	input wire [31:0] prog_mem_resp_data;
	output wire [THREADS_PER_CORE - 1:0] data_mem_req_valid;
	output wire [(THREADS_PER_CORE * 32) - 1:0] data_mem_req_addr;
	output wire [THREADS_PER_CORE - 1:0] data_mem_req_rw;
	output wire [(THREADS_PER_CORE * 32) - 1:0] data_mem_req_data;
	input wire [THREADS_PER_CORE - 1:0] data_mem_resp_valid;
	input wire [(THREADS_PER_CORE * 32) - 1:0] data_mem_resp_data;
	wire fetcher_en;
	wire lsu_en;
	wire execute_en;
	wire write_back_en_sched;
	wire pc_en;
	wire [2:0] current_state;
	wire [31:0] instruction;
	wire done;
	wire [31:0] req_addr;
	wire req_valid;
	wire [5:0] opcode;
	wire [4:0] rd_addr;
	wire [4:0] rs1_addr;
	wire [4:0] rs2_addr;
	wire [4:0] rs3_addr;
	wire [15:0] imm;
	wire [2:0] nzp_mask;
	wire [22:0] branch_offset;
	wire ret;
	wire write_back_en_dec;
	wire mem_read_en;
	wire mem_write_en;
	wire branch_en;
	wire nzp_en;
	(* syn_keep = 1 *) wire [31:0] alu_result [THREADS_PER_CORE - 1:0];
	(* syn_keep = 1 *) wire [2:0] nzp_result [THREADS_PER_CORE - 1:0];
	wire [THREADS_PER_CORE - 1:0] lsu_done;
	(* syn_keep = 1 *) wire [31:0] lsu_read_data [THREADS_PER_CORE - 1:0];
	(* syn_keep = 1 *) wire [31:0] reg_data1 [THREADS_PER_CORE - 1:0];
	(* syn_keep = 1 *) wire [31:0] reg_data2 [THREADS_PER_CORE - 1:0];
	(* syn_keep = 1 *) wire [31:0] reg_data3 [THREADS_PER_CORE - 1:0];
	(* syn_keep = 1 *) wire [31:0] mem_addr [THREADS_PER_CORE - 1:0];
	wire [31:0] pc_shared;
	scheduler #(.THREADS_PER_CORE(THREADS_PER_CORE)) shed(
		.clk(clk),
		.rst(rst),
		.core_start(core_start),
		.fetcher_done(done),
		.lsu_done(lsu_done),
		.mem_read_en(mem_read_en),
		.mem_write_en(mem_write_en),
		.ret(ret),
		.fetcher_en(fetcher_en),
		.lsu_en(lsu_en),
		.execute_en(execute_en),
		.write_back_en(write_back_en_sched),
		.current_state(current_state),
		.block_done(block_done),
		.pc_en(pc_en)
	);
	fetcher fetch(
		.clk(clk),
		.rst(rst),
		.core_en(fetcher_en),
		.pc_value(pc_shared),
		.instruction(instruction),
		.done(done),
		.req_valid(prog_mem_req_valid),
		.req_addr(prog_mem_req_addr),
		.resp_valid(prog_mem_resp_valid),
		.resp_data(prog_mem_resp_data)
	);
	decoder dec(
		.instruction(instruction),
		.opcode(opcode),
		.rd_addr(rd_addr),
		.rs1_addr(rs1_addr),
		.rs2_addr(rs2_addr),
		.rs3_addr(rs3_addr),
		.imm(imm),
		.nzp_mask(nzp_mask),
		.branch_offset(branch_offset),
		.ret(ret),
		.write_back_en(write_back_en_dec),
		.mem_read_en(mem_read_en),
		.mem_write_en(mem_write_en),
		.branch_en(branch_en),
		.nzp_en(nzp_en)
	);
	genvar _gv_i_2;
	(* syn_keep = 1 *) wire [31:0] write_data [THREADS_PER_CORE - 1:0];
	generate
		for (_gv_i_2 = 0; _gv_i_2 < THREADS_PER_CORE; _gv_i_2 = _gv_i_2 + 1) begin : thread_gen
			localparam i = _gv_i_2;
			assign mem_addr[i] = reg_data1[i] + {{16 {imm[15]}}, imm};
			assign write_data[i] = (mem_read_en ? lsu_read_data[i] : (opcode == 6'h11 ? {16'b0000000000000000, imm} : alu_result[i]));
			alu alu_inst(
				.operand1(reg_data1[i]),
				.operand2(reg_data2[i]),
				.operand3(reg_data3[i]),
				.op_select(opcode),
				.result(alu_result[i]),
				.nzp_flag(nzp_result[i])
			);
			lsu lsu_inst(
				.clk(clk),
				.rst(rst),
				.core_en(lsu_en),
				.mem_read_en(mem_read_en),
				.mem_write_en(mem_write_en),
				.mem_data_address(mem_addr[i]),
				.mem_write_data(reg_data3[i]),
				.req_valid(data_mem_req_valid[i]),
				.req_addr(data_mem_req_addr[i * 32+:32]),
				.read_write_switch(data_mem_req_rw[i]),
				.write_data(data_mem_req_data[i * 32+:32]),
				.resp_valid(data_mem_resp_valid[i]),
				.resp_data(data_mem_resp_data[i * 32+:32]),
				.done(lsu_done[i]),
				.mem_read_data(lsu_read_data[i])
			);
			registers reg_file(
				.clk(clk),
				.rst(rst),
				.w_addr(rd_addr),
				.r_addr1(rs1_addr),
				.r_addr2(rs2_addr),
				.r_addr3((mem_write_en ? rd_addr : rs3_addr)),
				.w_data(write_data[i]),
				.w_en(write_back_en_sched),
				.threadIdx(i),
				.blockIdx(blockIdx),
				.blockDim(blockDim),
				.r_data1(reg_data1[i]),
				.r_data2(reg_data2[i]),
				.r_data3(reg_data3[i])
			);
		end
	endgenerate
	pc pc_inst(
		.clk(clk),
		.rst(rst),
		.pc_en(pc_en),
		.branch_en(branch_en),
		.branch_offset(branch_offset),
		.nzp_en(nzp_en),
		.nzp_flag(nzp_result[0]),
		.nzp_mask(nzp_mask),
		.pc_out(pc_shared)
	);
	genvar _gv_k_1;
	wire [31:0] _keep_xor [THREADS_PER_CORE:0];
	assign _keep_xor[0] = 32'b00000000000000000000000000000000;
	generate
		for (_gv_k_1 = 0; _gv_k_1 < THREADS_PER_CORE; _gv_k_1 = _gv_k_1 + 1) begin : keep_xor_gen
			localparam k = _gv_k_1;
			assign _keep_xor[k + 1] = _keep_xor[k] ^ write_data[k];
		end
	endgenerate
	assign thread_keep_alive = _keep_xor[THREADS_PER_CORE];
endmodule
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
module gpu (
	clk,
	rst,
	dcr_write_en,
	dcr_addr,
	dcr_data,
	kernel_done,
	thread_keep_alive,
	prog_mem_req_valid,
	prog_mem_req_addr,
	prog_mem_resp_valid,
	prog_mem_resp_data,
	data_mem_req_valid,
	data_mem_req_addr,
	data_mem_req_rw,
	data_mem_req_data,
	data_mem_resp_valid,
	data_mem_resp_data
);
	parameter NUM_CORES = 4;
	parameter THREADS_PER_CORE = 4;
	parameter TOTAL_THREADS = NUM_CORES * THREADS_PER_CORE;
	input wire clk;
	input wire rst;
	input wire dcr_write_en;
	input wire [1:0] dcr_addr;
	input wire [31:0] dcr_data;
	output wire kernel_done;
	output wire [31:0] thread_keep_alive;
	output wire [NUM_CORES - 1:0] prog_mem_req_valid;
	output wire [(NUM_CORES * 32) - 1:0] prog_mem_req_addr;
	input wire [NUM_CORES - 1:0] prog_mem_resp_valid;
	input wire [(NUM_CORES * 32) - 1:0] prog_mem_resp_data;
	output wire [TOTAL_THREADS - 1:0] data_mem_req_valid;
	output wire [(TOTAL_THREADS * 32) - 1:0] data_mem_req_addr;
	output wire [TOTAL_THREADS - 1:0] data_mem_req_rw;
	output wire [(TOTAL_THREADS * 32) - 1:0] data_mem_req_data;
	input wire [TOTAL_THREADS - 1:0] data_mem_resp_valid;
	input wire [(TOTAL_THREADS * 32) - 1:0] data_mem_resp_data;
	wire [31:0] num_blocks;
	wire [31:0] blockDim;
	wire start;
	wire [NUM_CORES - 1:0] core_start;
	wire [(NUM_CORES * 32) - 1:0] blockIdx_out;
	wire [NUM_CORES - 1:0] block_done;
	wire [31:0] core_keep_alive [NUM_CORES - 1:0];
	dcr dcr_inst(
		.clk(clk),
		.rst(rst),
		.dcr_write_en(dcr_write_en),
		.dcr_addr(dcr_addr),
		.dcr_data(dcr_data),
		.num_blocks(num_blocks),
		.blockDim(blockDim),
		.start(start)
	);
	dispatcher dispatcher_inst(
		.clk(clk),
		.rst(rst),
		.dispatch_en(start),
		.num_blocks(num_blocks),
		.blockDim(blockDim),
		.block_done(block_done),
		.core_start(core_start),
		.blockIdx_out(blockIdx_out),
		.kernel_done(kernel_done)
	);
	genvar _gv_i_3;
	generate
		for (_gv_i_3 = 0; _gv_i_3 < NUM_CORES; _gv_i_3 = _gv_i_3 + 1) begin : core_gen
			localparam i = _gv_i_3;
			wire [THREADS_PER_CORE - 1:0] core_data_req_valid;
			wire [(THREADS_PER_CORE * 32) - 1:0] core_data_req_addr;
			wire [THREADS_PER_CORE - 1:0] core_data_req_rw;
			wire [(THREADS_PER_CORE * 32) - 1:0] core_data_req_data;
			wire [THREADS_PER_CORE - 1:0] core_data_resp_valid;
			wire [(THREADS_PER_CORE * 32) - 1:0] core_data_resp_data;
			wire [31:0] prog_mem_req_addr_wire;
			wire [31:0] prog_mem_resp_data_wire;
			assign prog_mem_req_addr[i * 32+:32] = prog_mem_req_addr_wire;
			assign prog_mem_resp_data_wire = prog_mem_resp_data[i * 32+:32];
			genvar _gv_j_1;
			for (_gv_j_1 = 0; _gv_j_1 < THREADS_PER_CORE; _gv_j_1 = _gv_j_1 + 1) begin : thread_wire_gen
				localparam j = _gv_j_1;
				assign data_mem_req_valid[(i * THREADS_PER_CORE) + j] = core_data_req_valid[j];
				assign data_mem_req_addr[((i * THREADS_PER_CORE) + j) * 32+:32] = core_data_req_addr[j * 32+:32];
				assign data_mem_req_rw[(i * THREADS_PER_CORE) + j] = core_data_req_rw[j];
				assign data_mem_req_data[((i * THREADS_PER_CORE) + j) * 32+:32] = core_data_req_data[j * 32+:32];
				assign core_data_resp_valid[j] = data_mem_resp_valid[(i * THREADS_PER_CORE) + j];
				assign core_data_resp_data[j * 32+:32] = data_mem_resp_data[((i * THREADS_PER_CORE) + j) * 32+:32];
			end
			core #(.THREADS_PER_CORE(THREADS_PER_CORE)) core_inst(
				.clk(clk),
				.rst(rst),
				.core_start(core_start[i]),
				.blockIdx(blockIdx_out[i * 32+:32]),
				.blockDim(blockDim),
				.block_done(block_done[i]),
				.thread_keep_alive(core_keep_alive[i]),
				.prog_mem_req_valid(prog_mem_req_valid[i]),
				.prog_mem_req_addr(prog_mem_req_addr_wire),
				.prog_mem_resp_valid(prog_mem_resp_valid[i]),
				.prog_mem_resp_data(prog_mem_resp_data_wire),
				.data_mem_req_valid(core_data_req_valid),
				.data_mem_req_addr(core_data_req_addr),
				.data_mem_req_rw(core_data_req_rw),
				.data_mem_req_data(core_data_req_data),
				.data_mem_resp_valid(core_data_resp_valid),
				.data_mem_resp_data(core_data_resp_data)
			);
		end
	endgenerate
	genvar _gv_m_1;
	wire [31:0] _top_keep_xor [NUM_CORES:0];
	assign _top_keep_xor[0] = 32'b00000000000000000000000000000000;
	generate
		for (_gv_m_1 = 0; _gv_m_1 < NUM_CORES; _gv_m_1 = _gv_m_1 + 1) begin : top_keep_xor_gen
			localparam m = _gv_m_1;
			assign _top_keep_xor[m + 1] = _top_keep_xor[m] ^ core_keep_alive[m];
		end
	endgenerate
	assign thread_keep_alive = _top_keep_xor[NUM_CORES];
endmodule