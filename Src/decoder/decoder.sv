module decoder (
    input  logic [31:0] instruction,

    output logic [5:0]  opcode,
    output logic [4:0]  rd_addr,
    output logic [4:0]  rs1_addr,
    output logic [4:0]  rs2_addr,
    output logic [4:0]  rs3_addr,
    output logic [15:0] imm,
    output logic [2:0]  nzp_mask,
    output logic [22:0] branch_offset,

    output logic ret,
    output logic write_back_en,
    output logic mem_read_en,
    output logic mem_write_en,
    output logic branch_en,
    output logic nzp_en
);

    // Raw instruction field extraction
    assign opcode        = instruction[31:26];
    assign rd_addr       = instruction[25:21];
    assign rs1_addr      = instruction[20:16];
    assign rs2_addr      = instruction[15:11];
    assign rs3_addr      = instruction[10:6];
    assign imm           = instruction[15:0];
    assign nzp_mask      = instruction[25:23];
    assign branch_offset = instruction[22:0];

    // Control signal decoding
    always_comb begin
        ret           = 1'b0;
        write_back_en = 1'b0;
        mem_read_en   = 1'b0;
        mem_write_en  = 1'b0;
        branch_en     = 1'b0;
        nzp_en        = 1'b0;

        case (opcode)
            6'h00: begin
                // NOP
            end

            // ALU operations
            6'h01, 6'h02, 6'h03, 6'h04,
            6'h05, 6'h06, 6'h07, 6'h08,
            6'h09, 6'h0A, 6'h0B, 6'h0C,
            6'h13, 6'h14: begin
                write_back_en = 1'b1;
            end

            6'h0D: begin
                // CMP
                nzp_en = 1'b1;
            end

            6'h0E: begin
                // BR / BRNZP
                branch_en = 1'b1;
            end

            6'h0F: begin
                // LOAD
                mem_read_en   = 1'b1;
                write_back_en = 1'b1;
            end

            6'h10: begin
                // STORE
                mem_write_en = 1'b1;
            end

            6'h11: begin
                // CONST
                write_back_en = 1'b1;
            end

            6'h12: begin
                // RET
                ret = 1'b1;
            end

            default: begin
                // Invalid/unsupported opcode: all controls stay low
            end
        endcase
    end

endmodule