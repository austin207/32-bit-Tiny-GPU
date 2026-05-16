module dcr (
    input logic clk,
    input logic rst,

    input logic dcr_write_en,
    input logic [1:0] dcr_addr,
    input logic [31:0] dcr_data,

    output logic [31:0] num_blocks,
    output logic [31:0] blockDim,
    output logic start
);

always_ff @( posedge clk or posedge rst ) begin 
    if (rst) begin
        num_blocks <= 0;
        blockDim <= 0;
        start <= 0;
    end else begin
        start <= 0; 
        if (dcr_write_en) begin
            case (dcr_addr)
                2'b00: num_blocks <= dcr_data;
                2'b01: blockDim <= dcr_data;
                2'b10: start <= 1;
            endcase
        end
    end
end
    
endmodule