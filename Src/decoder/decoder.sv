module decoder (
    input logic [31:0] instruction,
    output logic [5:0] opcode,
    output logic [4:0] rd_addr,
    output logic [4:0] rs1_addr,
    output logic [4:0] rs2_addr,
    output logic [4:0] rs3_addr,
    output logic [15:0] imm,
    output logic [2:0] nzp_mask,
    output logic [22:0] branch_offset,
    output logic ret,
    output logic write_back_en,
    output logic mem_read_en,
    output logic mem_write_en,
    output logic branch_en,
    output logic nzp_en
);

initial begin
    $dumpfile("pc.vcd");
    $dumpvars(0, pc);
end

always_comb begin 
    
end
    
endmodule