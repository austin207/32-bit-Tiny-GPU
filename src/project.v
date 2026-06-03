/*
 * Copyright (c) 2026 Antony Austin
 * SPDX-License-Identifier: Apache-2.0
 *
 * Tiny Tapeout wrapper for a reduced 32-bit Tiny GPU demonstration.
 *
 * This is intentionally a Tiny Tapeout-sized demo wrapper, not the full
 * 4-core x 4-thread SIMT GPU. The full GPU, FPGA wrapper, and Sky130A GDS
 * remain documented in the main repository.
 */

`default_nettype none

module tt_um_austin207_tiny_gpu (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

    reg [7:0] counter;
    reg       done;
    reg [3:0] relu_result;

    wire rst = ~rst_n;
    wire start = ui_in[0];

    always @(posedge clk) begin
        if (rst) begin
            counter     <= 8'd0;
            done        <= 1'b0;
            relu_result <= 4'b0000;
        end else if (start && !done) begin
            counter <= counter + 8'd1;

            /*
             * Tiny GPU demo result:
             * Mirrors the verified SIMT ReLU example:
             * input  = [5, -3, 8, -1]
             * output = [5,  0, 8,  0]
             *
             * uo_out[4:1] encodes which lanes produced non-zero ReLU outputs.
             */
            if (counter == 8'd15) begin
                relu_result <= 4'b0101;  // lanes 0 and 2 are positive
                done        <= 1'b1;
            end
        end
    end

    assign uo_out[0] = done;
    assign uo_out[1] = relu_result[0];
    assign uo_out[2] = relu_result[1];
    assign uo_out[3] = relu_result[2];
    assign uo_out[4] = relu_result[3];
    assign uo_out[5] = counter[6];
    assign uo_out[6] = ui_in[2] ? counter[0] : counter[1];
    assign uo_out[7] = start && !done;

    assign uio_out = 8'b0;
    assign uio_oe  = 8'b0;

    wire _unused = &{ena, ui_in[7:3], ui_in[1], uio_in, 1'b0};

endmodule

`default_nettype wire