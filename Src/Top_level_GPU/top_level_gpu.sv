module gpu #(
    parameter NUM_CORES = 4,
    parameter THREADS_PER_CORE = 4,
    parameter TOTAL_THREADS = NUM_CORES * THREADS_PER_CORE
) (
    input logic clk,
    input logic rst,

    input logic dcr_write_en,
    input logic [1:0] dcr_addr,
    input logic [31:0] dcr_data,
    output logic kernel_done,

    output logic [NUM_CORES-1:0] prog_mem_req_valid,
    output logic [31:0] prog_mem_req_addr [NUM_CORES-1:0],
    input logic [NUM_CORES-1:0] prog_mem_resp_valid,
    input logic [31:0] prog_mem_resp_data [NUM_CORES-1:0],

    output logic [TOTAL_THREADS-1:0] data_mem_req_valid,
    output logic [31:0] data_mem_req_addr [TOTAL_THREADS-1:0],
    output logic [TOTAL_THREADS-1:0] data_mem_req_rw,
    output logic [31:0] data_mem_req_data [TOTAL_THREADS-1:0],
    input logic [TOTAL_THREADS-1:0] data_mem_resp_valid,
    input logic [31:0] data_mem_resp_data [TOTAL_THREADS-1:0]
);

initial begin
    $dumpfile("gpu.vcd");
    $dumpvars(0, gpu);
end

logic [31:0] num_blocks;
logic [31:0] blockDim;
logic start;
logic [NUM_CORES-1:0] core_start;
logic [31:0] blockIdx_out [NUM_CORES-1:0];
logic [NUM_CORES-1:0] block_done;

dcr dcr_inst (
    .clk(clk),
    .rst(rst),
    .dcr_write_en(dcr_write_en),
    .dcr_addr(dcr_addr),
    .dcr_data(dcr_data),
    .num_blocks(num_blocks),
    .blockDim(blockDim),
    .start(start)
);

dispatcher dispatcher_inst (
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

genvar i;

generate
    for (i = 0; i < NUM_CORES; i = i + 1) begin : core_gen
        // Intermediate wires for array slicing
        logic [THREADS_PER_CORE-1:0] core_data_req_valid;
        logic [31:0] core_data_req_addr [THREADS_PER_CORE-1:0];
        logic [THREADS_PER_CORE-1:0] core_data_req_rw;
        logic [31:0] core_data_req_data [THREADS_PER_CORE-1:0];
        logic [THREADS_PER_CORE-1:0] core_data_resp_valid;
        logic [31:0] core_data_resp_data [THREADS_PER_CORE-1:0];

        // Connect intermediate wires to top-level arrays
        genvar j;
        for (j = 0; j < THREADS_PER_CORE; j++) begin : thread_wire_gen
            assign data_mem_req_valid[i*THREADS_PER_CORE+j] = core_data_req_valid[j];
            assign data_mem_req_addr[i*THREADS_PER_CORE+j] = core_data_req_addr[j];
            assign data_mem_req_rw[i*THREADS_PER_CORE+j] = core_data_req_rw[j];
            assign data_mem_req_data[i*THREADS_PER_CORE+j] = core_data_req_data[j];
            assign core_data_resp_valid[j] = data_mem_resp_valid[i*THREADS_PER_CORE+j];
            assign core_data_resp_data[j] = data_mem_resp_data[i*THREADS_PER_CORE+j];
        end

        core #(.THREADS_PER_CORE(THREADS_PER_CORE)) core_inst (
            .clk(clk),
            .rst(rst),
            .core_start(core_start[i]),
            .blockIdx(blockIdx_out[i]),
            .blockDim(blockDim),
            .block_done(block_done[i]),
            .prog_mem_req_valid(prog_mem_req_valid[i]),
            .prog_mem_req_addr(prog_mem_req_addr[i]),
            .prog_mem_resp_valid(prog_mem_resp_valid[i]),
            .prog_mem_resp_data(prog_mem_resp_data[i]),
            .data_mem_req_valid(core_data_req_valid),
            .data_mem_req_addr(core_data_req_addr),
            .data_mem_req_rw(core_data_req_rw),
            .data_mem_req_data(core_data_req_data),
            .data_mem_resp_valid(core_data_resp_valid),
            .data_mem_resp_data(core_data_resp_data)
        );
    end
endgenerate
endmodule