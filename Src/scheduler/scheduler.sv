module scheduler #(
    parameter NUM_CORES = 1,
    parameter THREADS_PER_CORE = 4,
    parameter TOTAL_THREADS = NUM_CORES * THREADS_PER_CORE
)(
    input logic clk,
    input logic rst,

    input logic core_start,
    input logic fetcher_done,
    input logic [TOTAL_THREADS-1:0] lsu_done,
    input logic mem_read_en,
    input logic mem_write_en,
    input logic ret,

    output logic fetcher_en,
    output logic lsu_en,
    output logic execute_en,
    output logic write_back_en,
    output logic [2:0] current_state,
    output logic block_done
);

initial begin
    $dumpfile("scheduler.vcd");
    $dumpvars(0, scheduler);
end

typedef enum logic [2:0] { 
    IDLE    = 3'b000,
    FETCH   = 3'b001,
    DECODE  = 3'b010,
    REQUEST = 3'b011,
    WAIT    = 3'b100,
    EXECUTE = 3'b101,
    UPDATE  = 3'b110
 } state_t;

state_t state;
assign current_state = state;
logic all_done;
assign all_done = &lsu_done;

always_ff @( posedge clk or posedge rst ) begin 
    if (rst) begin
        state <= IDLE;

        fetcher_en <= 0;
        lsu_en <= 0;
        execute_en <= 0;
        write_back_en <= 0;
        block_done <= 0;
    end else begin
        fetcher_en <= 0;
        lsu_en <= 0;
        execute_en <= 0;
        write_back_en <= 0;
        block_done <= 0;
        case (state)
           IDLE: begin
                if (core_start) begin
                    fetcher_en <= 1;
                    state <= FETCH;
                end
            end
            FETCH: begin
                if (fetcher_done) begin
                    state <= DECODE;
                end
            end
            DECODE: begin
                if (mem_read_en || mem_write_en) begin
                    state <= REQUEST;
                end else begin
                    state <= EXECUTE;
                end
            end
            REQUEST: begin
                lsu_en <= 1;
                state <= WAIT;
            end
            WAIT: begin
                if (all_done) begin
                    state <= EXECUTE;
                end
            end
            EXECUTE: begin
                execute_en <= 1;
                state <= UPDATE;
            end
            UPDATE: begin
                if (ret) begin
                    block_done <= 1;
                    state <= IDLE;
                end else begin
                    state <= FETCH;
                end
                write_back_en <= 1;
            end
            default: ;
        endcase
    end
end
endmodule