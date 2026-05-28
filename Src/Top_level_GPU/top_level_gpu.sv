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

    // thread_keep_alive: XOR of all thread write_data across all cores.
    // Connect to an LED or primary output in the FPGA wrapper to prevent
    // synthesis tools from sweeping thread logic as dead code.
    output logic [31:0] thread_keep_alive,

    output logic [NUM_CORES-1:0]       prog_mem_req_valid,
    output logic [31:0]                prog_mem_req_addr  [NUM_CORES-1:0],
    input  logic [NUM_CORES-1:0]       prog_mem_resp_valid,
    input  logic [31:0]                prog_mem_resp_data [NUM_CORES-1:0],

    output logic [TOTAL_THREADS-1:0]   data_mem_req_valid,
    output logic [31:0]                data_mem_req_addr  [TOTAL_THREADS-1:0],
    output logic [TOTAL_THREADS-1:0]   data_mem_req_rw,
    output logic [31:0]                data_mem_req_data  [TOTAL_THREADS-1:0],
    input  logic [TOTAL_THREADS-1:0]   data_mem_resp_valid,
    input  logic [31:0]                data_mem_resp_data [TOTAL_THREADS-1:0]
);

// ── DCR / Dispatcher wires ───────────────────────────────────────────────────
logic [31:0] num_blocks;
logic [31:0] blockDim;
logic start;
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

        // Intermediate wires for unpacked array slicing
        // (Icarus VPI does not support unpacked array part-selects directly)
        logic [THREADS_PER_CORE-1:0] core_data_req_valid;
        logic [31:0]                 core_data_req_addr [THREADS_PER_CORE-1:0];
        logic [THREADS_PER_CORE-1:0] core_data_req_rw;
        logic [31:0]                 core_data_req_data [THREADS_PER_CORE-1:0];
        logic [THREADS_PER_CORE-1:0] core_data_resp_valid;
        logic [31:0]                 core_data_resp_data [THREADS_PER_CORE-1:0];
        logic [31:0]                 prog_mem_req_addr_wire;
        logic [31:0]                 prog_mem_resp_data_wire;

        assign prog_mem_req_addr[i]    = prog_mem_req_addr_wire;
        assign prog_mem_resp_data_wire = prog_mem_resp_data[i];

        // Fan data memory channels to/from top-level flat arrays
        genvar j;
        for (j = 0; j < THREADS_PER_CORE; j++) begin : thread_wire_gen
            assign data_mem_req_valid [i*THREADS_PER_CORE+j] = core_data_req_valid[j];
            assign data_mem_req_addr  [i*THREADS_PER_CORE+j] = core_data_req_addr[j];
            assign data_mem_req_rw    [i*THREADS_PER_CORE+j] = core_data_req_rw[j];
            assign data_mem_req_data  [i*THREADS_PER_CORE+j] = core_data_req_data[j];
            assign core_data_resp_valid[j] = data_mem_resp_valid[i*THREADS_PER_CORE+j];
            assign core_data_resp_data [j] = data_mem_resp_data [i*THREADS_PER_CORE+j];
        end

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
            .data_mem_req_valid (core_data_req_valid),
            .data_mem_req_addr  (core_data_req_addr),
            .data_mem_req_rw    (core_data_req_rw),
            .data_mem_req_data  (core_data_req_data),
            .data_mem_resp_valid(core_data_resp_valid),
            .data_mem_resp_data (core_data_resp_data)
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

endmodule