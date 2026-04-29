module registers (
    input logic clk,
    input logic rst,
    input logic [4:0] r_addr1,
    input logic [4:0] r_addr2,
    input logic [4:0] w_addr,
    input logic [31:0] w_data,
    input logic w_en,
    input logic [31:0] threadIdx,   
    input logic [31:0] blockIdx,
    input logic [31:0] blockDim,
    output logic [31:0] r_data1,
    output logic [31:0] r_data2
);
logic [31:0] reg_file [0:31];

initial begin
    $dumpfile("register_file.vcd");
    $dumpvars(0, registers);
end

/*
Register write logic
- On reset, all registers (except the hardwired ones) are set to zero
- On a write enable signal, the specified register is updated with the provided data
- Writes to registers 0, 29, 30, and 31 are ignored since they are hardwired to specific values
*/

always_ff @(posedge clk or posedge rst ) begin
    if (rst) begin
        for (int i = 1; i < 29; i++) begin
           reg_file[i] <= 32'b0; 
        end
    end else if (w_en) begin
        if (w_addr >= 1 && w_addr <= 28) begin
            reg_file[w_addr] <= w_data;
        end
    end
end

/** Read logic for r_data1 and r_data2
 * Registers 0, 29, 30, and 31 are hardwired to specific values
 * Register 0 is always zero
 * Register 29 holds threadIdx
 * Register 30 holds blockIdx
 * Register 31 holds blockDim
 * All other registers return the value stored in the reg_file array
 */

always_comb begin : read_port_1
    case (r_addr1)
        5'd0: r_data1 = 32'b0; 
        5'd29: r_data1 = threadIdx; 
        5'd30: r_data1 = blockIdx;  
        5'd31: r_data1 = blockDim;   
        default: r_data1 = reg_file[r_addr1]; 
    endcase
end

always_comb begin : read_port_2
    case (r_addr2)
       5'd0: r_data2 = 32'b0; 
       5'd29: r_data2 = threadIdx; 
       5'd30: r_data2 = blockIdx;  
       5'd31: r_data2 = blockDim;  
        default: r_data2 = reg_file[r_addr2];
    endcase
end
endmodule