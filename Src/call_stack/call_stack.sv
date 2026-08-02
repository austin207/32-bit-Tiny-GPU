module call_stack #(
    parameter STACK_DEPTH = 2   // provably ≥1 is enough — see explanation below
) (
    input  logic clk,
    input  logic rst,

    input  logic push,
    input  logic [31:0] push_return_pc,

    input  logic pop,
    output logic [31:0] top_return_pc,

    output logic stack_empty,
    output logic stack_full,
    output logic stack_overflow
);

logic [31:0] stack_mem [STACK_DEPTH-1:0];
logic [$clog2(STACK_DEPTH+1)-1:0] sp;

assign stack_empty    = (sp == 0);
assign stack_full     = (sp == STACK_DEPTH);
assign stack_overflow = push && stack_full;
assign top_return_pc  = (sp > 0) ? stack_mem[sp-1] : 32'b0;

always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        sp <= 0;
    end else begin
        if (push && !stack_full)  begin stack_mem[sp] <= push_return_pc; sp <= sp + 1; end
        if (pop  && !stack_empty) sp <= sp - 1;
    end
end

endmodule