// gpu_fpga_top.sv — Tang Nano 20K wrapper for 32-bit Tiny GPU
//
// Clock:
//   clk      = 27 MHz onboard oscillator (pin 4, LVCMOS33)
//   clk_slow = 27 MHz / 8 = 3.375 MHz — fed to GPU and all BRAMs
//   UART TX runs on fast clk (27 MHz) for accurate 115200 baud
//
// Configuration:
//   THREADS_PER_CORE = 1, NUM_BLOCKS = 4
//   Runs 4 sequential blocks.  In each block r29 returns blockIdx
//   (patched in registers.sv) so:
//     block 0 → computes y[0] → stores at BRAM addr 20
//     block 1 → computes y[1] → stores at BRAM addr 21
//     block 2 → computes y[2] → stores at BRAM addr 22
//     block 3 → computes y[3] → stores at BRAM addr 23
//
// UART output (115200 8N1, pin 69 → BL616 USB-UART bridge):
//   Open the higher-numbered COM port in any terminal (PuTTY, Tera Term)
//   at 115200 baud after flashing.  Output:
//     GPU DONE
//     T:XXXXXXXX   (clk_slow cycles, 1 cycle = 296 ns)
//     Y:YYYYYYYY YYYYYYYY YYYYYYYY YYYYYYYY  (Q8 fixed-point hex)
//
//   To convert Y to float: value / 256.0
//   Simulation expected: y≈[0x1F3,0x3E7,0x5DB,0x7CF] → [1.95,3.89,5.84,7.80]
//
// NOTE: If UART pin 69 shows no output, verify the pin using
//   Gowin EDA → Tools → Visual Constraint Editor → Add from Template
//   for device GW2AR-18C, then update uart_tx in gpu_top.cst.
//
// LEDs (active-LOW):
//   led[0]   = kernel_done (solid ON when all 4 blocks complete)
//   led[5:1] = rolling heartbeat (confirms board alive, ~1.6 Hz)

module gpu_fpga_top (
    input  wire       clk,       // 27 MHz, pin 4 (Tang Nano 20K oscillator)
    input  wire       rst_n,     // power-on reset (unused — replaced by counter)
    output wire [5:0] led,       // active-LOW LEDs, pins 15–20
    output wire       uart_tx    // UART TX to BL616, pin 69, 115200 8N1
);

localparam NUM_CORES        = 1;
localparam THREADS_PER_CORE = 1;
localparam TOTAL_THREADS    = 1;
localparam PROG_DEPTH       = 64;
localparam DATA_DEPTH       = 32;

// ─── Power-on reset (no physical button) ─────────────────────────────────────
reg [7:0] por_cnt = 0;
wire      rst_raw = !por_cnt[7];
always @(posedge clk) if (!por_cnt[7]) por_cnt <= por_cnt + 1;

// 2-FF reset synchronizer
reg rst_r1, rst_sync;
always @(posedge clk or posedge rst_raw) begin
    if (rst_raw) begin rst_r1 <= 1; rst_sync <= 1; end
    else         begin rst_r1 <= 0; rst_sync <= rst_r1; end
end

// ─── Clock divider: 27 MHz → 3.375 MHz ───────────────────────────────────────
reg [2:0] clk_div;
reg       clk_slow;
always @(posedge clk or posedge rst_sync) begin
    if (rst_sync) begin clk_div <= 0; clk_slow <= 0; end
    else if (clk_div == 3'd3) begin clk_div <= 0; clk_slow <= ~clk_slow; end
    else clk_div <= clk_div + 1;
end

// ─── GPU port wires ───────────────────────────────────────────────────────────
wire        dcr_write_en;
wire [1:0]  dcr_addr;
wire [31:0] dcr_data;
wire        kernel_done;
wire [31:0] thread_keep_alive;

wire [0:0]  prog_mem_req_valid;
wire [31:0] prog_mem_req_addr;
wire [0:0]  prog_mem_resp_valid;
wire [31:0] prog_mem_resp_data;

wire [0:0]  data_mem_req_valid;
wire [31:0] data_mem_req_addr;
wire [0:0]  data_mem_req_rw;
wire [31:0] data_mem_req_data;
wire [0:0]  data_mem_resp_valid;
wire [31:0] data_mem_resp_data;

// ─── GPU instance (clk_slow domain) ──────────────────────────────────────────
gpu #(
    .NUM_CORES(NUM_CORES),
    .THREADS_PER_CORE(THREADS_PER_CORE)
) gpu_inst (
    .clk              (clk_slow),
    .rst              (rst_sync),
    .dcr_write_en     (dcr_write_en),
    .dcr_addr         (dcr_addr),
    .dcr_data         (dcr_data),
    .kernel_done      (kernel_done),
    .prog_mem_req_valid(prog_mem_req_valid),
    .prog_mem_req_addr (prog_mem_req_addr),
    .prog_mem_resp_valid(prog_mem_resp_valid),
    .prog_mem_resp_data (prog_mem_resp_data),
    .data_mem_req_valid(data_mem_req_valid),
    .data_mem_req_addr (data_mem_req_addr),
    .data_mem_req_rw   (data_mem_req_rw),
    .data_mem_req_data (data_mem_req_data),
    .data_mem_resp_valid(data_mem_resp_valid),
    .data_mem_resp_data (data_mem_resp_data),
    .thread_keep_alive (thread_keep_alive)
);

// ─── Boot dispatch FSM (clk_slow domain) ─────────────────────────────────────
// Writes DCR registers to start 4 sequential blocks (num_blocks=4, blockDim=1).
// With THREADS_PER_CORE=1 and the r29=blockIdx patch in registers.sv,
// each block computes one output neuron: y[blockIdx].
reg [2:0]  dstate;
reg [3:0]  boot_cnt;
reg        dcr_we_r;
reg [1:0]  dcr_addr_r;
reg [31:0] dcr_data_r;

assign dcr_write_en = dcr_we_r;
assign dcr_addr     = dcr_addr_r;
assign dcr_data     = dcr_data_r;

always @(posedge clk_slow or posedge rst_sync) begin
    if (rst_sync) begin
        dstate <= 0; boot_cnt <= 0;
        dcr_we_r <= 0; dcr_addr_r <= 0; dcr_data_r <= 0;
    end else begin
        dcr_we_r <= 0;
        case (dstate)
            3'd0: begin
                if (boot_cnt == 4'd7) dstate <= 1;
                else boot_cnt <= boot_cnt + 1;
            end
            3'd1: begin // num_blocks = 4
                dcr_we_r <= 1; dcr_addr_r <= 2'b00; dcr_data_r <= 32'd4;
                dstate <= 2;
            end
            3'd2: begin // blockDim = 1
                dcr_we_r <= 1; dcr_addr_r <= 2'b01; dcr_data_r <= 32'd1;
                dstate <= 3;
            end
            3'd3: begin
                // Keep dispatch_en=1 every cycle until kernel_done.
                // With NUM_CORES=1 and num_blocks=4, the dispatcher needs
                // dispatch_en asserted when each block completes so it can
                // assign the next block. A single pulse only dispatches block 0.
                dcr_we_r   <= 1'b1;
                dcr_addr_r <= 2'b10;
                dcr_data_r <= 32'd0;
                if (kernel_done) begin
                    dcr_we_r <= 1'b0; // stop after all blocks complete
                    dstate   <= 3'd4;
                end
            end
            3'd4: ;  // GPU done, kernel_done latched
        endcase
    end
end

// ─── Cycle timer (clk_slow domain) ───────────────────────────────────────────
// Counts clk_slow cycles from the start command to kernel_done.
// Resolution: 1 cycle = 296.3 ns at 3.375 MHz.
reg [31:0] cycle_count;
reg        timing_active;
wire       start_pulse = dcr_we_r && (dcr_addr_r == 2'b10);

always @(posedge clk_slow or posedge rst_sync) begin
    if (rst_sync) begin
        cycle_count  <= 32'd0;
        timing_active <= 1'b0;
    end else if (start_pulse && !timing_active) begin
        cycle_count   <= 32'd0;
        timing_active <= 1'b1;
    end else if (timing_active) begin
        if (!kernel_done) cycle_count <= cycle_count + 1;
        else              timing_active <= 1'b0;
    end
end

// ─── Result capture (snoop GPU write bus) ────────────────────────────────────
// Captures y[0..3] as the GPU writes them to BRAM addresses 20..23.
// No extra BRAM read port needed — we observe the write data bus directly.
reg [31:0] result [0:3];
always @(posedge clk_slow) begin
    if (data_mem_req_valid[0] && (data_mem_req_rw[0] == 1'b0)) begin
        if (data_mem_req_addr == 32'd20) result[0] <= data_mem_req_data;
        if (data_mem_req_addr == 32'd21) result[1] <= data_mem_req_data;
        if (data_mem_req_addr == 32'd22) result[2] <= data_mem_req_data;
        if (data_mem_req_addr == 32'd23) result[3] <= data_mem_req_data;
    end
end

// ─── Program BRAM (64 × 32-bit, clk_slow domain) ─────────────────────────────
reg [31:0] prog_bram [0:PROG_DEPTH-1];
initial $readmemh("prog_mem.hex", prog_bram);

reg        prog_resp_r;
reg [31:0] prog_data_r;
always @(posedge clk_slow or posedge rst_sync) begin
    if (rst_sync) begin prog_resp_r <= 0; prog_data_r <= 0; end
    else begin
        prog_resp_r <= prog_mem_req_valid[0];
        prog_data_r <= prog_bram[prog_mem_req_addr[7:0]];
    end
end
assign prog_mem_resp_valid = prog_resp_r;
assign prog_mem_resp_data  = prog_data_r;

// ─── Data BRAM (32 × 32-bit, thread 0, clk_slow domain) ──────────────────────
reg [31:0] data_bram_0 [0:DATA_DEPTH-1];
initial $readmemh("data_mem.hex", data_bram_0);

reg        data_resp_r;
reg [31:0] data_data_r;
always @(posedge clk_slow or posedge rst_sync) begin
    if (rst_sync) begin data_resp_r <= 0; data_data_r <= 0; end
    else begin
        if (data_mem_req_valid[0]) begin
            if (data_mem_req_rw[0] == 1'b0)
                data_bram_0[data_mem_req_addr[31:0]] <= data_mem_req_data;
            data_data_r <= data_bram_0[data_mem_req_addr[31:0]];
        end
        data_resp_r <= data_mem_req_valid[0];
    end
end
assign data_mem_resp_valid = data_resp_r;
assign data_mem_resp_data  = data_data_r;

// ─── LEDs ─────────────────────────────────────────────────────────────────────
reg [24:0] heartbeat;
always @(posedge clk) heartbeat <= heartbeat + 1;

assign led[0]   = ~(kernel_done | thread_keep_alive[31]);
assign led[5:1] = ~heartbeat[22:18];

// ─── UART TX module (27 MHz fast clock, 115200 baud, 8N1) ────────────────────
// Divisor = 27,000,000 / 115,200 = 234  (0.16% error — within UART tolerance)
// Pin 69 → BL616 USB-UART bridge.  Open the higher COM port in your terminal.
localparam UART_DIV = 8'd234;

reg [7:0]  uart_byte;
reg        uart_send;
wire       uart_busy;
reg        uart_tx_r;
assign uart_tx = uart_tx_r;

reg [7:0]  u_clk_cnt;
reg [3:0]  u_bit_cnt;
reg [9:0]  u_shift;
reg        u_sending;
assign uart_busy = u_sending;

always @(posedge clk or posedge rst_sync) begin
    if (rst_sync) begin
        uart_tx_r <= 1; u_sending <= 0;
        u_clk_cnt <= 0; u_bit_cnt <= 0; u_shift <= 0;
    end else if (!u_sending && uart_send) begin
        // Load: stop(1) | data[7:0] | start(0)  — LSB sent first
        u_shift   <= {1'b1, uart_byte, 1'b0};
        u_sending <= 1; u_clk_cnt <= 0; u_bit_cnt <= 0;
    end else if (u_sending) begin
        if (u_clk_cnt == UART_DIV - 1) begin
            u_clk_cnt <= 0;
            uart_tx_r <= u_shift[0];
            u_shift   <= {1'b1, u_shift[9:1]};
            if (u_bit_cnt == 9) u_sending <= 0;
            else u_bit_cnt <= u_bit_cnt + 1;
        end else begin
            u_clk_cnt <= u_clk_cnt + 1;
        end
    end else begin
        uart_tx_r <= 1;
    end
end

// ─── CDC: kernel_done (clk_slow) → fast clock domain ─────────────────────────
reg kd_s1, kd_s2, kd_s3;
always @(posedge clk) begin
    kd_s1 <= kernel_done; kd_s2 <= kd_s1; kd_s3 <= kd_s2;
end
wire kd_rise = kd_s2 & ~kd_s3;  // single-cycle pulse on rising edge

// ─── CDC: cycle_count + results (clk_slow → fast clock) ─────────────────────
// Latch all values simultaneously on kernel_done to avoid metastability.
// kernel_done is a stable flag after it asserts (never de-asserts until reset).
reg [31:0] saved_cycles;
reg [31:0] saved_y0, saved_y1, saved_y2, saved_y3;
always @(posedge clk) begin
    if (kd_rise) begin
        saved_cycles <= cycle_count;
        saved_y0     <= result[0];
        saved_y1     <= result[1];
        saved_y2     <= result[2];
        saved_y3     <= result[3];
    end
end

// ─── Hex nibble to ASCII helper ───────────────────────────────────────────────
function [7:0] h2a;
    input [3:0] n;
    h2a = (n < 4'hA) ? (8'h30 + {4'b0, n}) : (8'h57 + {4'b0, n});
    // 0x57 = 'a' - 10, so n=0xA→'a', n=0xF→'f'
endfunction

// ─── Message byte lookup (62 bytes total) ────────────────────────────────────
// Output:
//   "GPU DONE\r\n"     (10 bytes, pos 0-9)
//   "T:XXXXXXXX\r\n"   (12 bytes, pos 10-21)
//   "Y:YYYYYYYY YYYYYYYY YYYYYYYY YYYYYYYY\r\n"  (40 bytes, pos 22-61)
reg [7:0] cur_byte;
reg [5:0] msg_pos;   // 0-61
always @(*) begin
    case (msg_pos)
        // "GPU DONE\r\n"
        6'd0:  cur_byte = "G";
        6'd1:  cur_byte = "P";
        6'd2:  cur_byte = "U";
        6'd3:  cur_byte = " ";
        6'd4:  cur_byte = "D";
        6'd5:  cur_byte = "O";
        6'd6:  cur_byte = "N";
        6'd7:  cur_byte = "E";
        6'd8:  cur_byte = 8'h0D;
        6'd9:  cur_byte = 8'h0A;
        // "T:"
        6'd10: cur_byte = "T";
        6'd11: cur_byte = ":";
        // cycle count (8 hex digits, MSB first)
        6'd12: cur_byte = h2a(saved_cycles[31:28]);
        6'd13: cur_byte = h2a(saved_cycles[27:24]);
        6'd14: cur_byte = h2a(saved_cycles[23:20]);
        6'd15: cur_byte = h2a(saved_cycles[19:16]);
        6'd16: cur_byte = h2a(saved_cycles[15:12]);
        6'd17: cur_byte = h2a(saved_cycles[11:8]);
        6'd18: cur_byte = h2a(saved_cycles[7:4]);
        6'd19: cur_byte = h2a(saved_cycles[3:0]);
        6'd20: cur_byte = 8'h0D;
        6'd21: cur_byte = 8'h0A;
        // "Y: "
        6'd22: cur_byte = "Y";
        6'd23: cur_byte = ":";
        6'd24: cur_byte = " ";
        // y[0]
        6'd25: cur_byte = h2a(saved_y0[31:28]);
        6'd26: cur_byte = h2a(saved_y0[27:24]);
        6'd27: cur_byte = h2a(saved_y0[23:20]);
        6'd28: cur_byte = h2a(saved_y0[19:16]);
        6'd29: cur_byte = h2a(saved_y0[15:12]);
        6'd30: cur_byte = h2a(saved_y0[11:8]);
        6'd31: cur_byte = h2a(saved_y0[7:4]);
        6'd32: cur_byte = h2a(saved_y0[3:0]);
        6'd33: cur_byte = " ";
        // y[1]
        6'd34: cur_byte = h2a(saved_y1[31:28]);
        6'd35: cur_byte = h2a(saved_y1[27:24]);
        6'd36: cur_byte = h2a(saved_y1[23:20]);
        6'd37: cur_byte = h2a(saved_y1[19:16]);
        6'd38: cur_byte = h2a(saved_y1[15:12]);
        6'd39: cur_byte = h2a(saved_y1[11:8]);
        6'd40: cur_byte = h2a(saved_y1[7:4]);
        6'd41: cur_byte = h2a(saved_y1[3:0]);
        6'd42: cur_byte = " ";
        // y[2]
        6'd43: cur_byte = h2a(saved_y2[31:28]);
        6'd44: cur_byte = h2a(saved_y2[27:24]);
        6'd45: cur_byte = h2a(saved_y2[23:20]);
        6'd46: cur_byte = h2a(saved_y2[19:16]);
        6'd47: cur_byte = h2a(saved_y2[15:12]);
        6'd48: cur_byte = h2a(saved_y2[11:8]);
        6'd49: cur_byte = h2a(saved_y2[7:4]);
        6'd50: cur_byte = h2a(saved_y2[3:0]);
        6'd51: cur_byte = " ";
        // y[3]
        6'd52: cur_byte = h2a(saved_y3[31:28]);
        6'd53: cur_byte = h2a(saved_y3[27:24]);
        6'd54: cur_byte = h2a(saved_y3[23:20]);
        6'd55: cur_byte = h2a(saved_y3[19:16]);
        6'd56: cur_byte = h2a(saved_y3[15:12]);
        6'd57: cur_byte = h2a(saved_y3[11:8]);
        6'd58: cur_byte = h2a(saved_y3[7:4]);
        6'd59: cur_byte = h2a(saved_y3[3:0]);
        6'd60: cur_byte = 8'h0D;
        6'd61: cur_byte = 8'h0A;
        default: cur_byte = 8'h00;
    endcase
end

// ─── UART message sender FSM (fast clock domain) ──────────────────────────────
// Triggered by kernel_done rising edge (kd_rise).
// Sends 62 ASCII bytes over UART one at a time.
localparam MS_IDLE = 2'd0;
localparam MS_SEND = 2'd1;
localparam MS_WAIT = 2'd2;
localparam MS_DONE = 2'd3;

reg [1:0] ms_state;

always @(posedge clk or posedge rst_sync) begin
    if (rst_sync) begin
        ms_state  <= MS_IDLE;
        msg_pos   <= 6'd0;
        uart_send <= 1'b0;
        uart_byte <= 8'h00;
    end else begin
        uart_send <= 1'b0;
        case (ms_state)
            MS_IDLE: begin
                if (kd_rise) begin
                    msg_pos  <= 6'd0;
                    ms_state <= MS_SEND;
                end
            end
            MS_SEND: begin
                if (!uart_busy) begin
                    uart_byte <= cur_byte;
                    uart_send <= 1'b1;
                    ms_state  <= MS_WAIT;
                end
            end
            MS_WAIT: begin
                if (!uart_busy && !uart_send) begin
                    if (msg_pos == 6'd61) ms_state <= MS_DONE;
                    else begin
                        msg_pos  <= msg_pos + 1;
                        ms_state <= MS_SEND;
                    end
                end
            end
            MS_DONE: ; // stay here — output sent
        endcase
    end
end

endmodule