module warp_stack #(
    parameter THREADS_PER_CORE = 4,
    parameter STACK_DEPTH = 4
) (
    input logic clk,
    input logic rst,

    input logic push,
    input logic [31:0] push_sync_pc,
    input logic [THREADS_PER_CORE-1:0] push_saved_mask,

    input logic pop,
    output logic [31:0] top_sync_pc,
    output logic [THREADS_PER_CORE-1:0] top_saved_mask,

    output logic stack_empty,
    output logic stack_full,
    output logic stack_overflow
);

logic [35:0] stack_mem [STACK_DEPTH-1:0];
logic [2:0] sp;

assign stack_empty = (sp == 0);
assign stack_full = (sp == STACK_DEPTH);
assign stack_overflow = push && stack_full;

assign top_sync_pc = (sp > 0) ? stack_mem[sp-1][35:4] : 32'b0;
assign top_saved_mask = (sp > 0) ? stack_mem[sp-1][3:0] : '1;

always_ff @( posedge clk or posedge rst ) begin
    if (rst) begin
        sp <= 0;
    end else begin
        if (push && !stack_full) begin
            stack_mem[sp] <= {push_sync_pc, push_saved_mask};
            sp <= sp + 1;
        end 
        if (pop && !stack_empty) begin
            sp <= sp - 1;
        end
    end
end

    
endmodule