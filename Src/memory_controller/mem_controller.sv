module memory_controller #(
    parameter NUM_CORES = 1,
    parameter THREADS_PER_CORE = 4,
    parameter TOTAL_THREADS = NUM_CORES * THREADS_PER_CORE
)(
    // LSU Interface
    input  logic [TOTAL_THREADS-1:0] req_avail,
    input  logic [31:0] req_addr [TOTAL_THREADS-1:0],
    input  logic [TOTAL_THREADS-1:0] read_write_switch,
    input  logic [31:0] req_data [TOTAL_THREADS-1:0],

    output logic [TOTAL_THREADS-1:0] resp_valid,
    output logic [31:0] resp_data [TOTAL_THREADS-1:0],

    // Memory Request Interface
    output logic [TOTAL_THREADS-1:0] mem_req_valid,
    output logic [31:0] mem_req_addr [TOTAL_THREADS-1:0],
    output logic [TOTAL_THREADS-1:0] mem_req_rw,
    output logic [31:0] mem_req_data [TOTAL_THREADS-1:0],

    // Memory Response Interface
    input  logic [TOTAL_THREADS-1:0] mem_resp_valid,
    input  logic [31:0] mem_resp_data [TOTAL_THREADS-1:0]
);

    genvar i;

    generate
        for (i = 0; i < TOTAL_THREADS; i = i + 1) begin : request_response_forwarding
            assign mem_req_valid[i] = req_avail[i];
            assign mem_req_addr[i]  = req_addr[i];
            assign mem_req_rw[i]    = read_write_switch[i];
            assign mem_req_data[i]  = req_data[i];

            assign resp_valid[i]    = mem_resp_valid[i];
            assign resp_data[i]     = mem_resp_data[i];
        end
    endgenerate

endmodule