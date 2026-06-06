module core #(
    parameter THREADS_PER_CORE = 4
) (
    input  logic clk,
    input  logic rst,
    input  logic core_start,
    input  logic [31:0] blockIdx,
    input  logic [31:0] blockDim,

    output logic block_done,
    output logic [31:0] thread_keep_alive,

    output logic        prog_mem_req_valid,
    output logic [31:0] prog_mem_req_addr,
    input  logic        prog_mem_resp_valid,
    input  logic [31:0] prog_mem_resp_data,

    output logic        data_mem_req_valid,
    output logic [31:0] data_mem_req_addr,
    output logic        data_mem_req_rw,
    output logic [31:0] data_mem_req_data,
    input  logic        data_mem_resp_valid,
    input  logic [31:0] data_mem_resp_data
);

// ── Scheduler outputs ────────────────────────────────────────────────────────
logic fetcher_en, lsu_en, execute_en, write_back_en_sched, pc_en;
logic [3:0] current_state;

// ── Fetcher outputs ──────────────────────────────────────────────────────────
logic [31:0] instruction_raw;
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
logic [THREADS_PER_CORE-1:0] lsu_done_latch;
logic [THREADS_PER_CORE-1:0] lsu_done;

(* syn_keep=1 *) logic [31:0] lsu_read_data [THREADS_PER_CORE-1:0];
(* syn_keep=1 *) logic [31:0] reg_data1     [THREADS_PER_CORE-1:0];
(* syn_keep=1 *) logic [31:0] reg_data2     [THREADS_PER_CORE-1:0];
(* syn_keep=1 *) logic [31:0] reg_data3     [THREADS_PER_CORE-1:0];
(* syn_keep=1 *) logic [31:0] mem_addr      [THREADS_PER_CORE-1:0];

// LSU array → internal memory controller wires
logic [THREADS_PER_CORE-1:0] lsu_req_valid;
logic [31:0]                 lsu_req_addr [THREADS_PER_CORE-1:0];
logic [THREADS_PER_CORE-1:0] lsu_req_rw;
logic [31:0]                 lsu_req_data [THREADS_PER_CORE-1:0];

logic [THREADS_PER_CORE-1:0]        lsu_resp_valid;
logic [THREADS_PER_CORE-1:0][31:0]  lsu_resp_data;

// ── Active mask + PC ─────────────────────────────────────────────────────────
logic [31:0] pc_out [THREADS_PER_CORE-1:0];
logic [THREADS_PER_CORE-1:0] active_mask;
logic [2:0] nzp_stored [THREADS_PER_CORE-1:0];

logic divergence_detected;
logic [THREADS_PER_CORE-1:0] taken_mask;

logic pc_block_rst;
assign pc_block_rst = (current_state == 4'b0000) && core_start;

// ── IMPORTANT FIX:
// Fetcher output may only be valid around fetch completion.
// Latch the fetched instruction and decode the latched copy through the full
// DECODE / REQUEST / WAIT / EXECUTE / UPDATE sequence.
always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        instruction <= 32'b0;
    end else if (done) begin
        instruction <= instruction_raw;
    end
end

// ── LSU done latch ───────────────────────────────────────────────────────────
// IMPORTANT:
// lsu_done_latch must be cleared before every new memory instruction.
// Clearing only on lsu_en is too late for back-to-back LDRs: the scheduler can
// see stale all-done bits from the previous LDR and leave WAIT early.
//
// We clear when a newly fetched instruction is a LOAD/STORE, using
// instruction_raw because instruction is updated from instruction_raw on the
// same clock edge.
always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        lsu_done_latch <= '0;
    end else begin
        if (done && ((instruction_raw[31:26] == 6'h0F) ||
                     (instruction_raw[31:26] == 6'h10))) begin
            // New LDR/STR fetched: clear stale completion bits immediately.
            lsu_done_latch <= '0;
        end else if (lsu_en) begin
            // Memory request launch: also clear defensively.
            lsu_done_latch <= '0;
        end else begin
            // Accumulate completions from the active memory instruction.
            for (int i = 0; i < THREADS_PER_CORE; i++) begin
                if (lsu_done_raw[i]) begin
                    lsu_done_latch[i] <= 1'b1;
                end
            end
        end
    end
end

assign lsu_done = lsu_done_latch | ~active_mask;

// ── Branch/divergence detection ──────────────────────────────────────────────
always_comb begin
    for (int i = 0; i < THREADS_PER_CORE; i++) begin
        taken_mask[i] =
            branch_en &&
            active_mask[i] &&
            ((nzp_stored[i] & nzp_mask) != 3'b000);
    end

    divergence_detected =
        branch_en &&
        (taken_mask != active_mask) &&
        (taken_mask != '0);
end

logic [31:0] active_pc;

always_comb begin
    active_pc = pc_out[0];

    for (int i = THREADS_PER_CORE - 1; i >= 0; i--) begin
        if (active_mask[i]) begin
            active_pc = pc_out[i];
        end
    end
end

logic [31:0] sync_pc;
assign sync_pc = active_pc + {21'b0, sync_offset};

// ── Warp stack wires ─────────────────────────────────────────────────────────
logic ws_push, ws_pop;
logic [31:0] ws_top_sync_pc;
logic [THREADS_PER_CORE-1:0] ws_top_saved_mask;
logic ws_stack_empty, ws_stack_full, ws_stack_overflow;

assign ws_push = (current_state == 4'b0111);
assign ws_pop  = (current_state == 4'b1000);

// ── Scheduler ────────────────────────────────────────────────────────────────
scheduler #(
    .THREADS_PER_CORE(THREADS_PER_CORE)
) shed (
    .clk                 (clk),
    .rst                 (rst),
    .core_start          (core_start),
    .fetcher_done        (done),
    .lsu_done            (lsu_done),
    .mem_read_en         (mem_read_en),
    .mem_write_en        (mem_write_en),
    .ret                 (ret),
    .divergence_detected (divergence_detected),
    .taken_mask          (taken_mask),
    .sync_en             (sync_en),
    .saved_mask          (ws_stack_empty ? {THREADS_PER_CORE{1'b1}} : ws_top_saved_mask),

    .fetcher_en          (fetcher_en),
    .lsu_en              (lsu_en),
    .execute_en          (execute_en),
    .write_back_en       (write_back_en_sched),
    .current_state       (current_state),
    .active_mask         (active_mask),
    .block_done          (block_done),
    .pc_en               (pc_en)
);

// ── Warp Stack ───────────────────────────────────────────────────────────────
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

// ── Fetcher ──────────────────────────────────────────────────────────────────
fetcher fetch (
    .clk         (clk),
    .rst         (rst),
    .core_en     (fetcher_en),
    .pc_value    (active_pc),
    .instruction (instruction_raw),
    .done        (done),
    .req_valid   (prog_mem_req_valid),
    .req_addr    (prog_mem_req_addr),
    .resp_valid  (prog_mem_resp_valid),
    .resp_data   (prog_mem_resp_data)
);

// ── Decoder ──────────────────────────────────────────────────────────────────
decoder dec (
    .instruction   (instruction),
    .opcode        (opcode),
    .rd_addr       (rd_addr),
    .rs1_addr      (rs1_addr),
    .rs2_addr      (rs2_addr),
    .rs3_addr      (rs3_addr),
    .imm           (imm),
    .nzp_mask      (nzp_mask),
    .sync_offset   (sync_offset),
    .branch_offset (branch_offset),
    .sync_en       (sync_en),

    .ret           (ret),
    .write_back_en (write_back_en_dec),
    .mem_read_en   (mem_read_en),
    .mem_write_en  (mem_write_en),
    .branch_en     (branch_en),
    .nzp_en        (nzp_en)
);

// ── Per-thread generate: ALU, LSU, Register File, PC ─────────────────────────
genvar i;
(* syn_keep=1 *) logic [31:0] write_data [THREADS_PER_CORE-1:0];

generate
    for (i = 0; i < THREADS_PER_CORE; i++) begin : thread_gen

        assign mem_addr[i] = reg_data1[i] + {{16{imm[15]}}, imm};

        assign write_data[i] =
            mem_read_en        ? lsu_read_data[i] :
            (opcode == 6'h11)  ? {16'b0, imm}     :
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
            .clk               (clk),
            .rst               (rst),
            .core_en           (lsu_en & active_mask[i]),
            .done              (lsu_done_raw[i]),
            .mem_data_address  (mem_addr[i]),

            .req_valid         (lsu_req_valid[i]),
            .req_addr          (lsu_req_addr[i]),
            .write_data        (lsu_req_data[i]),
            .resp_valid        (lsu_resp_valid[i]),
            .resp_data         (lsu_resp_data[i]),

            .mem_write_en      (mem_write_en),
            .mem_write_data    (reg_data3[i]),
            .mem_read_en       (mem_read_en),
            .mem_read_data     (lsu_read_data[i]),

            .read_write_switch (lsu_req_rw[i])
        );

        registers reg_file (
            .clk       (clk),
            .rst       (rst),
            .r_addr1   (rs1_addr),
            .r_addr2   (rs2_addr),
            .r_addr3   (mem_write_en ? rd_addr : rs3_addr),
            .w_addr    (rd_addr),
            .w_data    (write_data[i]),

            // IMPORTANT FIX:
            // Scheduler says "this is UPDATE".
            // Decoder says "this instruction actually writes a register".
            .w_en      (write_back_en_sched & write_back_en_dec & active_mask[i]),

            .threadIdx (32'(i)),
            .blockIdx  (blockIdx),
            .blockDim  (blockDim),
            .r_data1   (reg_data1[i]),
            .r_data2   (reg_data2[i]),
            .r_data3   (reg_data3[i])
        );

        pc pc_inst (
            .clk           (clk),
            .rst           (rst),
            .block_rst     (pc_block_rst),
            .pc_en         (pc_en & active_mask[i]),
            .branch_en     (branch_en),
            .branch_offset (branch_offset),
            .nzp_en        (nzp_en),
            .nzp_flag      (nzp_result[i]),
            .nzp_mask      (nzp_mask),
            .pc_out        (pc_out[i]),
            .nzp_out       (nzp_stored[i])
        );

    end
endgenerate

// ── Memory controller ────────────────────────────────────────────────────────
mem_controller #(
    .THREADS_PER_CORE(THREADS_PER_CORE)
) mc (
    .clk            (clk),
    .rst            (rst),

    .req_valid      (lsu_req_valid),
    .req_addr       (lsu_req_addr),
    .req_rw         (lsu_req_rw),
    .req_data       (lsu_req_data),
    .resp_valid     (lsu_resp_valid),
    .resp_data      (lsu_resp_data),

    .mem_req_valid  (data_mem_req_valid),
    .mem_req_addr   (data_mem_req_addr),
    .mem_req_rw     (data_mem_req_rw),
    .mem_req_data   (data_mem_req_data),
    .mem_resp_valid (data_mem_resp_valid),
    .mem_resp_data  (data_mem_resp_data)
);

// ── thread_keep_alive XOR reduction ─────────────────────────────────────────
genvar k;
logic [31:0] _keep_xor [THREADS_PER_CORE:0];

assign _keep_xor[0] = 32'b0;

generate
    for (k = 0; k < THREADS_PER_CORE; k++) begin : keep_xor_gen
        assign _keep_xor[k + 1] = _keep_xor[k] ^ write_data[k];
    end
endgenerate

assign thread_keep_alive = _keep_xor[THREADS_PER_CORE];

endmodule