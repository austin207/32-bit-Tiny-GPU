module fetcher (
    input logic clk,
    input logic rst,

    input logic core_en,
    input logic [31:0] pc_value,
    output logic [31:0] instruction,
    output logic done,

    output logic req_valid,
    output logic [31:0] req_addr,
    input logic resp_valid,
    input logic [31:0] resp_data
);

initial begin
    $dumpfile("fetcher.vcd");
    $dumpvars(0, fetcher);
end

typedef enum logic { 
    IDLE = 1'b0,
    WAITING = 1'b1
 } state_t;

 state_t state;

 always_ff @( posedge clk or posedge rst ) begin
    if (rst) begin
        state <= IDLE;
        instruction <= 32'b0;
        req_valid <= 0;
        req_addr <= 32'b0;
        done <= 0;
    end else begin
        req_valid <= 0;
        done <= 0;

        case (state)
            IDLE : begin
                if (core_en) begin
                    req_addr <= pc_value;
                    req_valid <= 1;
                    done <= 0;
                    state <= WAITING;
                end
            end
            WAITING : begin
                if (resp_valid) begin
                    instruction <= resp_data;
                    done <= 1;
                    state <= IDLE;
                end 
            end
            default: ;
        endcase        
    end
 end
endmodule