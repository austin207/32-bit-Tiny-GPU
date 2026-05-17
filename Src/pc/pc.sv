module pc (
    input logic clk,
    input logic rst,
    input logic pc_en,
    input logic branch_en,
    input logic [22:0] branch_offset,
    input logic nzp_en,
    input logic [2:0] nzp_flag,
    input logic [2:0] nzp_mask,
    output logic [31:0] pc_out
);

logic [2:0] nzp_reg;

always_ff @( posedge clk or posedge rst ) begin 
    if (rst) begin
        pc_out <= 32'b0;
        nzp_reg <= 3'b000;
    end else if (nzp_en) begin
        nzp_reg <= nzp_flag;
    end else if (pc_en) begin   // only update when enabled
        if (branch_en) begin
            if ((nzp_reg & nzp_mask) != 0) begin
                pc_out <= pc_out + branch_offset;
            end else begin
                pc_out <= pc_out + 1;
            end
        end else begin
            pc_out <= pc_out + 1;
        end
    end
end
    
endmodule