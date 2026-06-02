// gpu_fpga_top.sv — Tang Nano 20K wrapper for 32-bit SIMT GPU
//
// Clock:
//   clk      = 27 MHz onboard oscillator (pin 4, LVCMOS33)
//   clk_slow = 27 MHz / 8 = 3.375 MHz — fed to GPU and all BRAMs
//   UART TX runs on fast clk (27 MHz) for accurate 115200 baud
//
// Configuration:
//   NUM_CORES=4, THREADS_PER_CORE=4, num_blocks=1, blockDim=4
//   Dispatcher assigns the single block to core 0; cores 1-3 stay idle.
//   Threads 0-3 run SIMT ReLU: if (z > 0) keep, else zero.
//
// Memory interface (vs SIMD version):
//   Prog memory: 4 BRAMs (one per core), packed 128-bit port
//   Data memory: 4 BRAMs (one per core), packed 128-bit port
//   mem_controller inside each core serialises 4-thread requests
//   — wrapper sees one clean req/resp channel per core.
//
// Boot sequence:
//   num_blocks=1, blockDim=4, then single start pulse.
//   SIMD version needed continuous dispatch_en because it ran
//   4 sequential blocks through 1 core. SIMT runs 1 block with
//   4 threads — dispatcher fills it in one cycle, no loop needed.
//
// UART output (115200 8N1, pin 69 → BL616 USB-UART bridge):
//   SIMT GPU\r\n
//   T:XXXXXXXX\r\n        (clk_slow cycles, 1 cycle = 296 ns)
//   R:YYYYYYYY YYYYYYYY YYYYYYYY YYYYYYYY\r\n  (mem[4..7])
//
//   Expected for SIMT ReLU with inputs [+5, -3, +8, -1]:
//     R:00000005 00000000 00000008 00000000
//
// Result capture:
//   Snoops core 0's data write bus. mem_controller serialises
//   T0..T3 writes, so each write to mem[4..7] appears as a
//   separate req_valid pulse on data_mem_req_valid[0].
//
// LEDs (active-LOW):
//   led[0]   = kernel_done (solid ON when inference finishes)
//   led[5:1] = rolling heartbeat (~1.6 Hz on fast clk)

module gpu_fpga_top (
    input  wire       clk,       // 27 MHz, pin 4
    input  wire       rst_n,     // unused — replaced by POR counter
    output wire [5:0] led,       // active-LOW LEDs
    output wire       uart_tx    // 115200 8N1 → BL616, pin 69
);

localparam NUM_CORES        = 4;
localparam THREADS_PER_CORE = 4;
localparam PROG_DEPTH       = 64;    // words per core (64 × 32-bit)
localparam DATA_DEPTH       = 256;   // words per core (256 × 32-bit)

// ─── Power-on reset (no physical button) ─────────────────────────────────────
reg [7:0] por_cnt = 0;
wire      rst_raw = !por_cnt[7];
always @(posedge clk) if (!por_cnt[7]) por_cnt <= por_cnt + 1;

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

// ─── GPU port wires — 4-wide packed interfaces ───────────────────────────────
wire        dcr_write_en;
wire [1:0]  dcr_addr;
wire [31:0] dcr_data;
wire        kernel_done;
wire [31:0] thread_keep_alive;

// Prog memory: 1 port per core, packed 128-bit address/data buses
wire [NUM_CORES-1:0]        prog_mem_req_valid;
wire [(NUM_CORES*32)-1:0]   prog_mem_req_addr;
wire [NUM_CORES-1:0]        prog_mem_resp_valid;
wire [(NUM_CORES*32)-1:0]   prog_mem_resp_data;

// Data memory: 1 port per core (mem_controller has already arbitrated threads)
wire [NUM_CORES-1:0]        data_mem_req_valid;
wire [(NUM_CORES*32)-1:0]   data_mem_req_addr;
wire [NUM_CORES-1:0]        data_mem_req_rw;     // 1=read, 0=write (lsu.sv convention)
wire [(NUM_CORES*32)-1:0]   data_mem_req_data;
wire [NUM_CORES-1:0]        data_mem_resp_valid;
wire [(NUM_CORES*32)-1:0]   data_mem_resp_data;

// ─── GPU instance (clk_slow domain) ──────────────────────────────────────────
gpu #(
    .NUM_CORES       (NUM_CORES),
    .THREADS_PER_CORE(THREADS_PER_CORE)
) gpu_inst (
    .clk               (clk_slow),
    .rst               (rst_sync),
    .dcr_write_en      (dcr_write_en),
    .dcr_addr          (dcr_addr),
    .dcr_data          (dcr_data),
    .kernel_done       (kernel_done),
    .thread_keep_alive (thread_keep_alive),
    .prog_mem_req_valid(prog_mem_req_valid),
    .prog_mem_req_addr (prog_mem_req_addr),
    .prog_mem_resp_valid(prog_mem_resp_valid),
    .prog_mem_resp_data (prog_mem_resp_data),
    .data_mem_req_valid(data_mem_req_valid),
    .data_mem_req_addr (data_mem_req_addr),
    .data_mem_req_rw   (data_mem_req_rw),
    .data_mem_req_data (data_mem_req_data),
    .data_mem_resp_valid(data_mem_resp_valid),
    .data_mem_resp_data (data_mem_resp_data)
);

// ─── Boot dispatch FSM (clk_slow domain) ─────────────────────────────────────
// SIMT: num_blocks=1, blockDim=4 → single start pulse is sufficient.
// (SIMD needed continuous dispatch_en because 4 blocks ran sequentially
//  through 1 core. SIMT runs 4 threads in 1 block — dispatcher fills it
//  in one cycle and kernel_done fires when that block completes.)
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
            3'd0: begin  // startup hold — let GPU come out of reset cleanly
                if (boot_cnt == 4'd7) dstate <= 1;
                else boot_cnt <= boot_cnt + 1;
            end
            3'd1: begin  // write num_blocks = 1
                dcr_we_r <= 1; dcr_addr_r <= 2'b00; dcr_data_r <= 32'd1;
                dstate <= 2;
            end
            3'd2: begin  // write blockDim = 4 (one block of 4 threads)
                dcr_we_r <= 1; dcr_addr_r <= 2'b01; dcr_data_r <= 32'd4;
                dstate <= 3;
            end
            3'd3: begin  // single start pulse — dispatcher assigns block 0 to core 0
                dcr_we_r <= 1; dcr_addr_r <= 2'b10; dcr_data_r <= 32'd1;
                dstate <= 4;
            end
            3'd4: ;  // idle — GPU is running, wait for kernel_done
        endcase
    end
end

// ─── Cycle timer (clk_slow domain) ───────────────────────────────────────────
// Counts from start pulse to kernel_done. Resolution: 296 ns per tick.
reg [31:0] cycle_count;
reg        timing_active;
wire       start_pulse = dcr_we_r && (dcr_addr_r == 2'b10);

always @(posedge clk_slow or posedge rst_sync) begin
    if (rst_sync) begin
        cycle_count   <= 32'd0;
        timing_active <= 1'b0;
    end else if (start_pulse && !timing_active) begin
        cycle_count   <= 32'd0;
        timing_active <= 1'b1;
    end else if (timing_active) begin
        if (!kernel_done) cycle_count <= cycle_count + 1;
        else              timing_active <= 1'b0;
    end
end

// ─── Result capture — snoop core 0 data write bus ────────────────────────────
// SIMT ReLU: T0 writes mem[4], T1 writes mem[5], T2 writes mem[6], T3 writes mem[7].
// mem_controller serialises these → 4 separate req_valid pulses on port 0.
// Capture each write address to reconstruct the full output vector.
reg [31:0] result [0:3];
always @(posedge clk_slow) begin
    if (data_mem_req_valid[0] && (data_mem_req_rw[0] == 1'b0)) begin
        case (data_mem_req_addr[31:0])
            32'd4: result[0] <= data_mem_req_data[31:0];
            32'd5: result[1] <= data_mem_req_data[31:0];
            32'd6: result[2] <= data_mem_req_data[31:0];
            32'd7: result[3] <= data_mem_req_data[31:0];
            default: ;
        endcase
    end
end

// ─── Program BRAMs: 4 × PROG_DEPTH, one per core (clk_slow domain) ───────────
// All 4 BRAMs load the same kernel hex — each core runs independently.
// 1-cycle latency: req_valid → resp_valid next cycle.
genvar p;
generate
    for (p = 0; p < NUM_CORES; p = p + 1) begin : prog_mem_gen
        reg [31:0] bram [0:PROG_DEPTH-1];
        reg        resp_r;
        reg [31:0] data_r;

        // Extract this core's slice once for readability
        wire [31:0] req_addr_p = prog_mem_req_addr[p*32+:32];

        initial $readmemh("prog_mem.hex", bram);

        always @(posedge clk_slow or posedge rst_sync) begin
            if (rst_sync) begin resp_r <= 0; data_r <= 0; end
            else begin
                // Read every cycle (BRAM read-before-write, no hazard for RO prog mem)
                resp_r <= prog_mem_req_valid[p];
                data_r <= bram[req_addr_p[5:0]];   // [5:0] → depth 64
            end
        end

        assign prog_mem_resp_valid[p]       = resp_r;
        assign prog_mem_resp_data[p*32+:32] = data_r;
    end
endgenerate

// ─── Data BRAMs: 4 × DATA_DEPTH, one per core (clk_slow domain) ──────────────
// Each core's mem_controller has already serialised 4 thread requests
// into a single valid/addr/rw/data channel. The wrapper provides one
// simple 1-cycle-latency BRAM bank per core — no further arbitration needed.
//
// Read/write convention (lsu.sv): rw=1 → read, rw=0 → write.
// On a write cycle, data_r returns the old value — this is harmless
// because the LSU only checks resp_valid on writes, not resp_data.
genvar c;
generate
    for (c = 0; c < NUM_CORES; c = c + 1) begin : data_mem_gen
        reg [31:0] bram [0:DATA_DEPTH-1];
        reg        resp_r;
        reg [31:0] data_r;

        // Extract this core's slice once — avoids nested part-select
        wire [31:0] req_addr_c = data_mem_req_addr[c*32+:32];
        wire [31:0] req_data_c = data_mem_req_data[c*32+:32];

        initial $readmemh("data_mem.hex", bram);

        always @(posedge clk_slow or posedge rst_sync) begin
            if (rst_sync) begin resp_r <= 0; data_r <= 0; end
            else begin
                if (data_mem_req_valid[c]) begin
                    if (!data_mem_req_rw[c])                // rw=0 → write
                        bram[req_addr_c[7:0]] <= req_data_c;
                    data_r <= bram[req_addr_c[7:0]];        // always read back
                end
                resp_r <= data_mem_req_valid[c];
            end
        end

        assign data_mem_resp_valid[c]       = resp_r;
        assign data_mem_resp_data[c*32+:32] = data_r;
    end
endgenerate

// ─── LEDs (active-LOW) ────────────────────────────────────────────────────────
reg [24:0] heartbeat;
always @(posedge clk) heartbeat <= heartbeat + 1;

assign led[0]   = ~(kernel_done | thread_keep_alive[31]);
assign led[5:1] = ~heartbeat[22:18];

// ─── UART TX module (27 MHz fast clock, 115200 baud, 8N1) ────────────────────
// Divisor = 27,000,000 / 115,200 = 234  (0.16% error)
localparam UART_DIV = 8'd234;

reg [7:0] uart_byte;
reg       uart_send;
wire      uart_busy;
reg       uart_tx_r;
assign uart_tx   = uart_tx_r;

reg [7:0] u_clk_cnt;
reg [3:0] u_bit_cnt;
reg [9:0] u_shift;
reg       u_sending;
assign uart_busy = u_sending;

always @(posedge clk or posedge rst_sync) begin
    if (rst_sync) begin
        uart_tx_r <= 1; u_sending <= 0;
        u_clk_cnt <= 0; u_bit_cnt <= 0; u_shift <= 0;
    end else if (!u_sending && uart_send) begin
        u_shift   <= {1'b1, uart_byte, 1'b0};
        u_sending <= 1; u_clk_cnt <= 0; u_bit_cnt <= 0;
    end else if (u_sending) begin
        if (u_clk_cnt == UART_DIV - 1) begin
            u_clk_cnt <= 0;
            uart_tx_r <= u_shift[0];
            u_shift   <= {1'b1, u_shift[9:1]};
            if (u_bit_cnt == 9) u_sending <= 0;
            else u_bit_cnt <= u_bit_cnt + 1;
        end else u_clk_cnt <= u_clk_cnt + 1;
    end else uart_tx_r <= 1;
end

// ─── CDC: kernel_done (clk_slow) → fast clock domain ─────────────────────────
reg kd_s1, kd_s2, kd_s3;
always @(posedge clk) begin
    kd_s1 <= kernel_done; kd_s2 <= kd_s1; kd_s3 <= kd_s2;
end
wire kd_rise = kd_s2 & ~kd_s3;

// ─── CDC: latch cycle_count + results on kernel_done ─────────────────────────
// kernel_done is a stable flag (never de-asserts until reset), so
// result[] and cycle_count are stable before kd_rise fires on clk.
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

// ─── Hex nibble → ASCII ───────────────────────────────────────────────────────
function [7:0] h2a;
    input [3:0] n;
    h2a = (n < 4'hA) ? (8'h30 + {4'b0, n}) : (8'h57 + {4'b0, n});
endfunction

// ─── UART message byte lookup (62 bytes) ─────────────────────────────────────
// "SIMT GPU\r\n"  (10 bytes, pos  0-9)
// "T:XXXXXXXX\r\n"  (12 bytes, pos 10-21)
// "R:YYYYYYYY YYYYYYYY YYYYYYYY YYYYYYYY\r\n"  (40 bytes, pos 22-61)
//   Y = mem[4] mem[5] mem[6] mem[7]  (SIMT ReLU outputs)
reg [7:0] cur_byte;
reg [5:0] msg_pos;

always @(*) begin
    case (msg_pos)
        // "SIMT GPU\r\n"
        6'd0:  cur_byte = "S";
        6'd1:  cur_byte = "I";
        6'd2:  cur_byte = "M";
        6'd3:  cur_byte = "T";
        6'd4:  cur_byte = " ";
        6'd5:  cur_byte = "G";
        6'd6:  cur_byte = "P";
        6'd7:  cur_byte = "U";
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
        // "R: " — R for ReLU outputs
        6'd22: cur_byte = "R";
        6'd23: cur_byte = ":";
        6'd24: cur_byte = " ";
        // mem[4] — T0 ReLU output
        6'd25: cur_byte = h2a(saved_y0[31:28]);
        6'd26: cur_byte = h2a(saved_y0[27:24]);
        6'd27: cur_byte = h2a(saved_y0[23:20]);
        6'd28: cur_byte = h2a(saved_y0[19:16]);
        6'd29: cur_byte = h2a(saved_y0[15:12]);
        6'd30: cur_byte = h2a(saved_y0[11:8]);
        6'd31: cur_byte = h2a(saved_y0[7:4]);
        6'd32: cur_byte = h2a(saved_y0[3:0]);
        6'd33: cur_byte = " ";
        // mem[5] — T1 ReLU output
        6'd34: cur_byte = h2a(saved_y1[31:28]);
        6'd35: cur_byte = h2a(saved_y1[27:24]);
        6'd36: cur_byte = h2a(saved_y1[23:20]);
        6'd37: cur_byte = h2a(saved_y1[19:16]);
        6'd38: cur_byte = h2a(saved_y1[15:12]);
        6'd39: cur_byte = h2a(saved_y1[11:8]);
        6'd40: cur_byte = h2a(saved_y1[7:4]);
        6'd41: cur_byte = h2a(saved_y1[3:0]);
        6'd42: cur_byte = " ";
        // mem[6] — T2 ReLU output
        6'd43: cur_byte = h2a(saved_y2[31:28]);
        6'd44: cur_byte = h2a(saved_y2[27:24]);
        6'd45: cur_byte = h2a(saved_y2[23:20]);
        6'd46: cur_byte = h2a(saved_y2[19:16]);
        6'd47: cur_byte = h2a(saved_y2[15:12]);
        6'd48: cur_byte = h2a(saved_y2[11:8]);
        6'd49: cur_byte = h2a(saved_y2[7:4]);
        6'd50: cur_byte = h2a(saved_y2[3:0]);
        6'd51: cur_byte = " ";
        // mem[7] — T3 ReLU output
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
localparam MS_IDLE = 2'd0, MS_SEND = 2'd1, MS_WAIT = 2'd2, MS_DONE = 2'd3;
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
            MS_DONE: ;  // stay — output sent, board idle until reset
        endcase
    end
end

endmodule