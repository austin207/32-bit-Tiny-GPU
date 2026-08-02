module alu (
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
	wire signed [15:0] dot_p0;
	wire signed [15:0] dot_p1;
	wire signed [15:0] dot_p2;
	wire signed [15:0] dot_p3;
	assign dot_p0 = $signed(operand1[7:0]) * $signed(operand2[7:0]);
	assign dot_p1 = $signed(operand1[15:8]) * $signed(operand2[15:8]);
	assign dot_p2 = $signed(operand1[23:16]) * $signed(operand2[23:16]);
	assign dot_p3 = $signed(operand1[31:24]) * $signed(operand2[31:24]);
	reg [7:0] exp8_result;
	always @(*) begin
		if (_sv2v_0)
			;
		result = 32'b00000000000000000000000000000000;
		nzp_flag = 3'b000;
		case (op_select)
			6'h01: result = operand1 + operand2;
			6'h02: result = operand1 - operand2;
			6'h03: result = operand1 * operand2;
			6'h04: result = 32'b0;
			6'h05: result = 32'b0;
			6'h06: result = operand1 << operand2;
			6'h07: result = operand1 >> operand2;
			6'h08: result = operand1 & operand2;
			6'h09: result = operand1 | operand2;
			6'h0a: result = operand1 ^ operand2;
			6'h0b: result = ~operand1;
			6'h0c: result = (operand1 * operand2) + operand3;
			6'h0d: begin
				result = 32'b00000000000000000000000000000000;
				if ($signed(operand1) == $signed(operand2))
					nzp_flag = 3'b010;
				else if ($signed(operand1) > $signed(operand2))
					nzp_flag = 3'b001;
				else
					nzp_flag = 3'b100;
			end
			6'h13: result = $signed(operand1) * $signed(operand2);
			6'h14: result = $signed(operand1) >>> operand2;
			6'h16: result = ((($signed(operand3) + dot_p0) + dot_p1) + dot_p2) + dot_p3;
			6'h17: result = ($signed(operand1) < 0 ? 32'b00000000000000000000000000000000 : operand1);
			6'h18:
				if ($signed(operand1) > 127)
					result = 32'd127;
				else if ($signed(operand1) < -128)
					result = -32'd128;
				else
					result = operand1;
			6'h19: result = ($signed(operand1) >= $signed(operand2) ? operand1 : operand2);
			6'h1a: result = ($signed(operand1) <= $signed(operand2) ? operand1 : operand2);
			6'h1b: result = {24'b000000000000000000000000, exp8_result};
			default:
				;
		endcase
	end
	always @(*) begin
		if (_sv2v_0)
			;
		case (operand1[7:0])
			8'h80: exp8_result = 8'd17;
			8'h81: exp8_result = 8'd17;
			8'h82: exp8_result = 8'd18;
			8'h83: exp8_result = 8'd18;
			8'h84: exp8_result = 8'd18;
			8'h85: exp8_result = 8'd19;
			8'h86: exp8_result = 8'd19;
			8'h87: exp8_result = 8'd19;
			8'h88: exp8_result = 8'd19;
			8'h89: exp8_result = 8'd20;
			8'h8a: exp8_result = 8'd20;
			8'h8b: exp8_result = 8'd20;
			8'h8c: exp8_result = 8'd21;
			8'h8d: exp8_result = 8'd21;
			8'h8e: exp8_result = 8'd21;
			8'h8f: exp8_result = 8'd22;
			8'h90: exp8_result = 8'd22;
			8'h91: exp8_result = 8'd22;
			8'h92: exp8_result = 8'd23;
			8'h93: exp8_result = 8'd23;
			8'h94: exp8_result = 8'd23;
			8'h95: exp8_result = 8'd24;
			8'h96: exp8_result = 8'd24;
			8'h97: exp8_result = 8'd25;
			8'h98: exp8_result = 8'd25;
			8'h99: exp8_result = 8'd25;
			8'h9a: exp8_result = 8'd26;
			8'h9b: exp8_result = 8'd26;
			8'h9c: exp8_result = 8'd27;
			8'h9d: exp8_result = 8'd27;
			8'h9e: exp8_result = 8'd27;
			8'h9f: exp8_result = 8'd28;
			8'ha0: exp8_result = 8'd28;
			8'ha1: exp8_result = 8'd29;
			8'ha2: exp8_result = 8'd29;
			8'ha3: exp8_result = 8'd30;
			8'ha4: exp8_result = 8'd30;
			8'ha5: exp8_result = 8'd31;
			8'ha6: exp8_result = 8'd31;
			8'ha7: exp8_result = 8'd32;
			8'ha8: exp8_result = 8'd32;
			8'ha9: exp8_result = 8'd33;
			8'haa: exp8_result = 8'd33;
			8'hab: exp8_result = 8'd34;
			8'hac: exp8_result = 8'd34;
			8'had: exp8_result = 8'd35;
			8'hae: exp8_result = 8'd35;
			8'haf: exp8_result = 8'd36;
			8'hb0: exp8_result = 8'd36;
			8'hb1: exp8_result = 8'd37;
			8'hb2: exp8_result = 8'd38;
			8'hb3: exp8_result = 8'd38;
			8'hb4: exp8_result = 8'd39;
			8'hb5: exp8_result = 8'd39;
			8'hb6: exp8_result = 8'd40;
			8'hb7: exp8_result = 8'd41;
			8'hb8: exp8_result = 8'd41;
			8'hb9: exp8_result = 8'd42;
			8'hba: exp8_result = 8'd43;
			8'hbb: exp8_result = 8'd43;
			8'hbc: exp8_result = 8'd44;
			8'hbd: exp8_result = 8'd45;
			8'hbe: exp8_result = 8'd45;
			8'hbf: exp8_result = 8'd46;
			8'hc0: exp8_result = 8'd47;
			8'hc1: exp8_result = 8'd47;
			8'hc2: exp8_result = 8'd48;
			8'hc3: exp8_result = 8'd49;
			8'hc4: exp8_result = 8'd50;
			8'hc5: exp8_result = 8'd51;
			8'hc6: exp8_result = 8'd51;
			8'hc7: exp8_result = 8'd52;
			8'hc8: exp8_result = 8'd53;
			8'hc9: exp8_result = 8'd54;
			8'hca: exp8_result = 8'd55;
			8'hcb: exp8_result = 8'd55;
			8'hcc: exp8_result = 8'd56;
			8'hcd: exp8_result = 8'd57;
			8'hce: exp8_result = 8'd58;
			8'hcf: exp8_result = 8'd59;
			8'hd0: exp8_result = 8'd60;
			8'hd1: exp8_result = 8'd61;
			8'hd2: exp8_result = 8'd62;
			8'hd3: exp8_result = 8'd63;
			8'hd4: exp8_result = 8'd64;
			8'hd5: exp8_result = 8'd65;
			8'hd6: exp8_result = 8'd66;
			8'hd7: exp8_result = 8'd67;
			8'hd8: exp8_result = 8'd68;
			8'hd9: exp8_result = 8'd69;
			8'hda: exp8_result = 8'd70;
			8'hdb: exp8_result = 8'd71;
			8'hdc: exp8_result = 8'd72;
			8'hdd: exp8_result = 8'd74;
			8'hde: exp8_result = 8'd75;
			8'hdf: exp8_result = 8'd76;
			8'he0: exp8_result = 8'd77;
			8'he1: exp8_result = 8'd78;
			8'he2: exp8_result = 8'd79;
			8'he3: exp8_result = 8'd81;
			8'he4: exp8_result = 8'd82;
			8'he5: exp8_result = 8'd83;
			8'he6: exp8_result = 8'd85;
			8'he7: exp8_result = 8'd86;
			8'he8: exp8_result = 8'd87;
			8'he9: exp8_result = 8'd89;
			8'hea: exp8_result = 8'd90;
			8'heb: exp8_result = 8'd91;
			8'hec: exp8_result = 8'd93;
			8'hed: exp8_result = 8'd94;
			8'hee: exp8_result = 8'd96;
			8'hef: exp8_result = 8'd97;
			8'hf0: exp8_result = 8'd99;
			8'hf1: exp8_result = 8'd100;
			8'hf2: exp8_result = 8'd102;
			8'hf3: exp8_result = 8'd104;
			8'hf4: exp8_result = 8'd105;
			8'hf5: exp8_result = 8'd107;
			8'hf6: exp8_result = 8'd109;
			8'hf7: exp8_result = 8'd110;
			8'hf8: exp8_result = 8'd112;
			8'hf9: exp8_result = 8'd114;
			8'hfa: exp8_result = 8'd116;
			8'hfb: exp8_result = 8'd117;
			8'hfc: exp8_result = 8'd119;
			8'hfd: exp8_result = 8'd121;
			8'hfe: exp8_result = 8'd123;
			8'hff: exp8_result = 8'd125;
			default: exp8_result = 8'd127;
		endcase
	end
	initial _sv2v_0 = 0;
endmodule
module registers (
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
module pc (
	clk,
	rst,
	block_rst,
	pc_en,
	branch_en,
	branch_offset,
	call_en,
	sret_en,
	sret_target,
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
	input wire call_en;
	input wire sret_en;
	input wire [31:0] sret_target;
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
				if (sret_en)
					pc_out <= sret_target;
				else if (call_en || (branch_en && ((nzp_reg & nzp_mask) != 0)))
					pc_out <= pc_out + {{20 {branch_offset[11]}}, branch_offset};
				else
					pc_out <= pc_out + 1;
			end
		end
	assign nzp_out = nzp_reg;
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
	sync_offset,
	branch_offset,
	sync_en,
	ret,
	write_back_en,
	mem_read_en,
	mem_write_en,
	branch_en,
	nzp_en,
	call_en,
	sret_en
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
	output reg call_en;
	output reg sret_en;
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
		call_en = 1'b0;
		sret_en = 1'b0;
		case (opcode)
			6'h00:
				;
			6'h01, 6'h02, 6'h03, 6'h04, 6'h05, 6'h06, 6'h07, 6'h08, 6'h09, 6'h0a, 6'h0b, 6'h0c, 6'h13, 6'h14, 6'h16, 6'h17, 6'h18, 6'h19, 6'h1a, 6'h1b: write_back_en = 1'b1;
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
			6'h1c: call_en = 1'b1;
			6'h1d: sret_en = 1'b1;
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
	integer scan_idx;
	always @(*) begin
		if (_sv2v_0)
			;
		next_thread = 1'sb0;
		found = 1'b0;
		scan_idx = 0;
		begin : sv2v_autoblock_3
			reg signed [31:0] j;
			for (j = 0; j < THREADS_PER_CORE; j = j + 1)
				begin
					scan_idx = rr_ptr + j;
					if (scan_idx >= THREADS_PER_CORE)
						scan_idx = scan_idx - THREADS_PER_CORE;
					if (!found && scan_valid[scan_idx]) begin
						next_thread = scan_idx;
						found = 1'b1;
					end
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
	function automatic [PTR_W - 1:0] sv2v_cast_E310E;
		input reg [PTR_W - 1:0] inp;
		sv2v_cast_E310E = inp;
	endfunction
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
module warp_stack (
	clk,
	rst,
	push,
	push_sync_pc,
	push_saved_mask,
	pop,
	top_sync_pc,
	top_saved_mask,
	stack_empty,
	stack_full,
	stack_overflow
);
	parameter THREADS_PER_CORE = 4;
	parameter STACK_DEPTH = 4;
	input wire clk;
	input wire rst;
	input wire push;
	input wire [31:0] push_sync_pc;
	input wire [THREADS_PER_CORE - 1:0] push_saved_mask;
	input wire pop;
	output wire [31:0] top_sync_pc;
	output wire [THREADS_PER_CORE - 1:0] top_saved_mask;
	output wire stack_empty;
	output wire stack_full;
	output wire stack_overflow;
	reg [35:0] stack_mem [STACK_DEPTH - 1:0];
	reg [2:0] sp;
	assign stack_empty = sp == 0;
	assign stack_full = sp == STACK_DEPTH;
	assign stack_overflow = push && stack_full;
	assign top_sync_pc = (sp > 0 ? stack_mem[sp - 1][35:4] : 32'b00000000000000000000000000000000);
	assign top_saved_mask = (sp > 0 ? stack_mem[sp - 1][3:0] : {THREADS_PER_CORE {1'sb1}});
	always @(posedge clk or posedge rst)
		if (rst)
			sp <= 0;
		else begin
			if (push && !stack_full) begin
				stack_mem[sp] <= {push_sync_pc, push_saved_mask};
				sp <= sp + 1;
			end
			if (pop && !stack_empty)
				sp <= sp - 1;
		end
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
	reg _sv2v_0;
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
	output wire data_mem_req_valid;
	output wire [31:0] data_mem_req_addr;
	output wire data_mem_req_rw;
	output wire [31:0] data_mem_req_data;
	input wire data_mem_resp_valid;
	input wire [31:0] data_mem_resp_data;
	wire fetcher_en;
	wire lsu_en;
	wire execute_en;
	wire write_back_en_sched;
	wire pc_en;
	wire [3:0] current_state;
	wire [31:0] instruction_raw;
	reg [31:0] instruction;
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
	wire [10:0] sync_offset;
	wire [11:0] branch_offset;
	wire ret;
	wire write_back_en_dec;
	wire mem_read_en;
	wire mem_write_en;
	wire branch_en;
	wire nzp_en;
	wire sync_en;
	(* syn_keep = 1 *) wire [31:0] alu_result [THREADS_PER_CORE - 1:0];
	(* syn_keep = 1 *) wire [2:0] nzp_result [THREADS_PER_CORE - 1:0];
	wire [THREADS_PER_CORE - 1:0] lsu_done_raw;
	reg [THREADS_PER_CORE - 1:0] lsu_done_latch;
	wire [THREADS_PER_CORE - 1:0] lsu_done;
	(* syn_keep = 1 *) wire [31:0] lsu_read_data [THREADS_PER_CORE - 1:0];
	(* syn_keep = 1 *) wire [31:0] reg_data1 [THREADS_PER_CORE - 1:0];
	(* syn_keep = 1 *) wire [31:0] reg_data2 [THREADS_PER_CORE - 1:0];
	(* syn_keep = 1 *) wire [31:0] reg_data3 [THREADS_PER_CORE - 1:0];
	(* syn_keep = 1 *) wire [31:0] mem_addr [THREADS_PER_CORE - 1:0];
	wire [THREADS_PER_CORE - 1:0] lsu_req_valid;
	wire [(THREADS_PER_CORE * 32) - 1:0] lsu_req_addr;
	wire [THREADS_PER_CORE - 1:0] lsu_req_rw;
	wire [(THREADS_PER_CORE * 32) - 1:0] lsu_req_data;
	wire [THREADS_PER_CORE - 1:0] lsu_resp_valid;
	wire [(THREADS_PER_CORE * 32) - 1:0] lsu_resp_data;
	wire [31:0] pc_out [THREADS_PER_CORE - 1:0];
	wire [THREADS_PER_CORE - 1:0] active_mask;
	wire [2:0] nzp_stored [THREADS_PER_CORE - 1:0];
	reg divergence_detected;
	reg [THREADS_PER_CORE - 1:0] taken_mask;
	wire pc_block_rst;
	assign pc_block_rst = (current_state == 4'b0000) && core_start;
	always @(posedge clk or posedge rst)
		if (rst)
			instruction <= 32'b00000000000000000000000000000000;
		else if (done)
			instruction <= instruction_raw;
	always @(posedge clk or posedge rst)
		if (rst)
			lsu_done_latch <= 1'sb0;
		else if (done && ((instruction_raw[31:26] == 6'h0f) || (instruction_raw[31:26] == 6'h10)))
			lsu_done_latch <= 1'sb0;
		else if (lsu_en)
			lsu_done_latch <= 1'sb0;
		else begin : sv2v_autoblock_1
			reg signed [31:0] i;
			for (i = 0; i < THREADS_PER_CORE; i = i + 1)
				if (lsu_done_raw[i])
					lsu_done_latch[i] <= 1'b1;
		end
	assign lsu_done = lsu_done_latch | ~active_mask;
	always @(*) begin
		if (_sv2v_0)
			;
		begin : sv2v_autoblock_2
			reg signed [31:0] i;
			for (i = 0; i < THREADS_PER_CORE; i = i + 1)
				taken_mask[i] = (branch_en && active_mask[i]) && ((nzp_stored[i] & nzp_mask) != 3'b000);
		end
		divergence_detected = (branch_en && (taken_mask != active_mask)) && (taken_mask != {THREADS_PER_CORE {1'sb0}});
	end
	reg [31:0] active_pc;
	always @(*) begin
		if (_sv2v_0)
			;
		active_pc = pc_out[0];
		begin : sv2v_autoblock_3
			reg signed [31:0] i;
			for (i = THREADS_PER_CORE - 1; i >= 0; i = i - 1)
				if (active_mask[i])
					active_pc = pc_out[i];
		end
	end
	wire [31:0] sync_pc;
	assign sync_pc = active_pc + {21'b000000000000000000000, sync_offset};
	wire call_en;
	wire sret_en;
	wire [31:0] call_return_pc;
	assign call_return_pc = active_pc + 32'd1;
	wire cs_push;
	wire cs_pop;
	wire [31:0] cs_top_return_pc;
	wire cs_stack_empty;
	wire cs_stack_full;
	wire cs_stack_overflow;
	assign cs_push = call_en & pc_en;
	assign cs_pop = sret_en & pc_en;
	wire ws_push;
	wire ws_pop;
	wire [31:0] ws_top_sync_pc;
	wire [THREADS_PER_CORE - 1:0] ws_top_saved_mask;
	wire ws_stack_empty;
	wire ws_stack_full;
	wire ws_stack_overflow;
	assign ws_push = current_state == 4'b0111;
	assign ws_pop = current_state == 4'b1000;
	scheduler #(.THREADS_PER_CORE(THREADS_PER_CORE)) shed(
		.clk(clk),
		.rst(rst),
		.core_start(core_start),
		.fetcher_done(done),
		.lsu_done(lsu_done),
		.mem_read_en(mem_read_en),
		.mem_write_en(mem_write_en),
		.ret(ret),
		.divergence_detected(divergence_detected),
		.taken_mask(taken_mask),
		.sync_en(sync_en),
		.saved_mask((ws_stack_empty ? {THREADS_PER_CORE {1'b1}} : ws_top_saved_mask)),
		.fetcher_en(fetcher_en),
		.lsu_en(lsu_en),
		.execute_en(execute_en),
		.write_back_en(write_back_en_sched),
		.current_state(current_state),
		.active_mask(active_mask),
		.block_done(block_done),
		.pc_en(pc_en)
	);
	warp_stack #(.THREADS_PER_CORE(THREADS_PER_CORE)) ws(
		.clk(clk),
		.rst(rst),
		.push(ws_push),
		.push_sync_pc(sync_pc),
		.push_saved_mask(~taken_mask & active_mask),
		.pop(ws_pop),
		.top_sync_pc(ws_top_sync_pc),
		.top_saved_mask(ws_top_saved_mask),
		.stack_empty(ws_stack_empty),
		.stack_full(ws_stack_full),
		.stack_overflow(ws_stack_overflow)
	);
	call_stack cs(
		.clk(clk),
		.rst(rst),
		.push(cs_push),
		.push_return_pc(call_return_pc),
		.pop(cs_pop),
		.top_return_pc(cs_top_return_pc),
		.stack_empty(cs_stack_empty),
		.stack_full(cs_stack_full),
		.stack_overflow(cs_stack_overflow)
	);
	fetcher fetch(
		.clk(clk),
		.rst(rst),
		.core_en(fetcher_en),
		.pc_value(active_pc),
		.instruction(instruction_raw),
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
		.sync_offset(sync_offset),
		.branch_offset(branch_offset),
		.sync_en(sync_en),
		.call_en(call_en),
		.sret_en(sret_en),
		.ret(ret),
		.write_back_en(write_back_en_dec),
		.mem_read_en(mem_read_en),
		.mem_write_en(mem_write_en),
		.branch_en(branch_en),
		.nzp_en(nzp_en)
	);
	genvar _gv_i_1;
	(* syn_keep = 1 *) wire [31:0] write_data [THREADS_PER_CORE - 1:0];
	generate
		for (_gv_i_1 = 0; _gv_i_1 < THREADS_PER_CORE; _gv_i_1 = _gv_i_1 + 1) begin : thread_gen
			localparam i = _gv_i_1;
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
				.core_en(lsu_en & active_mask[i]),
				.done(lsu_done_raw[i]),
				.mem_data_address(mem_addr[i]),
				.req_valid(lsu_req_valid[i]),
				.req_addr(lsu_req_addr[i * 32+:32]),
				.write_data(lsu_req_data[i * 32+:32]),
				.resp_valid(lsu_resp_valid[i]),
				.resp_data(lsu_resp_data[i * 32+:32]),
				.mem_write_en(mem_write_en),
				.mem_write_data(reg_data3[i]),
				.mem_read_en(mem_read_en),
				.mem_read_data(lsu_read_data[i]),
				.read_write_switch(lsu_req_rw[i])
			);
			registers reg_file(
				.clk(clk),
				.rst(rst),
				.r_addr1(rs1_addr),
				.r_addr2(rs2_addr),
				.r_addr3((mem_write_en ? rd_addr : rs3_addr)),
				.w_addr(rd_addr),
				.w_data(write_data[i]),
				.w_en((write_back_en_sched & write_back_en_dec) & active_mask[i]),
				.threadIdx(i),
				.blockIdx(blockIdx),
				.blockDim(blockDim),
				.r_data1(reg_data1[i]),
				.r_data2(reg_data2[i]),
				.r_data3(reg_data3[i])
			);
			pc pc_inst(
				.clk(clk),
				.rst(rst),
				.block_rst(pc_block_rst),
				.pc_en(pc_en & active_mask[i]),
				.branch_en(branch_en),
				.branch_offset(branch_offset),
				.call_en(call_en),
				.sret_en(sret_en),
				.sret_target(cs_top_return_pc),
				.nzp_en(nzp_en),
				.nzp_flag(nzp_result[i]),
				.nzp_mask(nzp_mask),
				.pc_out(pc_out[i]),
				.nzp_out(nzp_stored[i])
			);
		end
	endgenerate
	mem_controller #(.THREADS_PER_CORE(THREADS_PER_CORE)) mc(
		.clk(clk),
		.rst(rst),
		.req_valid(lsu_req_valid),
		.req_addr(lsu_req_addr),
		.req_rw(lsu_req_rw),
		.req_data(lsu_req_data),
		.resp_valid(lsu_resp_valid),
		.resp_data(lsu_resp_data),
		.mem_req_valid(data_mem_req_valid),
		.mem_req_addr(data_mem_req_addr),
		.mem_req_rw(data_mem_req_rw),
		.mem_req_data(data_mem_req_data),
		.mem_resp_valid(data_mem_resp_valid),
		.mem_resp_data(data_mem_resp_data)
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
	initial _sv2v_0 = 0;
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
	reg _sv2v_0;
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
	reg running;
	reg [31:0] next_block;
	reg [31:0] completed_blocks;
	reg running_next;
	reg kernel_done_next;
	reg [31:0] next_block_next;
	reg [31:0] completed_blocks_next;
	reg [NUM_CORES - 1:0] core_start_next;
	reg [(NUM_CORES * 32) - 1:0] blockIdx_out_next;
	always @(*) begin
		if (_sv2v_0)
			;
		running_next = running;
		kernel_done_next = kernel_done;
		next_block_next = next_block;
		completed_blocks_next = completed_blocks;
		core_start_next = core_start;
		blockIdx_out_next = blockIdx_out;
		if (dispatch_en && !running) begin
			running_next = 1'b1;
			kernel_done_next = 1'b0;
			next_block_next = 32'd0;
			completed_blocks_next = 32'd0;
			core_start_next = 1'sb0;
			blockIdx_out_next = 1'sb0;
		end
		if (running_next) begin
			begin : sv2v_autoblock_1
				reg signed [31:0] i;
				for (i = 0; i < NUM_CORES; i = i + 1)
					if (core_start_next[i] && block_done[i]) begin
						core_start_next[i] = 1'b0;
						completed_blocks_next = completed_blocks_next + 32'd1;
					end
			end
			begin : sv2v_autoblock_2
				reg signed [31:0] i;
				for (i = 0; i < NUM_CORES; i = i + 1)
					if (!core_start_next[i] && (next_block_next < num_blocks)) begin
						core_start_next[i] = 1'b1;
						blockIdx_out_next[i * 32+:32] = next_block_next;
						next_block_next = next_block_next + 32'd1;
					end
			end
			if (((num_blocks > 0) && (next_block_next == num_blocks)) && (completed_blocks_next == num_blocks)) begin
				running_next = 1'b0;
				kernel_done_next = 1'b1;
				core_start_next = 1'sb0;
			end
		end
		if ((dispatch_en && !running) && (num_blocks == 0)) begin
			running_next = 1'b0;
			kernel_done_next = 1'b1;
			core_start_next = 1'sb0;
		end
	end
	always @(posedge clk or posedge rst)
		if (rst) begin
			running <= 1'b0;
			kernel_done <= 1'b0;
			next_block <= 32'd0;
			completed_blocks <= 32'd0;
			core_start <= 1'sb0;
			blockIdx_out <= 1'sb0;
		end
		else begin
			running <= running_next;
			kernel_done <= kernel_done_next;
			next_block <= next_block_next;
			completed_blocks <= completed_blocks_next;
			core_start <= core_start_next;
			blockIdx_out <= blockIdx_out_next;
		end
	initial _sv2v_0 = 0;
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
	kernel_cycles,
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
	data_mem_resp_data,
	accel_data_req_valid,
	accel_data_req_addr,
	accel_data_req_rw,
	accel_data_req_data,
	accel_data_resp_valid,
	accel_data_resp_data
);
	reg _sv2v_0;
	parameter NUM_CORES = 4;
	parameter THREADS_PER_CORE = 4;
	parameter TOTAL_THREADS = NUM_CORES * THREADS_PER_CORE;
	input wire clk;
	input wire rst;
	input wire dcr_write_en;
	input wire [1:0] dcr_addr;
	input wire [31:0] dcr_data;
	output wire kernel_done;
	output reg [31:0] kernel_cycles;
	output wire [31:0] thread_keep_alive;
	output wire [NUM_CORES - 1:0] prog_mem_req_valid;
	output wire [(NUM_CORES * 32) - 1:0] prog_mem_req_addr;
	input wire [NUM_CORES - 1:0] prog_mem_resp_valid;
	input wire [(NUM_CORES * 32) - 1:0] prog_mem_resp_data;
	output wire [NUM_CORES - 1:0] data_mem_req_valid;
	output wire [(NUM_CORES * 32) - 1:0] data_mem_req_addr;
	output wire [NUM_CORES - 1:0] data_mem_req_rw;
	output wire [(NUM_CORES * 32) - 1:0] data_mem_req_data;
	input wire [NUM_CORES - 1:0] data_mem_resp_valid;
	input wire [(NUM_CORES * 32) - 1:0] data_mem_resp_data;
	output wire accel_data_req_valid;
	output wire [31:0] accel_data_req_addr;
	output wire accel_data_req_rw;
	output wire [31:0] accel_data_req_data;
	input wire accel_data_resp_valid;
	input wire [31:0] accel_data_resp_data;
	wire [31:0] num_blocks;
	wire [31:0] blockDim;
	wire start;
	reg kc_running;
	wire [NUM_CORES - 1:0] core_start;
	wire [(NUM_CORES * 32) - 1:0] blockIdx_out;
	wire [NUM_CORES - 1:0] block_done;
	wire [31:0] core_keep_alive [NUM_CORES - 1:0];
	wire dispatcher_kernel_done;
	reg accel_inflight;
	wire accel_start_write;
	wire accel_done_status;
	wire [NUM_CORES - 1:0] accel_sel;
	reg [NUM_CORES - 1:0] accel_resp_valid_d;
	reg accel_ctrl_wr_valid;
	reg [3:0] accel_ctrl_wr_addr;
	reg [31:0] accel_ctrl_wr_data;
	wire [3:0] accel_ctrl_rd_addr;
	wire [31:0] accel_ctrl_rd_data;
	assign accel_start_write = (accel_ctrl_wr_valid && (accel_ctrl_wr_addr == 4'h7)) && accel_ctrl_wr_data[0];
	assign accel_done_status = accel_ctrl_rd_data[0];
	assign kernel_done = dispatcher_kernel_done && !accel_inflight;
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
		.kernel_done(dispatcher_kernel_done)
	);
	genvar _gv_i_2;
	generate
		for (_gv_i_2 = 0; _gv_i_2 < NUM_CORES; _gv_i_2 = _gv_i_2 + 1) begin : core_gen
			localparam i = _gv_i_2;
			wire [31:0] data_mem_req_addr_wire;
			wire [31:0] data_mem_req_data_wire;
			wire [31:0] data_mem_resp_data_wire;
			wire [31:0] prog_mem_req_addr_wire;
			wire [31:0] prog_mem_resp_data_wire;
			assign prog_mem_req_addr[i * 32+:32] = prog_mem_req_addr_wire;
			assign prog_mem_resp_data_wire = prog_mem_resp_data[i * 32+:32];
			assign data_mem_req_addr[i * 32+:32] = data_mem_req_addr_wire;
			assign data_mem_req_data[i * 32+:32] = data_mem_req_data_wire;
			assign data_mem_resp_data_wire = (accel_resp_valid_d[i] ? accel_ctrl_rd_data : data_mem_resp_data[i * 32+:32]);
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
				.data_mem_req_valid(data_mem_req_valid[i]),
				.data_mem_req_addr(data_mem_req_addr_wire),
				.data_mem_req_rw(data_mem_req_rw[i]),
				.data_mem_req_data(data_mem_req_data_wire),
				.data_mem_resp_valid((accel_resp_valid_d[i] ? 1'b1 : data_mem_resp_valid[i])),
				.data_mem_resp_data(data_mem_resp_data_wire)
			);
		end
	endgenerate
	genvar _gv_n_1;
	generate
		for (_gv_n_1 = 0; _gv_n_1 < NUM_CORES; _gv_n_1 = _gv_n_1 + 1) begin : accel_decode_gen
			localparam n = _gv_n_1;
			assign accel_sel[n] = (data_mem_req_valid[n] && (data_mem_req_addr[n * 32+:32] >= 32'h000001f0)) && (data_mem_req_addr[n * 32+:32] <= 32'h000001ff);
		end
	endgenerate
	always @(posedge clk or posedge rst)
		if (rst)
			accel_resp_valid_d <= 1'sb0;
		else
			accel_resp_valid_d <= accel_sel;
	always @(*) begin
		if (_sv2v_0)
			;
		if (accel_sel[0] && !data_mem_req_rw[0]) begin
			accel_ctrl_wr_valid = 1'b1;
			accel_ctrl_wr_addr = data_mem_req_addr[3-:4];
			accel_ctrl_wr_data = data_mem_req_data[0+:32];
		end
		else if (accel_sel[1] && !data_mem_req_rw[1]) begin
			accel_ctrl_wr_valid = 1'b1;
			accel_ctrl_wr_addr = data_mem_req_addr[35-:4];
			accel_ctrl_wr_data = data_mem_req_data[32+:32];
		end
		else if (accel_sel[2] && !data_mem_req_rw[2]) begin
			accel_ctrl_wr_valid = 1'b1;
			accel_ctrl_wr_addr = data_mem_req_addr[67-:4];
			accel_ctrl_wr_data = data_mem_req_data[64+:32];
		end
		else if (accel_sel[3] && !data_mem_req_rw[3]) begin
			accel_ctrl_wr_valid = 1'b1;
			accel_ctrl_wr_addr = data_mem_req_addr[99-:4];
			accel_ctrl_wr_data = data_mem_req_data[96+:32];
		end
		else begin
			accel_ctrl_wr_valid = 1'b0;
			accel_ctrl_wr_addr = 4'b0000;
			accel_ctrl_wr_data = 32'b00000000000000000000000000000000;
		end
	end
	assign accel_ctrl_rd_addr = (accel_sel[0] && data_mem_req_rw[0] ? data_mem_req_addr[3-:4] : (accel_sel[1] && data_mem_req_rw[1] ? data_mem_req_addr[35-:4] : (accel_sel[2] && data_mem_req_rw[2] ? data_mem_req_addr[67-:4] : (accel_sel[3] && data_mem_req_rw[3] ? data_mem_req_addr[99-:4] : 4'h8))));
	matmul_accelerator accel_inst(
		.clk(clk),
		.rst(rst),
		.ctrl_wr_valid(accel_ctrl_wr_valid),
		.ctrl_wr_addr(accel_ctrl_wr_addr),
		.ctrl_wr_data(accel_ctrl_wr_data),
		.ctrl_rd_addr(accel_ctrl_rd_addr),
		.ctrl_rd_data(accel_ctrl_rd_data),
		.data_req_valid(accel_data_req_valid),
		.data_req_addr(accel_data_req_addr),
		.data_req_rw(accel_data_req_rw),
		.data_req_data(accel_data_req_data),
		.data_resp_valid(accel_data_resp_valid),
		.data_resp_data(accel_data_resp_data)
	);
	always @(posedge clk or posedge rst)
		if (rst)
			accel_inflight <= 1'b0;
		else if (accel_start_write)
			accel_inflight <= 1'b1;
		else if (accel_inflight && accel_done_status)
			accel_inflight <= 1'b0;
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
	always @(posedge clk or posedge rst)
		if (rst) begin
			kc_running <= 1'b0;
			kernel_cycles <= 32'b00000000000000000000000000000000;
		end
		else begin
			if ((start & ~kc_running) & ~kernel_done) begin
				kc_running <= 1'b1;
				kernel_cycles <= 32'b00000000000000000000000000000000;
			end
			else if (kc_running & ~kernel_done)
				kernel_cycles <= kernel_cycles + 1;
			if (kernel_done)
				kc_running <= 1'b0;
		end
	initial _sv2v_0 = 0;
endmodule