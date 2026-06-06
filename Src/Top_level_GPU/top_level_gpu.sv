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

    output logic [NUM_CORES-1:0]   data_mem_req_valid,
    output logic [31:0]                data_mem_req_addr  [NUM_CORES-1:0],
    output logic [NUM_CORES-1:0]   data_mem_req_rw,
    output logic [31:0]                data_mem_req_data  [NUM_CORES-1:0],
    input  logic [NUM_CORES-1:0]   data_mem_resp_valid,
    input  logic [NUM_CORES-1:0][31:0] data_mem_resp_data
);

// ── DCR / Dispatcher wires ───────────────────────────────────────────────────
logic [31:0] num_blocks;
logic [31:0] blockDim;
logic start;
// ── Kernel cycle counter ──────────────────────────────────────────────────────
logic        kc_running;
logic [NUM_CORES-1:0]       core_start;
logic [NUM_CORES-1:0][31:0] blockIdx_out;
logic [NUM_CORES-1:0]       block_done;

// Per-core thread_keep_alive; XOR-reduced to single top-level output.
logic [31:0] core_keep_alive [NUM_CORES-1:0];

// ── DCR ──────────────────────────────────────────────────────────────────────
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

// ── Dispatcher ───────────────────────────────────────────────────────────────
dispatcher dispatcher_inst (
    .clk          (clk),
    .rst          (rst),
    .dispatch_en  (start),
    .num_blocks   (num_blocks),
    .blockDim     (blockDim),
    .block_done   (block_done),
    .core_start   (core_start),
    .blockIdx_out (blockIdx_out),
    .kernel_done  (kernel_done)
);

// ── Cores ────────────────────────────────────────────────────────────────────
genvar i;

generate
    for (i = 0; i < NUM_CORES; i = i + 1) begin : core_gen
        logic [31:0] data_mem_req_addr_wire;
        logic [31:0] data_mem_req_data_wire;
        logic [31:0] data_mem_resp_data_wire;
        logic [31:0]                 prog_mem_req_addr_wire;
        logic [31:0]                 prog_mem_resp_data_wire;

        assign prog_mem_req_addr[i]    = prog_mem_req_addr_wire;
        assign prog_mem_resp_data_wire = prog_mem_resp_data[i];
        assign data_mem_req_addr[i]    = data_mem_req_addr_wire;
        assign data_mem_req_data[i]    = data_mem_req_data_wire;
        assign data_mem_resp_data_wire = data_mem_resp_data[i];

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
            .data_mem_resp_valid(data_mem_resp_valid[i]),
            .data_mem_resp_data (data_mem_resp_data_wire)
        );
    end
endgenerate

// ── thread_keep_alive: XOR of all core keep_alive signals ───────────────────
// Parameterized generate chain so it works for any NUM_CORES.
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
// kc_running sets on the start pulse and clears when kernel_done asserts.
// kernel_cycles increments every cycle while running.
// Both reset to 0 on rst so back-to-back launches restart cleanly.
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