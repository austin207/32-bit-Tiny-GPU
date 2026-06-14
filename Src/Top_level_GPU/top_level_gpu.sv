module gpu #(
    parameter NUM_CORES        = 4,
    parameter THREADS_PER_CORE = 4,
    parameter TOTAL_THREADS    = NUM_CORES * THREADS_PER_CORE
) (
    input  logic clk,
    input  logic rst,

    input  logic        dcr_write_en,
    input  logic [1:0]  dcr_addr,
    input  logic [31:0] dcr_data,
    output logic        kernel_done,
    output logic [31:0] kernel_cycles,
    output logic [31:0] thread_keep_alive,

    output logic [NUM_CORES-1:0]       prog_mem_req_valid,
    output logic [31:0]                prog_mem_req_addr  [NUM_CORES-1:0],
    input  logic [NUM_CORES-1:0]       prog_mem_resp_valid,
    input  logic [31:0]                prog_mem_resp_data [NUM_CORES-1:0],

    output logic [NUM_CORES-1:0]       data_mem_req_valid,
    output logic [31:0]                data_mem_req_addr  [NUM_CORES-1:0],
    output logic [NUM_CORES-1:0]       data_mem_req_rw,
    output logic [31:0]                data_mem_req_data  [NUM_CORES-1:0],
    input  logic [NUM_CORES-1:0]       data_mem_resp_valid,
    input  logic [NUM_CORES-1:0][31:0] data_mem_resp_data,

    // ── Phase 4: accelerator matrix data port ────────────────────────────────
    output logic        accel_data_req_valid,
    output logic [31:0] accel_data_req_addr,
    output logic        accel_data_req_rw,
    output logic [31:0] accel_data_req_data,
    input  logic        accel_data_resp_valid,
    input  logic [31:0] accel_data_resp_data
);

// ── DCR / Dispatcher wires ────────────────────────────────────────────────────
logic [31:0] num_blocks;
logic [31:0] blockDim;
logic start;

// ── Kernel cycle counter ──────────────────────────────────────────────────────
logic        kc_running;
logic [NUM_CORES-1:0]       core_start;
logic [NUM_CORES-1:0][31:0] blockIdx_out;
logic [NUM_CORES-1:0]       block_done;

logic [31:0] core_keep_alive [NUM_CORES-1:0];

// ── Dispatcher done gated by accelerator ──────────────────────────────────────
logic dispatcher_kernel_done;
logic accel_inflight;

wire accel_start_write;
wire accel_done_status;

// ── Phase 4: accelerator ctrl signals ─────────────────────────────────────────
// accel_sel[i]          : core i is accessing ctrl reg address space (>= 0x1F0)
// accel_resp_valid_d[i] : 1-cycle delayed ack for core i ctrl reg access
logic [NUM_CORES-1:0] accel_sel;
logic [NUM_CORES-1:0] accel_resp_valid_d;

logic        accel_ctrl_wr_valid;
logic [3:0]  accel_ctrl_wr_addr;   // addr[3:0]: offset 0..8 from 0x1F0
logic [31:0] accel_ctrl_wr_data;
logic [3:0]  accel_ctrl_rd_addr;
logic [31:0] accel_ctrl_rd_data;

// Detect accelerator START write
assign accel_start_write =
    accel_ctrl_wr_valid &&
    (accel_ctrl_wr_addr == 4'h7) &&
    accel_ctrl_wr_data[0];

// accel_ctrl_rd_addr defaults to DONE register when no core is reading.
// So this becomes the real accelerator DONE status after cores RET.
assign accel_done_status = accel_ctrl_rd_data[0];

// Final kernel_done is dispatcher done AND accelerator not still running.
assign kernel_done = dispatcher_kernel_done && !accel_inflight;

// ── DCR ───────────────────────────────────────────────────────────────────────
dcr dcr_inst (
    .clk          (clk),
    .rst          (rst),
    .dcr_write_en (dcr_write_en),
    .dcr_addr     (dcr_addr),
    .dcr_data     (dcr_data),
    .num_blocks   (num_blocks),
    .blockDim     (blockDim),
    .start        (start)
);

// ── Dispatcher ────────────────────────────────────────────────────────────────
dispatcher dispatcher_inst (
    .clk          (clk),
    .rst          (rst),
    .dispatch_en  (start),
    .num_blocks   (num_blocks),
    .blockDim     (blockDim),
    .block_done   (block_done),
    .core_start   (core_start),
    .blockIdx_out (blockIdx_out),
    .kernel_done  (dispatcher_kernel_done)
);

// ── Cores ─────────────────────────────────────────────────────────────────────
genvar i;
generate
    for (i = 0; i < NUM_CORES; i = i + 1) begin : core_gen
        logic [31:0] data_mem_req_addr_wire;
        logic [31:0] data_mem_req_data_wire;
        logic [31:0] data_mem_resp_data_wire;
        logic [31:0] prog_mem_req_addr_wire;
        logic [31:0] prog_mem_resp_data_wire;

        assign prog_mem_req_addr[i]    = prog_mem_req_addr_wire;
        assign prog_mem_resp_data_wire = prog_mem_resp_data[i];
        assign data_mem_req_addr[i]    = data_mem_req_addr_wire;
        assign data_mem_req_data[i]    = data_mem_req_data_wire;

        // ── Phase 4: response mux ─────────────────────────────────────────────
        // When accel_resp_valid_d[i]=1, serve ctrl reg read data instead of
        // external data_mem response. External resp is ignored for that cycle.
        assign data_mem_resp_data_wire = accel_resp_valid_d[i]
                                         ? accel_ctrl_rd_data
                                         : data_mem_resp_data[i];

        core #(.THREADS_PER_CORE(THREADS_PER_CORE)) core_inst (
            .clk                (clk),
            .rst                (rst),
            .core_start         (core_start[i]),
            .blockIdx           (blockIdx_out[i]),
            .blockDim           (blockDim),
            .block_done         (block_done[i]),
            .thread_keep_alive  (core_keep_alive[i]),
            .prog_mem_req_valid (prog_mem_req_valid[i]),
            .prog_mem_req_addr  (prog_mem_req_addr_wire),
            .prog_mem_resp_valid(prog_mem_resp_valid[i]),
            .prog_mem_resp_data (prog_mem_resp_data_wire),
            .data_mem_req_valid (data_mem_req_valid[i]),
            .data_mem_req_addr  (data_mem_req_addr_wire),
            .data_mem_req_rw    (data_mem_req_rw[i]),
            .data_mem_req_data  (data_mem_req_data_wire),

            // mux: accel ctrl ack OR external data_mem ack
            .data_mem_resp_valid(accel_resp_valid_d[i]
                                 ? 1'b1
                                 : data_mem_resp_valid[i]),
            .data_mem_resp_data (data_mem_resp_data_wire)
        );
    end
endgenerate

// ── Phase 4: address decode — which cores are accessing ctrl reg space ────────
genvar n;
generate
    for (n = 0; n < NUM_CORES; n = n + 1) begin : accel_decode_gen
        assign accel_sel[n] = data_mem_req_valid[n] &&
                              (data_mem_req_addr[n] >= 32'h1F0);
    end
endgenerate

// 1-cycle delayed ctrl ack
always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        accel_resp_valid_d <= '0;
    end else begin
        accel_resp_valid_d <= accel_sel;
    end
end

// ── Phase 4: ctrl write port — priority to lowest-index writing core ──────────
// All cores write identical param values; last-write-wins does not matter.
always_comb begin
    if (accel_sel[0] && !data_mem_req_rw[0]) begin
        accel_ctrl_wr_valid = 1'b1;
        accel_ctrl_wr_addr  = data_mem_req_addr[0][3:0];
        accel_ctrl_wr_data  = data_mem_req_data[0];
    end else if (accel_sel[1] && !data_mem_req_rw[1]) begin
        accel_ctrl_wr_valid = 1'b1;
        accel_ctrl_wr_addr  = data_mem_req_addr[1][3:0];
        accel_ctrl_wr_data  = data_mem_req_data[1];
    end else if (accel_sel[2] && !data_mem_req_rw[2]) begin
        accel_ctrl_wr_valid = 1'b1;
        accel_ctrl_wr_addr  = data_mem_req_addr[2][3:0];
        accel_ctrl_wr_data  = data_mem_req_data[2];
    end else if (accel_sel[3] && !data_mem_req_rw[3]) begin
        accel_ctrl_wr_valid = 1'b1;
        accel_ctrl_wr_addr  = data_mem_req_addr[3][3:0];
        accel_ctrl_wr_data  = data_mem_req_data[3];
    end else begin
        accel_ctrl_wr_valid = 1'b0;
        accel_ctrl_wr_addr  = 4'b0;
        accel_ctrl_wr_data  = 32'b0;
    end
end

// ── Phase 4: ctrl read addr — pick lowest-index reading core ─────────────────
// All polling cores read DONE at addr 0x1F8, offset 8.
// If no core is reading, default to DONE register.
assign accel_ctrl_rd_addr =
    (accel_sel[0] && data_mem_req_rw[0]) ? data_mem_req_addr[0][3:0] :
    (accel_sel[1] && data_mem_req_rw[1]) ? data_mem_req_addr[1][3:0] :
    (accel_sel[2] && data_mem_req_rw[2]) ? data_mem_req_addr[2][3:0] :
    (accel_sel[3] && data_mem_req_rw[3]) ? data_mem_req_addr[3][3:0] :
    4'h8;

// ── Phase 4: matmul accelerator instance ─────────────────────────────────────
matmul_accelerator accel_inst (
    .clk            (clk),
    .rst            (rst),
    .ctrl_wr_valid  (accel_ctrl_wr_valid),
    .ctrl_wr_addr   (accel_ctrl_wr_addr),
    .ctrl_wr_data   (accel_ctrl_wr_data),
    .ctrl_rd_addr   (accel_ctrl_rd_addr),
    .ctrl_rd_data   (accel_ctrl_rd_data),
    .data_req_valid (accel_data_req_valid),
    .data_req_addr  (accel_data_req_addr),
    .data_req_rw    (accel_data_req_rw),
    .data_req_data  (accel_data_req_data),
    .data_resp_valid(accel_data_resp_valid),
    .data_resp_data (accel_data_resp_data)
);

// ── Accelerator inflight tracker ──────────────────────────────────────────────
// This prevents top-level kernel_done from asserting before accelerator has
// finished writing the full C matrix.
always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        accel_inflight <= 1'b0;
    end else begin
        if (accel_start_write) begin
            accel_inflight <= 1'b1;
        end else if (accel_inflight && accel_done_status) begin
            accel_inflight <= 1'b0;
        end
    end
end

// ── thread_keep_alive: XOR of all core keep_alive signals ────────────────────
genvar m;
logic [31:0] _top_keep_xor [NUM_CORES:0];
assign _top_keep_xor[0] = 32'b0;

generate
    for (m = 0; m < NUM_CORES; m++) begin : top_keep_xor_gen
        assign _top_keep_xor[m+1] = _top_keep_xor[m] ^ core_keep_alive[m];
    end
endgenerate

assign thread_keep_alive = _top_keep_xor[NUM_CORES];

// ── Kernel cycle counter ──────────────────────────────────────────────────────
always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        kc_running    <= 1'b0;
        kernel_cycles <= 32'b0;
    end else begin
        if (start & ~kc_running & ~kernel_done) begin
            kc_running    <= 1'b1;
            kernel_cycles <= 32'b0;
        end else if (kc_running & ~kernel_done) begin
            kernel_cycles <= kernel_cycles + 1;
        end

        if (kernel_done) begin
            kc_running <= 1'b0;
        end
    end
end

endmodule