module lsu (
    input logic clk,
    input logic rst,

    input logic core_en,
    output logic done,
    input logic [31:0] mem_data_address,

    output logic req_valid,
    output logic [31:0] req_addr,
    output logic [31:0] write_data,
    input logic resp_valid,
    input logic [31:0] resp_data,

    input logic mem_write_en,
    input logic [31:0] mem_write_data,
    input logic mem_read_en,
    output logic [31:0] mem_read_data,

    output logic read_write_switch
);

logic is_read;

typedef enum logic { 
    IDLE = 1'b0,
    WAITING = 1'b1
} state_t;

state_t state;

always_ff @( posedge clk or posedge rst ) begin
    if (rst) begin
        req_valid <= 0;
        req_addr <= 32'b0;
        mem_read_data <= 32'b0;
        done <= 0;
        is_read <= 0;
        state <= IDLE;
    end else begin
        req_valid <= 0;
        req_addr <= 32'b0;
        done <= 0;

        case (state)
            IDLE : begin
                if (core_en) begin
                    if (mem_read_en) begin
                        is_read <= 1;
                        req_addr <= mem_data_address;
                        req_valid <= 1;
                        read_write_switch <= 1;
                        state <= WAITING;
                    end else if (mem_write_en) begin
                        req_addr <= mem_data_address;
                        req_valid <= 1;
                        read_write_switch <= 0;
                        write_data <= mem_write_data;  
                        state <= WAITING;
                    end
                end
            end
            WAITING : begin
                if (is_read) begin
                    if (resp_valid) begin
                        mem_read_data <= resp_data;
                        done <= 1;
                        state <= IDLE;
                    end 
                end else begin
                    if (resp_valid) begin
                        done <= 1;
                        state <= IDLE;                        
                    end
                end
            end
            default : begin
                state <= IDLE;
            end
        endcase
    end
end
endmodule