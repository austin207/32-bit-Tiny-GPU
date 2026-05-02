module memory_controller #(
    parameter NUM_CORES = 1,
    parameter THREADS_PER_CORE = 4,
    parameter TOTAL_THREADS = NUM_CORES * THREADS_PER_CORE
)(
    // uncomment clock and reset for round robin arbitration and pipelining
    //input logic clk,
    //input logic rst,
    //LSU Interface
    input logic [TOTAL_THREADS-1:0] req_avail,
    input logic [31:0] req_addr [TOTAL_THREADS-1:0],
    input logic [TOTAL_THREADS-1:0] read_write_switch,
    input logic [31:0] req_data [TOTAL_THREADS-1:0],
    output logic [TOTAL_THREADS-1:0] resp_valid,
    output logic [31:0] resp_data [TOTAL_THREADS-1:0],

    //Memory Interface
    output logic [TOTAL_THREADS-1:0] mem_req_valid,
    output logic [31:0] mem_req_addr [TOTAL_THREADS-1:0],
    output logic [TOTAL_THREADS-1:0] mem_req_rw,
    output logic [31:0] mem_req_data [TOTAL_THREADS-1:0],

    //Memory Response Interface
    input logic [TOTAL_THREADS-1:0] mem_resp_valid,
    input logic [31:0] mem_resp_data [TOTAL_THREADS-1:0]
);

initial begin
    $dumpfile("memory_controller.vcd");
    $dumpvars(0, memory_controller);
end

always_comb begin
    for (int i = 0; i < TOTAL_THREADS; i++) begin
        mem_req_valid[i] = req_avail[i];
        mem_req_addr[i] = req_addr[i];
        mem_req_rw[i] = read_write_switch[i];
        mem_req_data[i] = req_data[i];
        resp_valid[i] = mem_resp_valid[i];
        resp_data[i] = mem_resp_data[i];
    end
end

endmodule