module dispatcher #(
    parameter NUM_CORES = 4,
    parameter THREADS_PER_CORE = 4
) (
    input logic clk,
    input logic rst,

    input logic [31:0] num_blocks,
    input logic [31:0] blockDim,
    input logic dispatch_en,
    input logic [NUM_CORES-1:0] block_done,

    output logic [NUM_CORES-1:0] core_start,
    output logic [31:0] blockIdx_out [NUM_CORES-1:0],
    output logic kernel_done
);

logic [31:0] next_block;
logic [31:0] active_blocks;
logic assigned;
logic [31:0] done_count;
logic signed [31:0] delta;

always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        next_block <= 0;
        active_blocks <= 0;
        kernel_done <= 0;
        for (int i = 0; i < NUM_CORES; i++) begin
            core_start[i] <= 0;
            blockIdx_out[i] <= 0;
        end
    end else begin
        done_count = 0;
        delta = 0;
        for (int i = 0; i < NUM_CORES; i++) begin
            if (block_done[i]) begin
                core_start[i] <= 0;
                done_count = done_count + 1;
                delta = delta - 1;
            end
        end
        
        if (dispatch_en) begin
            assigned = 0;
            for (int i = 0; i < NUM_CORES; i++) begin
                if (!assigned && core_start[i] == 0 && block_done[i] == 0 && next_block < num_blocks) begin
                    core_start[i] <= 1;
                    blockIdx_out[i] <= next_block;
                    next_block <= next_block + 1;
                    delta = delta + 1;
                    assigned = 1;
                end
            end
        end
        active_blocks <= active_blocks + delta;

        if (next_block == num_blocks && active_blocks == 0 && num_blocks > 0) begin
            kernel_done <= 1;
        end
    end
end
endmodule