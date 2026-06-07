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
    output logic [NUM_CORES-1:0][31:0] blockIdx_out,
    output logic kernel_done
);

logic running;

logic [31:0] next_block;
logic [31:0] completed_blocks;

logic running_next;
logic kernel_done_next;
logic [31:0] next_block_next;
logic [31:0] completed_blocks_next;
logic [NUM_CORES-1:0] core_start_next;
logic [NUM_CORES-1:0][31:0] blockIdx_out_next;

always_comb begin
    running_next          = running;
    kernel_done_next      = kernel_done;
    next_block_next       = next_block;
    completed_blocks_next = completed_blocks;
    core_start_next       = core_start;
    blockIdx_out_next     = blockIdx_out;

    /*
     * dispatch_en is treated as a launch pulse.
     * Once launched, dispatcher keeps issuing blocks internally until all
     * num_blocks are completed.
     */
    if (dispatch_en && !running) begin
        running_next          = 1'b1;
        kernel_done_next      = 1'b0;
        next_block_next       = 32'd0;
        completed_blocks_next = 32'd0;
        core_start_next       = '0;
        blockIdx_out_next     = '0;
    end

    if (running_next) begin
        /*
         * First consume completed blocks.
         * core_start acts as a per-core busy/enable bit, so only count
         * block_done from cores that were actually active.
         */
        for (int i = 0; i < NUM_CORES; i++) begin
            if (core_start_next[i] && block_done[i]) begin
                core_start_next[i] = 1'b0;
                completed_blocks_next = completed_blocks_next + 32'd1;
            end
        end

        /*
         * Then launch as many pending blocks as there are free cores.
         * This fixes the old bug where only one block was launched per
         * dispatch_en cycle.
         */
        for (int i = 0; i < NUM_CORES; i++) begin
            if (!core_start_next[i] && (next_block_next < num_blocks)) begin
                core_start_next[i] = 1'b1;
                blockIdx_out_next[i] = next_block_next;
                next_block_next = next_block_next + 32'd1;
            end
        end

        /*
         * Done when all requested blocks have completed.
         */
        if ((num_blocks > 0) &&
            (next_block_next == num_blocks) &&
            (completed_blocks_next == num_blocks)) begin
            running_next     = 1'b0;
            kernel_done_next = 1'b1;
            core_start_next  = '0;
        end
    end

    /*
     * Empty kernel safety.
     */
    if (dispatch_en && !running && (num_blocks == 0)) begin
        running_next     = 1'b0;
        kernel_done_next = 1'b1;
        core_start_next  = '0;
    end
end

always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        running          <= 1'b0;
        kernel_done      <= 1'b0;
        next_block       <= 32'd0;
        completed_blocks <= 32'd0;
        core_start       <= '0;
        blockIdx_out     <= '0;
    end else begin
        running          <= running_next;
        kernel_done      <= kernel_done_next;
        next_block       <= next_block_next;
        completed_blocks <= completed_blocks_next;
        core_start       <= core_start_next;
        blockIdx_out     <= blockIdx_out_next;
    end
end

endmodule