// matmul_accelerator.sv
// Memory-mapped INT8 matrix multiply accelerator — 32-bit Tiny GPU Phase 21
//
// Ctrl registers decoded by top_level_gpu from data_mem addr >= 0x1F0:
//   offset 0 (0x1F0)  A_BASE  W   base addr of A matrix in data_mem
//   offset 1 (0x1F1)  B_BASE  W   base addr of B^T matrix in data_mem
//   offset 2 (0x1F2)  C_BASE  W   base addr of C output in data_mem
//   offset 3 (0x1F3)  M       W   rows of A / rows of C
//   offset 4 (0x1F4)  N       W   cols of B / cols of C
//   offset 5 (0x1F5)  K       W   inner dim, must be multiple of 4
//   offset 6 (0x1F6)  SCALE   W   arithmetic right-shift on accumulator before store
//   offset 7 (0x1F7)  START   W   write 1 to launch
//   offset 8 (0x1F8)  DONE    R   reads 1 when complete; cleared on next START
//
// Matrix layout in data_mem:
//   A[i][k_chunk]   at A_BASE + i*(K>>2) + k_chunk
//   B^T[j][k_chunk] at B_BASE + j*(K>>2) + k_chunk
//   C[i][j]         at C_BASE + i*N + j

module matmul_accelerator (
    input  logic        clk,
    input  logic        rst,

    // ctrl register write port
    input  logic        ctrl_wr_valid,
    input  logic [3:0]  ctrl_wr_addr,
    input  logic [31:0] ctrl_wr_data,

    // ctrl register read port
    input  logic [3:0]  ctrl_rd_addr,
    output logic [31:0] ctrl_rd_data,

    // matrix data memory port
    output logic        data_req_valid,
    output logic [31:0] data_req_addr,
    output logic        data_req_rw,      // 1 = read, 0 = write
    output logic [31:0] data_req_data,
    input  logic        data_resp_valid,
    input  logic [31:0] data_resp_data
);

    // ─────────────────────────────────────────────────────────────────────
    // FSM state
    // ─────────────────────────────────────────────────────────────────────
    typedef enum logic [3:0] {
        IDLE       = 4'd0,
        LOAD_A     = 4'd1,
        WAIT_A     = 4'd2,
        LOAD_B     = 4'd3,
        WAIT_B     = 4'd4,
        MAC_STATE  = 4'd5,
        STORE      = 4'd6,
        WAIT_STORE = 4'd7,
        NEXT_IJ    = 4'd8,
        DONE_SET   = 4'd9
    } state_t;

    state_t state;

    // ─────────────────────────────────────────────────────────────────────
    // MMIO config registers
    // These are host/core-visible registers.
    // They can be written only while accelerator is IDLE.
    // ─────────────────────────────────────────────────────────────────────
    logic [31:0] reg_a_base;
    logic [31:0] reg_b_base;
    logic [31:0] reg_c_base;
    logic [31:0] reg_m;
    logic [31:0] reg_n;
    logic [31:0] reg_k;
    logic [31:0] reg_scale;
    logic        reg_done;

    // ─────────────────────────────────────────────────────────────────────
    // Runtime-latched config
    // These are captured once on START and used for the full run.
    // This prevents later MMIO writes from corrupting an active matmul.
    // ─────────────────────────────────────────────────────────────────────
    logic [31:0] run_a_base;
    logic [31:0] run_b_base;
    logic [31:0] run_c_base;
    logic [31:0] run_m;
    logic [31:0] run_n;
    logic [31:0] run_k;
    logic [31:0] run_scale;
    logic [31:0] run_k_chunks;

    // ─────────────────────────────────────────────────────────────────────
    // Loop counters and datapath registers
    // ─────────────────────────────────────────────────────────────────────
    logic [31:0] i;
    logic [31:0] j;
    logic [31:0] k_chunk;

    logic [31:0] a_word;
    logic [31:0] b_word;

    logic signed [31:0] acc;

    // ─────────────────────────────────────────────────────────────────────
    // MMIO register writes
    // Ignore config writes while accelerator is running.
    // START is handled inside FSM.
    // DONE is read-only.
    // ─────────────────────────────────────────────────────────────────────
    always_ff @(posedge clk or posedge rst) begin
        if (rst) begin
            reg_a_base <= 32'b0;
            reg_b_base <= 32'b0;
            reg_c_base <= 32'b0;
            reg_m      <= 32'b0;
            reg_n      <= 32'b0;
            reg_k      <= 32'b0;
            reg_scale  <= 32'b0;
        end else if (ctrl_wr_valid && state == IDLE) begin
            case (ctrl_wr_addr)
                4'h0: reg_a_base <= ctrl_wr_data;
                4'h1: reg_b_base <= ctrl_wr_data;
                4'h2: reg_c_base <= ctrl_wr_data;
                4'h3: reg_m      <= ctrl_wr_data;
                4'h4: reg_n      <= ctrl_wr_data;
                4'h5: reg_k      <= ctrl_wr_data;
                4'h6: reg_scale  <= ctrl_wr_data;
                default: ;
            endcase
        end
    end

    // ─────────────────────────────────────────────────────────────────────
    // MMIO register reads
    // ─────────────────────────────────────────────────────────────────────
    always_comb begin
        case (ctrl_rd_addr)
            4'h0: ctrl_rd_data = reg_a_base;
            4'h1: ctrl_rd_data = reg_b_base;
            4'h2: ctrl_rd_data = reg_c_base;
            4'h3: ctrl_rd_data = reg_m;
            4'h4: ctrl_rd_data = reg_n;
            4'h5: ctrl_rd_data = reg_k;
            4'h6: ctrl_rd_data = reg_scale;
            4'h8: ctrl_rd_data = {31'b0, reg_done};
            default: ctrl_rd_data = 32'b0;
        endcase
    end

    // ─────────────────────────────────────────────────────────────────────
    // DOT4 combinational datapath
    // signed INT8 x signed INT8, accumulated into signed INT32
    // ─────────────────────────────────────────────────────────────────────
    logic signed [7:0]  a0;
    logic signed [7:0]  a1;
    logic signed [7:0]  a2;
    logic signed [7:0]  a3;

    logic signed [7:0]  b0;
    logic signed [7:0]  b1;
    logic signed [7:0]  b2;
    logic signed [7:0]  b3;

    logic signed [15:0] p0;
    logic signed [15:0] p1;
    logic signed [15:0] p2;
    logic signed [15:0] p3;

    logic signed [31:0] dot4_result;

    assign a0 = a_word[7:0];
    assign a1 = a_word[15:8];
    assign a2 = a_word[23:16];
    assign a3 = a_word[31:24];

    assign b0 = b_word[7:0];
    assign b1 = b_word[15:8];
    assign b2 = b_word[23:16];
    assign b3 = b_word[31:24];

    assign p0 = a0 * b0;
    assign p1 = a1 * b1;
    assign p2 = a2 * b2;
    assign p3 = a3 * b3;

    assign dot4_result =
        {{16{p0[15]}}, p0} +
        {{16{p1[15]}}, p1} +
        {{16{p2[15]}}, p2} +
        {{16{p3[15]}}, p3};

    // ─────────────────────────────────────────────────────────────────────
    // Main FSM
    // ─────────────────────────────────────────────────────────────────────
    always_ff @(posedge clk or posedge rst) begin
        if (rst) begin
            state          <= IDLE;

            reg_done       <= 1'b0;

            data_req_valid <= 1'b0;
            data_req_addr  <= 32'b0;
            data_req_rw    <= 1'b0;
            data_req_data  <= 32'b0;

            run_a_base     <= 32'b0;
            run_b_base     <= 32'b0;
            run_c_base     <= 32'b0;
            run_m          <= 32'b0;
            run_n          <= 32'b0;
            run_k          <= 32'b0;
            run_scale      <= 32'b0;
            run_k_chunks   <= 32'b0;

            i              <= 32'b0;
            j              <= 32'b0;
            k_chunk        <= 32'b0;

            a_word         <= 32'b0;
            b_word         <= 32'b0;
            acc            <= 32'sd0;
        end else begin
            // default: no memory request unless a state asserts it
            data_req_valid <= 1'b0;

            case (state)

                // ─────────────────────────────────────────────────────────
                // Wait for START
                // Latch all config on START.
                // ─────────────────────────────────────────────────────────
                IDLE: begin
                    if (ctrl_wr_valid && ctrl_wr_addr == 4'h7 && ctrl_wr_data[0]) begin
                        reg_done     <= 1'b0;

                        run_a_base   <= reg_a_base;
                        run_b_base   <= reg_b_base;
                        run_c_base   <= reg_c_base;
                        run_m        <= reg_m;
                        run_n        <= reg_n;
                        run_k        <= reg_k;
                        run_scale    <= reg_scale;
                        run_k_chunks <= reg_k >> 2;

                        i            <= 32'b0;
                        j            <= 32'b0;
                        k_chunk      <= 32'b0;
                        acc          <= 32'sd0;

                        state        <= LOAD_A;
                    end
                end

                // ─────────────────────────────────────────────────────────
                // Read A[i][k_chunk]
                // ─────────────────────────────────────────────────────────
                LOAD_A: begin
                    data_req_valid <= 1'b1;
                    data_req_rw    <= 1'b1;
                    data_req_addr  <= run_a_base + (i * run_k_chunks) + k_chunk;
                    data_req_data  <= 32'b0;

                    state          <= WAIT_A;
                end

                WAIT_A: begin
                    if (data_resp_valid) begin
                        a_word <= data_resp_data;
                        state  <= LOAD_B;
                    end
                end

                // ─────────────────────────────────────────────────────────
                // Read B^T[j][k_chunk]
                // ─────────────────────────────────────────────────────────
                LOAD_B: begin
                    data_req_valid <= 1'b1;
                    data_req_rw    <= 1'b1;
                    data_req_addr  <= run_b_base + (j * run_k_chunks) + k_chunk;
                    data_req_data  <= 32'b0;

                    state          <= WAIT_B;
                end

                WAIT_B: begin
                    if (data_resp_valid) begin
                        b_word <= data_resp_data;
                        state  <= MAC_STATE;
                    end
                end

                // ─────────────────────────────────────────────────────────
                // Accumulate one DOT4 chunk
                // ─────────────────────────────────────────────────────────
                MAC_STATE: begin
                    acc <= acc + dot4_result;

                    if (k_chunk + 1 >= run_k_chunks) begin
                        state <= STORE;
                    end else begin
                        k_chunk <= k_chunk + 1;
                        state   <= LOAD_A;
                    end
                end

                // ─────────────────────────────────────────────────────────
                // Store C[i][j]
                // ─────────────────────────────────────────────────────────
                STORE: begin
                    data_req_valid <= 1'b1;
                    data_req_rw    <= 1'b0;
                    data_req_addr  <= run_c_base + (i * run_n) + j;
                    data_req_data  <= $signed(acc) >>> run_scale[4:0];

                    state          <= WAIT_STORE;
                end

                WAIT_STORE: begin
                    if (data_resp_valid) begin
                        state <= NEXT_IJ;
                    end
                end

                // ─────────────────────────────────────────────────────────
                // Advance j, then i
                // ─────────────────────────────────────────────────────────
                NEXT_IJ: begin
                    acc     <= 32'sd0;
                    k_chunk <= 32'b0;

                    if (j + 1 >= run_n) begin
                        j <= 32'b0;

                        if (i + 1 >= run_m) begin
                            state <= DONE_SET;
                        end else begin
                            i     <= i + 1;
                            state <= LOAD_A;
                        end
                    end else begin
                        j     <= j + 1;
                        state <= LOAD_A;
                    end
                end

                // ─────────────────────────────────────────────────────────
                // Done visible to CPU polling at 0x1F8
                // ─────────────────────────────────────────────────────────
                DONE_SET: begin
                    reg_done <= 1'b1;
                    state    <= IDLE;
                end

                default: begin
                    state <= IDLE;
                end

            endcase
        end
    end

endmodule