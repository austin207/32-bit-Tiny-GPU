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

always_comb begin 
    opcode = instruction[31:26];
    rd_addr = instruction[25:21];
    rs1_addr = instruction[20:16];
    rs2_addr = instruction[15:11];
    rs3_addr = instruction[10:6];
    imm = instruction[15:0];
    nzp_mask = instruction[25:23];
    branch_offset = instruction[22:0];
    
    ret = 0;
    write_back_en = 0;
    mem_read_en = 0;
    mem_write_en = 0;
    branch_en = 0;
    nzp_en = 0;

    case (opcode)
        6'h00: begin // NOP
            
        end
        6'h01, 6'h02, 6'h03, 6'h04, 6'h05, 6'h06, 6'h07, 6'h08, 6'h09, 6'h0A, 6'h0B, 6'h0C, 6'h13: begin // ALU operations
            write_back_en = 1; 
        end
        6'h0D: begin // CMP
            nzp_en = 1; 
        end
        6'h0E: begin // Branching instructions
            branch_en = 1;
        end
        6'h0F: begin // LOAD
            mem_read_en = 1; 
            write_back_en = 1; 
        end
        6'h10: begin // STORE
            mem_write_en = 1;
        end
        6'h11: begin // CONST
            write_back_en = 1; 
        end
        6'h12: begin // RET
            ret = 1; 
        end
        default: begin 
        end 
    endcase

end
    
endmodule