module mem_controller #(
    parameter THREADS_PER_CORE = 4
)(
    input  logic clk,
    input  logic rst,

    input  logic [THREADS_PER_CORE-1:0]       req_valid,
    input  logic [31:0]                       req_addr  [THREADS_PER_CORE-1:0],
    input  logic [THREADS_PER_CORE-1:0]       req_rw,
    input  logic [31:0]                       req_data  [THREADS_PER_CORE-1:0],

    output logic [THREADS_PER_CORE-1:0]       resp_valid,

    // IMPORTANT:
    // Packed 2D response data, matching core.sv:
    //   logic [THREADS_PER_CORE-1:0][31:0] lsu_resp_data;
    //
    // Old unpacked form caused this failure:
    //   mc_out_data0=5 but lsu0_resp_data=0
    output logic [THREADS_PER_CORE-1:0][31:0] resp_data,

    output logic        mem_req_valid,
    output logic [31:0] mem_req_addr,
    output logic        mem_req_rw,
    output logic [31:0] mem_req_data,
    input  logic        mem_resp_valid,
    input  logic [31:0] mem_resp_data
);

localparam PTR_W = (THREADS_PER_CORE <= 1) ? 1 : $clog2(THREADS_PER_CORE);

typedef enum logic {
    IDLE = 1'b0,
    WAIT = 1'b1
} state_t;

state_t state;

logic [PTR_W-1:0] rr_ptr;
logic [PTR_W-1:0] in_flight;

// ── Request buffer ────────────────────────────────────────────────────────────
// LSU req_valid is a ONE-CYCLE PULSE. If the controller is in WAIT when
// another thread fires req_valid, that pulse is lost without this buffer.
// pending latches the pulse. pending_addr/rw/data capture the payload
// on the same cycle so it remains readable later.
logic [THREADS_PER_CORE-1:0] pending;
logic [31:0]                 pending_addr [THREADS_PER_CORE-1:0];
logic [THREADS_PER_CORE-1:0] pending_rw;
logic [31:0]                 pending_data [THREADS_PER_CORE-1:0];

always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        pending    <= '0;
        pending_rw <= '0;

        for (int i = 0; i < THREADS_PER_CORE; i++) begin
            pending_addr[i] <= 32'b0;
            pending_data[i] <= 32'b0;
        end
    end else begin
        for (int i = 0; i < THREADS_PER_CORE; i++) begin
            if (req_valid[i]) begin
                pending[i]      <= 1'b1;
                pending_addr[i] <= req_addr[i];
                pending_rw[i]   <= req_rw[i];
                pending_data[i] <= req_data[i];
            end
        end

        // Clear served thread when memory responds.
        if (state == WAIT && mem_resp_valid) begin
            pending[in_flight] <= 1'b0;
        end
    end
end

// Scan source: pending buffered requests OR same-cycle req_valid pulses.
logic [THREADS_PER_CORE-1:0] scan_valid;
assign scan_valid = pending | req_valid;

// ── Round-robin scan ──────────────────────────────────────────────────────────
logic [PTR_W-1:0] next_thread;
logic             found;
integer           scan_idx;

always_comb begin
    next_thread = '0;
    found       = 1'b0;
    scan_idx    = 0;

    for (int j = 0; j < THREADS_PER_CORE; j++) begin
        scan_idx = rr_ptr + j;

        if (scan_idx >= THREADS_PER_CORE)
            scan_idx = scan_idx - THREADS_PER_CORE;

        if (!found && scan_valid[scan_idx]) begin
            next_thread = scan_idx;
            found       = 1'b1;
        end
    end
end

// ── Request payload mux ───────────────────────────────────────────────────────
// If req_valid[i] is live this cycle, use it directly.
// Otherwise use buffered pending data.
logic [31:0] sel_addr;
logic        sel_rw;
logic [31:0] sel_data;

always_comb begin
    if (req_valid[next_thread]) begin
        sel_addr = req_addr[next_thread];
        sel_rw   = req_rw[next_thread];
        sel_data = req_data[next_thread];
    end else begin
        sel_addr = pending_addr[next_thread];
        sel_rw   = pending_rw[next_thread];
        sel_data = pending_data[next_thread];
    end
end

// ── FSM ───────────────────────────────────────────────────────────────────────
always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        state         <= IDLE;
        rr_ptr        <= '0;
        in_flight     <= '0;

        mem_req_valid <= 1'b0;
        mem_req_addr  <= 32'b0;
        mem_req_rw    <= 1'b0;
        mem_req_data  <= 32'b0;

        resp_valid    <= '0;

        for (int i = 0; i < THREADS_PER_CORE; i++) begin
            resp_data[i] <= 32'b0;
        end
    end else begin
        // Default: no thread response this cycle.
        resp_valid <= '0;

        case (state)
            IDLE: begin
                if (found) begin
                    in_flight     <= next_thread;

                    mem_req_valid <= 1'b1;
                    mem_req_addr  <= sel_addr;
                    mem_req_rw    <= sel_rw;
                    mem_req_data  <= sel_data;

                    state         <= WAIT;
                end else begin
                    mem_req_valid <= 1'b0;
                end
            end

            WAIT: begin
                if (mem_resp_valid) begin
                    resp_valid[in_flight] <= 1'b1;

                    // This now writes into packed resp_data[in_flight],
                    // which matches core.sv lsu_resp_data[i].
                    resp_data[in_flight]  <= mem_resp_data;

                    rr_ptr                <= PTR_W'(in_flight + 1);
                    mem_req_valid         <= 1'b0;
                    state                 <= IDLE;
                end
            end

            default: begin
                state         <= IDLE;
                mem_req_valid <= 1'b0;
                resp_valid    <= '0;
            end
        endcase
    end
end

endmodule