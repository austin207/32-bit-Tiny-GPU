module warp_stack (
	clk,
	rst,
	push,
	push_sync_pc,
	push_saved_mask,
	pop,
	top_sync_pc,
	top_saved_mask,
	stack_empty,
	stack_full,
	stack_overflow
);
	parameter THREADS_PER_CORE = 4;
	parameter STACK_DEPTH = 4;
	input wire clk;
	input wire rst;
	input wire push;
	input wire [31:0] push_sync_pc;
	input wire [THREADS_PER_CORE - 1:0] push_saved_mask;
	input wire pop;
	output wire [31:0] top_sync_pc;
	output wire [THREADS_PER_CORE - 1:0] top_saved_mask;
	output wire stack_empty;
	output wire stack_full;
	output wire stack_overflow;
	reg [35:0] stack_mem [STACK_DEPTH - 1:0];
	reg [2:0] sp;
	assign stack_empty = sp == 0;
	assign stack_full = sp == STACK_DEPTH;
	assign stack_overflow = push && stack_full;
	assign top_sync_pc = (sp > 0 ? stack_mem[sp - 1][35:4] : 32'b00000000000000000000000000000000);
	assign top_saved_mask = (sp > 0 ? stack_mem[sp - 1][3:0] : {THREADS_PER_CORE {1'sb1}});
	always @(posedge clk or posedge rst)
		if (rst)
			sp <= 0;
		else begin
			if (push && !stack_full) begin
				stack_mem[sp] <= {push_sync_pc, push_saved_mask};
				sp <= sp + 1;
			end
			if (pop && !stack_empty)
				sp <= sp - 1;
		end
endmodule
