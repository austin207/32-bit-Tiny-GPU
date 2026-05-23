module core #(
    parameter THREADS_PER_CORE = 4
) (
    input logic clk,
    input logic rst,
    input logic core_start,
    input logic [31:0] blockIdx,
    input logic [31:0] blockDim,

    output logic block_done,

    output logic prog_mem_req_valid,
    output logic [31:0] prog_mem_req_addr,

    input logic prog_mem_resp_valid,
    input logic [31:0] prog_mem_resp_data,

    output logic [THREADS_PER_CORE-1:0] data_mem_req_valid,
    output logic [31:0] data_mem_req_addr [THREADS_PER_CORE-1:0],
    output logic [THREADS_PER_CORE-1:0] data_mem_req_rw,
    output logic [31:0] data_mem_req_data [THREADS_PER_CORE-1:0],

    input logic [THREADS_PER_CORE-1:0] data_mem_resp_valid,
    input logic [31:0] data_mem_resp_data [THREADS_PER_CORE-1:0]
);

// Scheduler outputs
logic fetcher_en, lsu_en, execute_en, write_back_en_sched, pc_en;
logic [2:0] current_state;

// Fetcher outputs
logic [31:0] instruction;
logic done;
logic [31:0] req_addr;
logic req_valid;

// Decoder outputs
logic [5:0] opcode;
logic [4:0] rd_addr, rs1_addr, rs2_addr, rs3_addr;
logic [15:0] imm;
logic [2:0] nzp_mask;
logic [22:0] branch_offset;
logic ret, write_back_en_dec, mem_read_en, mem_write_en, branch_en, nzp_en;

// Per Thread arrays
logic [31:0] alu_result [THREADS_PER_CORE-1:0];
logic [2:0] nzp_result [THREADS_PER_CORE-1:0];
logic [THREADS_PER_CORE-1:0] lsu_done;
logic [31:0] lsu_read_data [THREADS_PER_CORE-1:0];
logic [31:0] reg_data1 [THREADS_PER_CORE-1:0];
logic [31:0] reg_data2 [THREADS_PER_CORE-1:0];
logic [31:0] reg_data3 [THREADS_PER_CORE-1:0];
logic [31:0] pc_out [THREADS_PER_CORE-1:0];

logic [31:0] mem_addr [THREADS_PER_CORE-1:0];

scheduler #(
    .THREADS_PER_CORE(THREADS_PER_CORE)
) shed (
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

fetcher fetch (
    .clk(clk),
    .rst(rst),
    .core_en(fetcher_en),
    .pc_value(pc_out[0]),
    .instruction(instruction),
    .done(done),
    .req_valid(prog_mem_req_valid),
    .req_addr(prog_mem_req_addr),
    .resp_valid(prog_mem_resp_valid),
    .resp_data(prog_mem_resp_data)
);

decoder dec (
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

genvar i;
logic [31:0] write_data [THREADS_PER_CORE-1:0];

generate
    for (i = 0; i < THREADS_PER_CORE; i++) begin : thread_gen

        assign mem_addr[i] = reg_data1[i] + {{16{imm[15]}}, imm};
        assign write_data[i] = mem_read_en        ? lsu_read_data[i]  :
                       (opcode == 6'h11)  ? {16'b0, imm}      :
                       alu_result[i];

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
            .req_addr(data_mem_req_addr[i]),
            .read_write_switch(data_mem_req_rw[i]),
            .write_data(data_mem_req_data[i]),
            .resp_valid(data_mem_resp_valid[i]),
            .resp_data(data_mem_resp_data[i]),
            .done(lsu_done[i]),
            .mem_read_data(lsu_read_data[i])
        );

        pc pc_inst(
            .clk(clk),
            .rst(rst),
            .pc_en(pc_en),
            .branch_en(branch_en),
            .branch_offset(branch_offset),
            .nzp_en(nzp_en),
            .nzp_flag(nzp_result[i]),
            .nzp_mask(nzp_mask),
            .pc_out(pc_out[i])
        );

        registers reg_file (
            .clk(clk),
            .rst(rst),
            .w_addr(rd_addr),
            .r_addr1(rs1_addr),
            .r_addr2(rs2_addr),
            .r_addr3(mem_write_en ? rd_addr : rs3_addr),
            .w_data(write_data[i]),
            .w_en(write_back_en_sched),
            .threadIdx(32'(i)),
            .blockIdx(blockIdx),
            .blockDim(blockDim),
            .r_data1(reg_data1[i]),
            .r_data2(reg_data2[i]),
            .r_data3(reg_data3[i])
        );
    end
endgenerate

endmodule