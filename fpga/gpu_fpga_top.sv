// gpu_fpga_top.sv — Tang Nano 20K wrapper for 32-bit Tiny GPU
//
// Clock architecture:
//   clk      = 27 MHz board oscillator (pin 4, LVCMOS18)
//   clk_slow = 27 MHz / 8 = 3.375 MHz  → fed to GPU and all memory models
//
// Why clk_slow?
//   The critical path through the ALU (32-bit multiply chain) is ~146 ns.
//   27 MHz = 37 ns period — too fast. 3.375 MHz = 296 ns period — 150 ns slack.
//   All GPU logic, BRAMs, and DCR dispatch FSM run on clk_slow so that
//   req/resp handshake signals are in the same clock domain.
//   Only the heartbeat LED counter stays on fast clk (cosmetic only).
//
// Memory:
//   Program BRAM : 1 × 64-deep × 32-bit, preloaded with prog_mem.hex
//   Data BRAMs   : 4 × 32-deep × 32-bit, each preloaded with data_mem.hex
//                  (weights at 0-15, inputs at 16-19, targets at 24-27)
//
// LED output (active-LOW on Tang Nano 20K):
//   led[0]   = kernel_done (lights solid when GPU finishes forward pass)
//   led[5:1] = rolling blink from heartbeat counter (board-alive indicator)

module gpu_fpga_top (
    input  wire       clk,    // 27 MHz, pin 4 (Tang Nano 20K oscillator, LVCMOS18)
    input  wire       rst_n,  // active-low reset (power-on reset — no physical button)
    output wire [5:0] led     // active-low LEDs, pins 15 16 17 18 19 20
);

localparam NUM_CORES        = 1;
localparam THREADS_PER_CORE = 4;
localparam TOTAL_THREADS    = 4;
localparam PROG_DEPTH       = 64;
localparam DATA_DEPTH       = 32;

// ─── Reset synchronizer (2-FF, fast clock domain) ────────────────────────────
// Converts async rst_n to synchronous rst_sync in the fast clock domain.
// rst_sync is then used directly — it is stable well before clk_slow edges.
reg rst_r1, rst_sync;
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        rst_r1   <= 1'b1;
        rst_sync <= 1'b1;
    end else begin
        rst_r1   <= 1'b0;
        rst_sync <= rst_r1;
    end
end

// ─── Clock divider: 27 MHz → 3.375 MHz ───────────────────────────────────────
// Toggle clk_slow every 4 fast cycles → period = 8 fast cycles = 296 ns
// This gives ~150 ns of timing margin over the 146 ns critical path.
reg [2:0] clk_div;
reg       clk_slow;

always @(posedge clk or posedge rst_sync) begin
    if (rst_sync) begin
        clk_div  <= 3'd0;
        clk_slow <= 1'b0;
    end else begin
        if (clk_div == 3'd3) begin
            clk_div  <= 3'd0;
            clk_slow <= ~clk_slow;
        end else begin
            clk_div <= clk_div + 3'd1;
        end
    end
end

// ─── GPU port wires ───────────────────────────────────────────────────────────
wire        dcr_write_en;
wire [1:0]  dcr_addr;
wire [31:0] dcr_data;
wire        kernel_done;

wire [0:0]   prog_mem_req_valid;
wire [31:0]  prog_mem_req_addr;
wire [0:0]   prog_mem_resp_valid;
wire [31:0]  prog_mem_resp_data;

wire [3:0]   data_mem_req_valid;
wire [127:0] data_mem_req_addr;
wire [3:0]   data_mem_req_rw;
wire [127:0] data_mem_req_data;
wire [3:0]   data_mem_resp_valid;
wire [127:0] data_mem_resp_data;

// thread_keep_alive: synthesis observability guard from core module.
// XOR of all 4 thread write_data paths — keeps per-thread ALU and register
// file instances in the netlist by providing a traceable primary output path.
wire [31:0] thread_keep_alive;

// ─── GPU instance (runs on clk_slow) ─────────────────────────────────────────
gpu #(
    .NUM_CORES(NUM_CORES),
    .THREADS_PER_CORE(THREADS_PER_CORE)
) gpu_inst (
    .clk(clk_slow),           // slow clock — matches BRAM and dispatch domain
    .rst(rst_sync),
    .dcr_write_en(dcr_write_en),
    .dcr_addr(dcr_addr),
    .dcr_data(dcr_data),
    .kernel_done(kernel_done),
    .prog_mem_req_valid(prog_mem_req_valid),
    .prog_mem_req_addr(prog_mem_req_addr),
    .prog_mem_resp_valid(prog_mem_resp_valid),
    .prog_mem_resp_data(prog_mem_resp_data),
    .data_mem_req_valid(data_mem_req_valid),
    .data_mem_req_addr(data_mem_req_addr),
    .data_mem_req_rw(data_mem_req_rw),
    .data_mem_req_data(data_mem_req_data),
    .data_mem_resp_valid(data_mem_resp_valid),
    .data_mem_resp_data(data_mem_resp_data),
    .thread_keep_alive(thread_keep_alive)
);

// ─── Auto-dispatch FSM (clk_slow domain) ─────────────────────────────────────
// No host CPU on the FPGA, so this FSM writes the DCR registers automatically
// after reset. It runs on clk_slow so DCR pulses are a full slow cycle wide
// and guaranteed to be sampled by the GPU's DCR module.
//
// Sequence:
//   Wait 8 slow cycles → write num_blocks=1 → write blockDim=4 → pulse start
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
        dstate     <= 3'd0;
        boot_cnt   <= 4'd0;
        dcr_we_r   <= 1'b0;
        dcr_addr_r <= 2'd0;
        dcr_data_r <= 32'd0;
    end else begin
        dcr_we_r <= 1'b0;
        case (dstate)
            3'd0: begin
                // Wait 8 slow cycles after reset for all FFs to settle
                if (boot_cnt == 4'd7)
                    dstate <= 3'd1;
                else
                    boot_cnt <= boot_cnt + 4'd1;
            end
            3'd1: begin
                // Write DCR addr 0x00 = num_blocks = 1
                dcr_we_r   <= 1'b1;
                dcr_addr_r <= 2'b00;
                dcr_data_r <= 32'd1;
                dstate     <= 3'd2;
            end
            3'd2: begin
                // Write DCR addr 0x01 = blockDim = 4
                dcr_we_r   <= 1'b1;
                dcr_addr_r <= 2'b01;
                dcr_data_r <= 32'd4;
                dstate     <= 3'd3;
            end
            3'd3: begin
                // Write DCR addr 0x10 = start pulse
                dcr_we_r   <= 1'b1;
                dcr_addr_r <= 2'b10;
                dcr_data_r <= 32'd0;
                dstate     <= 3'd4;
            end
            3'd4: ;  // GPU is running, stay idle
        endcase
    end
end

// ─── Program memory: 1 BRAM (1 core, clk_slow domain) ───────────────────────
// 64 × 32-bit, preloaded with prog_mem.hex (phase4_forward kernel).
// BRAM runs on clk_slow: req on cycle N → resp on cycle N+1.
// The fetcher's valid/ready handshake handles this 1-cycle latency correctly.
reg [31:0] prog_bram [0:PROG_DEPTH-1];
initial $readmemh("prog_mem.hex", prog_bram);

reg        prog_resp_r;
reg [31:0] prog_data_r;

always @(posedge clk_slow or posedge rst_sync) begin
    if (rst_sync) begin
        prog_resp_r <= 1'b0;
        prog_data_r <= 32'd0;
    end else begin
        prog_resp_r <= prog_mem_req_valid[0];
        prog_data_r <= prog_bram[prog_mem_req_addr[7:0]];
    end
end

assign prog_mem_resp_valid = prog_resp_r;
assign prog_mem_resp_data  = prog_data_r;

// ─── Data memory: 4 BRAMs (4 threads, clk_slow domain) ──────────────────────
// Each thread gets its own 32 × 32-bit BRAM, all initialized identically.
// Memory layout (addresses):
//   0-15  : W[4][4] weights in Q8 (W[i][j] at addr i*4+j)
//   16-19 : x[4] input vector in Q8
//   20-23 : y[4] output (written by GPU during forward pass)
//   24-27 : t[4] target vector in Q8
//
// rw=0 means WRITE (matches lsu.sv: read_write_switch=0 on the write path)
// rw=1 means READ
//
// After kernel_done, thread N's BRAM holds y[N] at address 20+N.

reg [31:0] data_bram_0 [0:DATA_DEPTH-1];
reg [31:0] data_bram_1 [0:DATA_DEPTH-1];
reg [31:0] data_bram_2 [0:DATA_DEPTH-1];
reg [31:0] data_bram_3 [0:DATA_DEPTH-1];

initial begin
    $readmemh("data_mem.hex", data_bram_0);
    $readmemh("data_mem.hex", data_bram_1);
    $readmemh("data_mem.hex", data_bram_2);
    $readmemh("data_mem.hex", data_bram_3);
end

reg [3:0]   data_resp_r;
reg [127:0] data_data_r;

// BRAM macro: runs on clk_slow, handles read and write in same always block.
// Write takes effect immediately on the rising edge.
// Read data is registered one cycle later (resp_r delayed by 1).
`define DATA_BRAM(T, BRAM)                                            \
always @(posedge clk_slow or posedge rst_sync) begin                  \
    if (rst_sync) begin                                                \
        data_resp_r[T]          <= 1'b0;                               \
        data_data_r[T*32 +: 32] <= 32'd0;                             \
    end else begin                                                     \
        if (data_mem_req_valid[T]) begin                               \
            if (data_mem_req_rw[T] == 1'b0)                           \
                BRAM[data_mem_req_addr[T*32 +: 32]] <=                 \
                    data_mem_req_data[T*32 +: 32];                     \
            data_data_r[T*32 +: 32] <=                                 \
                BRAM[data_mem_req_addr[T*32 +: 32]];                  \
        end                                                            \
        data_resp_r[T] <= data_mem_req_valid[T];                       \
    end                                                                \
end

`DATA_BRAM(0, data_bram_0)
`DATA_BRAM(1, data_bram_1)
`DATA_BRAM(2, data_bram_2)
`DATA_BRAM(3, data_bram_3)

assign data_mem_resp_valid = data_resp_r;
assign data_mem_resp_data  = data_data_r;

// ─── LEDs (active-LOW on Tang Nano 20K) ──────────────────────────────────────
// led[0]  : kernel_done — goes LOW (lights up) when GPU completes
// led[5:1]: rolling blink from heartbeat on fast clk — shows board is alive
//           at 27 MHz, bits [22:17] blink at ~1.6 Hz (visible without flicker)
reg [24:0] heartbeat;
always @(posedge clk) heartbeat <= heartbeat + 25'd1;

// thread_keep_alive[31]: synthesis observability anchor.
// For Q8 positive values this bit is 0 at runtime so led[0] behaves as ~kernel_done.
// Synthesis cannot prove this statically (depends on threadIdx runtime values),
// so the full thread_keep_alive → write_data → alu → regfile chain is preserved.
assign led[0]   = ~(kernel_done | thread_keep_alive[31]);
assign led[5:1] = ~heartbeat[22:18];

endmodule