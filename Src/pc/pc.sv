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

always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
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
    
endmodule