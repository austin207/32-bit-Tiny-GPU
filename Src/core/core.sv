module core #(
    parameter THREADS_PER_CORE = 4
) (
    input  logic clk,
    input  logic rst,
    input  logic core_start,
    input  logic [31:0] blockIdx,
    input  logic [31:0] blockDim,

    output logic block_done,

    // thread_keep_alive: XOR of all thread write_data signals.
    // Forces every thread's ALU and register file into the synthesis
    // backward-analysis chain when connected to a primary output (LED).
    // Without this, synthesis tools sweep threads 1-3 as dead logic on
    // single-output designs (e.g. FPGA wrapper that only exposes kernel_done).
    output logic [31:0] thread_keep_alive,

    output logic        prog_mem_req_valid,
    output logic [31:0] prog_mem_req_addr,
    input  logic        prog_mem_resp_valid,
    input  logic [31:0] prog_mem_resp_data,

    output logic [THREADS_PER_CORE-1:0] data_mem_req_valid,
    output logic [31:0] data_mem_req_addr [THREADS_PER_CORE-1:0],
    output logic [THREADS_PER_CORE-1:0] data_mem_req_rw,
    output logic [31:0] data_mem_req_data [THREADS_PER_CORE-1:0],

    input  logic [THREADS_PER_CORE-1:0] data_mem_resp_valid,
    input  logic [31:0] data_mem_resp_data [THREADS_PER_CORE-1:0]
);

logic divergence_detected;
logic [THREADS_PER_CORE-1:0] taken_mask;
logic [2:0] nzp_stored [THREADS_PER_CORE-1:0];

always_comb begin
    for (int i = 0; i < THREADS_PER_CORE; i++) begin
        taken_mask[i] = branch_en & ((nzp_stored[i] & nzp_mask) != 3'b000) & active_mask[i];
    end

    divergence_detected = branch_en & (taken_mask != active_mask) & (taken_mask != '0);
end

// ── Scheduler outputs ────────────────────────────────────────────────────────
logic fetcher_en, lsu_en, execute_en, write_back_en_sched, pc_en;
logic [3:0] current_state;

// ── Fetcher outputs ──────────────────────────────────────────────────────────
logic [31:0] instruction;
logic done;
logic [31:0] req_addr;
logic req_valid;

// ── Decoder outputs ──────────────────────────────────────────────────────────
logic [5:0]  opcode;
logic [4:0]  rd_addr, rs1_addr, rs2_addr, rs3_addr;
logic [15:0] imm;
logic [2:0]  nzp_mask;
logic [10:0] sync_offset;
logic [11:0] branch_offset;
logic ret, write_back_en_dec, mem_read_en, mem_write_en, branch_en, nzp_en, sync_en;

// ── Per-thread arrays ────────────────────────────────────────────────────────
(* syn_keep=1 *) logic [31:0] alu_result    [THREADS_PER_CORE-1:0];
(* syn_keep=1 *) logic [2:0]  nzp_result    [THREADS_PER_CORE-1:0];
                 logic [THREADS_PER_CORE-1:0] lsu_done_raw;
                 logic [THREADS_PER_CORE-1:0] lsu_done;
                 assign lsu_done = lsu_done_raw | ~active_mask;
(* syn_keep=1 *) logic [31:0] lsu_read_data [THREADS_PER_CORE-1:0];
(* syn_keep=1 *) logic [31:0] reg_data1     [THREADS_PER_CORE-1:0];
(* syn_keep=1 *) logic [31:0] reg_data2     [THREADS_PER_CORE-1:0];
(* syn_keep=1 *) logic [31:0] reg_data3     [THREADS_PER_CORE-1:0];
(* syn_keep=1 *) logic [31:0] mem_addr      [THREADS_PER_CORE-1:0];

// Shared PC — single instance for all threads (SIMD).
logic [31:0] pc_out [THREADS_PER_CORE-1:0];
logic [THREADS_PER_CORE-1:0] active_mask;

// pc_block_rst: resets PC to 0 at the start of each new block.
// Fires when scheduler is in IDLE (3'b000) and core_start pulses (IDLE→FETCH).
// Ensures block N+1 fetches from instruction 0, not block N's RET address.
logic pc_block_rst;
assign pc_block_rst = (current_state == 4'b0000) && core_start;

// ── Scheduler ────────────────────────────────────────────────────────────────
scheduler #(
    .THREADS_PER_CORE(THREADS_PER_CORE)
) shed (
    .clk          (clk),
    .rst          (rst),
    .core_start   (core_start),
    .fetcher_done (done),
    .lsu_done     (lsu_done),
    .mem_read_en  (mem_read_en),
    .mem_write_en (mem_write_en),
    .ret          (ret),
    .fetcher_en   (fetcher_en),
    .lsu_en       (lsu_en),
    .execute_en   (execute_en),
    .write_back_en(write_back_en_sched),
    .current_state(current_state),
    .block_done   (block_done),
    .pc_en        (pc_en),
    .divergence_detected(divergence_detected),
    .taken_mask(taken_mask),
    .active_mask(active_mask),
    .sync_en(sync_en),
    .saved_mask(ws_stack_empty ? {THREADS_PER_CORE{1'b1}} : ws_top_saved_mask)
);

logic [31:0] active_pc;

always_comb begin
    active_pc = pc_out[0];
    for (int i = THREADS_PER_CORE-1; i >= 0; i--) begin
        if (active_mask[i]) begin
            active_pc = pc_out[i];
        end
    end
end

logic [31:0] sync_pc;
assign sync_pc = active_pc + {21'b0, sync_offset};

// ── Warp Stack ───────────────────────────────────────────────────────────────
logic ws_push, ws_pop;
logic [31:0] ws_top_sync_pc;
logic [THREADS_PER_CORE-1:0] ws_top_saved_mask;
logic ws_stack_empty, ws_stack_full, ws_stack_overflow;

assign ws_push = (current_state == 4'b0111);
assign ws_pop  = (current_state == 4'b1000);

warp_stack #(
    .THREADS_PER_CORE(THREADS_PER_CORE)
) ws (
    .clk             (clk),
    .rst             (rst),
    .push            (ws_push),
    .push_sync_pc    (sync_pc),
    .push_saved_mask (~taken_mask & active_mask),
    .pop             (ws_pop),
    .top_sync_pc     (ws_top_sync_pc),
    .top_saved_mask  (ws_top_saved_mask),
    .stack_empty     (ws_stack_empty),
    .stack_full      (ws_stack_full),
    .stack_overflow  (ws_stack_overflow)
);

// ── Fetcher ──────────────────────────────────────────────────────────
fetcher fetch (
    .clk         (clk),
    .rst         (rst),
    .core_en     (fetcher_en),
    .pc_value    (active_pc),
    .instruction (instruction),
    .done        (done),
    .req_valid   (prog_mem_req_valid),
    .req_addr    (prog_mem_req_addr),
    .resp_valid  (prog_mem_resp_valid),
    .resp_data   (prog_mem_resp_data)
);

// ── Decoder ──────────────────────────────────────────────────────────────────
decoder dec (
    .instruction  (instruction),
    .opcode       (opcode),
    .rd_addr      (rd_addr),
    .rs1_addr     (rs1_addr),
    .rs2_addr     (rs2_addr),
    .rs3_addr     (rs3_addr),
    .imm          (imm),
    .nzp_mask     (nzp_mask),
    .sync_offset  (sync_offset),
    .branch_offset(branch_offset),
    .ret          (ret),
    .write_back_en(write_back_en_dec),
    .mem_read_en  (mem_read_en),
    .mem_write_en (mem_write_en),
    .branch_en    (branch_en),
    .nzp_en       (nzp_en),
    .sync_en      (sync_en)
);

// ── Per-thread generate: ALU, LSU, Register File, PC ─────────────────────────────
genvar i;
(* syn_keep=1 *) logic [31:0] write_data [THREADS_PER_CORE-1:0];

generate
    for (i = 0; i < THREADS_PER_CORE; i++) begin : thread_gen

        assign mem_addr[i]   = reg_data1[i] + {{16{imm[15]}}, imm};

        assign write_data[i] = mem_read_en       ? lsu_read_data[i]  :
                               (opcode == 6'h11) ? {16'b0, imm}      :
                               alu_result[i];

        alu alu_inst (
            .operand1  (reg_data1[i]),
            .operand2  (reg_data2[i]),
            .operand3  (reg_data3[i]),
            .op_select (opcode),
            .result    (alu_result[i]),
            .nzp_flag  (nzp_result[i])
        );

        lsu lsu_inst (
            .clk              (clk),
            .rst              (rst),
            .core_en          (lsu_en & active_mask[i]),
            .mem_read_en      (mem_read_en),
            .mem_write_en     (mem_write_en),
            .mem_data_address (mem_addr[i]),
            .mem_write_data   (reg_data3[i]),
            .req_valid        (data_mem_req_valid[i]),
            .req_addr         (data_mem_req_addr[i]),
            .read_write_switch(data_mem_req_rw[i]),
            .write_data       (data_mem_req_data[i]),
            .resp_valid       (data_mem_resp_valid[i]),
            .resp_data        (data_mem_resp_data[i]),
            .done             (lsu_done_raw[i]),
            .mem_read_data    (lsu_read_data[i])
        );

        registers reg_file (
            .clk      (clk),
            .rst      (rst),
            .w_addr   (rd_addr),
            .r_addr1  (rs1_addr),
            .r_addr2  (rs2_addr),
            .r_addr3  (mem_write_en ? rd_addr : rs3_addr),
            .w_data   (write_data[i]),
            .w_en     (write_back_en_sched & active_mask[i]),
            .threadIdx(32'(i)),
            .blockIdx (blockIdx),
            .blockDim (blockDim),
            .r_data1  (reg_data1[i]),
            .r_data2  (reg_data2[i]),
            .r_data3  (reg_data3[i])
        );

        pc pc_inst (
            .clk          (clk),
            .rst          (rst),
            .block_rst    (pc_block_rst),
            .pc_en        (pc_en & active_mask[i]),
            .branch_en    (branch_en),
            .branch_offset(branch_offset),
            .nzp_en       (nzp_en),
            .nzp_flag     (nzp_result[i]),   // each thread uses its own NZP
            .nzp_mask     (nzp_mask),
            .pc_out       (pc_out[i]),
            .nzp_out      (nzp_stored[i])
        );
    end
endgenerate

// ── thread_keep_alive: XOR reduction across all thread write_data ────────────
genvar k;
logic [31:0] _keep_xor [THREADS_PER_CORE:0];
assign _keep_xor[0] = 32'b0;
generate
    for (k = 0; k < THREADS_PER_CORE; k++) begin : keep_xor_gen
        assign _keep_xor[k+1] = _keep_xor[k] ^ write_data[k];
    end
endgenerate
assign thread_keep_alive = _keep_xor[THREADS_PER_CORE];

endmodule