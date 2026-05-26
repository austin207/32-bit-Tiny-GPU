module gpu_fpga_top (
    input  logic       clk,      // 27MHz, pin 52
    input  logic       rst_n,    // active-low button, pin 88
    output logic [5:0] led       // active-low LEDs
);

// ─── Parameters ──────────────────────────────────────────────────────────────
localparam NUM_CORES        = 4;
localparam THREADS_PER_CORE = 4;
localparam TOTAL_THREADS    = 16;
localparam PROG_DEPTH       = 64;   // enough for any kernel
localparam DATA_DEPTH       = 32;   // mem[0..31]

// ─── Reset synchronizer (2-FF, avoids metastability) ─────────────────────────
logic rst_r1, rst_sync;
always_ff @(posedge clk) begin
    rst_r1   <= ~rst_n;     // invert: rst_n low = reset active
    rst_sync <= rst_r1;
end

// ─── GPU port wires ───────────────────────────────────────────────────────────
logic        dcr_write_en;
logic [1:0]  dcr_addr;
logic [31:0] dcr_data;
logic        kernel_done;

logic [NUM_CORES-1:0]  prog_mem_req_valid;
logic [31:0]           prog_mem_req_addr  [NUM_CORES-1:0];
logic [NUM_CORES-1:0]  prog_mem_resp_valid;
logic [31:0]           prog_mem_resp_data [NUM_CORES-1:0];

logic [TOTAL_THREADS-1:0] data_mem_req_valid;
logic [31:0]              data_mem_req_addr [TOTAL_THREADS-1:0];
logic [TOTAL_THREADS-1:0] data_mem_req_rw;
logic [31:0]              data_mem_req_data [TOTAL_THREADS-1:0];
logic [TOTAL_THREADS-1:0] data_mem_resp_valid;
logic [31:0]              data_mem_resp_data [TOTAL_THREADS-1:0];

// ─── GPU instantiation ────────────────────────────────────────────────────────
gpu #(
    .NUM_CORES(NUM_CORES),
    .THREADS_PER_CORE(THREADS_PER_CORE)
) gpu_inst (
    .clk(clk),
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
    .data_mem_resp_data(data_mem_resp_data)
);

// ─── Auto-dispatch state machine ─────────────────────────────────────────────
// No host CPU on FPGA, so the wrapper handles DCR writes after reset.
// Sequence: wait 8 cycles → write num_blocks=1 → write blockDim=4 → pulse start
typedef enum logic [2:0] {
    BOOT_WAIT   = 3'd0,
    WRITE_NB    = 3'd1,
    WRITE_BD    = 3'd2,
    WRITE_START = 3'd3,
    RUNNING     = 3'd4
} dispatch_state_t;

dispatch_state_t dstate;
logic [3:0] boot_cnt;

always_ff @(posedge clk) begin
    if (rst_sync) begin
        dstate       <= BOOT_WAIT;
        boot_cnt     <= 0;
        dcr_write_en <= 0;
        dcr_addr     <= 0;
        dcr_data     <= 0;
    end else begin
        dcr_write_en <= 0;
        case (dstate)
            BOOT_WAIT: begin
                boot_cnt <= boot_cnt + 1;
                if (boot_cnt == 4'd7) dstate <= WRITE_NB;
            end
            WRITE_NB: begin
                dcr_write_en <= 1;
                dcr_addr     <= 2'b00;
                dcr_data     <= 32'd1;   // num_blocks = 1
                dstate       <= WRITE_BD;
            end
            WRITE_BD: begin
                dcr_write_en <= 1;
                dcr_addr     <= 2'b01;
                dcr_data     <= 32'd4;   // blockDim = 4
                dstate       <= WRITE_START;
            end
            WRITE_START: begin
                dcr_write_en <= 1;
                dcr_addr     <= 2'b10;
                dcr_data     <= 32'd0;   // start pulse
                dstate       <= RUNNING;
            end
            RUNNING: ;  // idle, GPU is running
        endcase
    end
end

// ─── Program memory: 4 BRAMs, one per core ───────────────────────────────────
// All 4 cores run the same kernel, so all 4 BRAMs hold the same content.
// BRAM has 1-cycle read latency, so resp_valid is req_valid delayed by 1 cycle.
logic [31:0] prog_bram [NUM_CORES-1:0] [0:PROG_DEPTH-1];
logic [NUM_CORES-1:0] prog_resp_valid_r;

initial begin
    for (int c = 0; c < NUM_CORES; c++)
        $readmemh("prog_mem.hex", prog_bram[c]);
end

genvar c;
generate
    for (c = 0; c < NUM_CORES; c++) begin : prog_mem_gen
        always_ff @(posedge clk) begin
            prog_resp_valid_r[c]   <= prog_mem_req_valid[c];
            prog_mem_resp_data[c]  <= prog_bram[c][prog_mem_req_addr[c][7:0]];
        end
        assign prog_mem_resp_valid[c] = prog_resp_valid_r[c];
    end
endgenerate

// ─── Data memory: 16 BRAMs, one per thread ───────────────────────────────────
// Each thread gets its own BRAM, all initialized identically with weights+inputs.
// This works for the forward pass: each thread reads shared data (weights, x)
// from its own copy, and writes to a unique address (y[i] at addr 20+i).
// After kernel_done, LED pattern shows completion.
logic [31:0] data_bram [TOTAL_THREADS-1:0] [0:DATA_DEPTH-1];
logic [TOTAL_THREADS-1:0] data_resp_valid_r;

genvar t;
generate
    for (t = 0; t < TOTAL_THREADS; t++) begin : data_mem_gen
        initial $readmemh("data_mem.hex", data_bram[t]);

        always_ff @(posedge clk) begin
            if (data_mem_req_valid[t]) begin
                if (data_mem_req_rw[t] == 1'b0) begin
                    // Write: rw=0 matches lsu.sv convention (read_write_switch=0 → write)
                    data_bram[t][data_mem_req_addr[t][7:0]] <= data_mem_req_data[t];
                end
                data_mem_resp_data[t] <= data_bram[t][data_mem_req_addr[t][7:0]];
            end
            data_resp_valid_r[t] <= data_mem_req_valid[t];
        end
        assign data_mem_resp_valid[t] = data_resp_valid_r[t];
    end
endgenerate

// ─── LED output ──────────────────────────────────────────────────────────────
// Tang Nano 20K LEDs are active-LOW.
// led[0] = kernel_done indicator (lights up when GPU finishes)
// led[5:1] = heartbeat from clock divider (shows board is alive)
logic [24:0] heartbeat;
always_ff @(posedge clk) heartbeat <= heartbeat + 1;

assign led[0] = ~kernel_done;
assign led[5:1] = ~heartbeat[24:20];

endmodule