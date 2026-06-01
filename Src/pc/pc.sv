(* syn_dont_touch = 1 *) module pc (
    input logic clk,
    input logic rst,
    input logic block_rst,    // resets PC to 0 at start of each new block
                               // connect to: (scheduler_state==IDLE) && core_start
    input logic pc_en,
    input logic branch_en,
    input logic [11:0] branch_offset,
    input logic nzp_en,
    input logic [2:0] nzp_flag,
    input logic [2:0] nzp_mask,
    output logic [31:0] pc_out,
    output logic [2:0] nzp_out
);

logic [2:0] nzp_reg;

always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        pc_out  <= 32'b0;
        nzp_reg <= 3'b000;
    end else if (block_rst) begin
        // Reset PC to 0 when a new block is dispatched.
        // Fires when scheduler is in IDLE and core_start pulses (IDLE→FETCH).
        // Ensures block N+1 fetches from instruction 0, not block N's RET address.
        pc_out  <= 32'b0;
        nzp_reg <= 3'b000;
    end else begin
        if (nzp_en)
            nzp_reg <= nzp_flag;
        if (pc_en) begin
            if (branch_en && (nzp_reg & nzp_mask) != 0)
                pc_out <= pc_out + branch_offset;
            else
                pc_out <= pc_out + 1;
        end
    end
end

assign nzp_out = nzp_reg;

endmodule