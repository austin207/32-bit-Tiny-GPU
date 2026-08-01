#include "codegen.h"
#include "lexer.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define R0  0    /* always zero                     */
#define R29 29   /* threadIdx                        */
#define R30 30   /* blockIdx                         */
#define R31 31   /* blockDim                         */

/* NZP mask constants matching ISA */
#define NZP_N   0b100
#define NZP_Z   0b010
#define NZP_P   0b001
#define NZP_NZ  0b110
#define NZP_NP  0b101
#define NZP_ZP  0b011
#define NZP_ALL 0b111

/* ── Codegen context ─────────────────────────────────────────────────────── */
typedef struct {
    InstrBuf         *buf;
    const KernelSyms *syms;
    const char       *filename;
    int               had_error;
    int               next_tmp;   /* reset to SEMA_TMP_BASE per statement */
} CGen;

static void cg_err(CGen *g, int line, int col, const char *msg) {
    fprintf(stderr, "%s:%d:%d: codegen: %s\n",
            g->filename ? g->filename : "?", line, col, msg);
    g->had_error = 1;
}

static int alloc_tmp(CGen *g) {
    if (g->next_tmp >= SEMA_TMP_ONE) {
        fprintf(stderr, "codegen: out of temporary registers\n");
        g->had_error = 1;
        return SEMA_TMP_ONE - 1;
    }
    return g->next_tmp++;
}

static void reset_tmp(CGen *g) { g->next_tmp = SEMA_TMP_BASE; }

/* Emit a "move": dst = src (via ADD dst, src, R0). */
static void emit_mov(InstrBuf *buf, int dst, int src) {
    if (dst != src) emit_add(buf, dst, src, R0);
}

/* Return the NZP mask for a given comparison op (cond is taken when mask matches). */
static int nzp_for_op(int op) {
    switch (op) {
        case TOK_GT:  return NZP_P;
        case TOK_LT:  return NZP_N;
        case TOK_GEQ: return NZP_ZP;
        case TOK_LEQ: return NZP_NZ;
        case TOK_EQ:  return NZP_Z;
        case TOK_NEQ: return NZP_NP;
        default:      return NZP_ALL;
    }
}

/* Invert a 3-bit NZP mask. */
//static int nzp_invert(int mask) { return (~mask) & 0x7; }

/* Build and patch a BRnzp word back into the buffer. */
static void patch_brnzp(InstrBuf *buf, int idx, int nzp, int sync_off, int branch_off) {
    uint32_t word = ((uint32_t)0x0E            << 26)
                  | ((uint32_t)(nzp & 0x7)     << 23)
                  | ((uint32_t)(sync_off   & 0x7FF) << 12)
                  | ((uint32_t)(branch_off & 0xFFF));
    ibuf_patch(buf, idx, word);
}

/* ── Expression evaluation ────────────────────────────────────────────────── */
/* Returns register holding result. May emit instructions. */
static int eval_expr(CGen *g, const Expr *e) {
    if (!e) { cg_err(g, 0, 0, "null expression"); return R0; }

    switch (e->kind) {

        case EXPR_INT_LIT: {
            int t = alloc_tmp(g);
            emit_const(g->buf, t, e->ival);
            return t;
        }
        case EXPR_IDENT: {
            int r = syms_lookup(g->syms, e->name);
            if (r < 0) { cg_err(g, e->line, e->col, "undefined variable"); return R0; }
            return r;
        }
        case EXPR_THREAD_IDX: return R29;
        case EXPR_BLOCK_IDX:  return R30;
        case EXPR_BLOCK_DIM:  return R31;

        case EXPR_BINOP: {
            /* Comparison ops are handled at the statement level (if/for), not here. */
            int lreg = eval_expr(g, e->binop.left);
            int rreg = eval_expr(g, e->binop.right);
            int dst  = alloc_tmp(g);
            switch (e->binop.op) {
                case TOK_PLUS:    emit_add (g->buf, dst, lreg, rreg); break;
                case TOK_MINUS:   emit_sub (g->buf, dst, lreg, rreg); break;
                case TOK_STAR:    emit_imul(g->buf, dst, lreg, rreg); break;
                case TOK_SLASH:   emit_div (g->buf, dst, lreg, rreg); break;
                case TOK_PERCENT: emit_mod (g->buf, dst, lreg, rreg); break;
                case TOK_SHR:     emit_sar (g->buf, dst, lreg, rreg); break;
                case TOK_SHL:     emit_shl (g->buf, dst, lreg, rreg); break;
                case TOK_AMP:     emit_and (g->buf, dst, lreg, rreg); break;
                case TOK_PIPE:    emit_or  (g->buf, dst, lreg, rreg); break;
                case TOK_CARET:   emit_xor (g->buf, dst, lreg, rreg); break;
                default:
                    cg_err(g, e->line, e->col,
                           "comparison op not valid in arithmetic expression");
            }
            return dst;
        }

        case EXPR_UNOP: {
            int sreg = eval_expr(g, e->unop.operand);
            int dst  = alloc_tmp(g);
            switch (e->unop.op) {
                case TOK_MINUS:
                    emit_sub(g->buf, dst, R0, sreg);   /* 0 - x = -x */
                    break;
                case TOK_TILDE:
                    emit_not(g->buf, dst, sreg);
                    break;
                default:
                    cg_err(g, e->line, e->col, "unsupported unary op");
            }
            return dst;
        }

        case EXPR_MEM_LOAD: {
            int addr = eval_expr(g, e->mem_load.addr);
            int dst  = alloc_tmp(g);
            emit_ldr(g->buf, dst, addr, 0);
            return dst;
        }

        case EXPR_FMA: {
            int a = eval_expr(g, e->fma.a);
            int b = eval_expr(g, e->fma.b);
            int c = eval_expr(g, e->fma.c);
            int dst = alloc_tmp(g);
            emit_fma(g->buf, dst, a, b, c);
            return dst;
        }

        case EXPR_DOT4: {
            /* dot4(a, b) = packed INT8x4 dot product, alu.sv 6'h16:
             * result = rs3 + (a0*b0 + a1*b1 + a2*b2 + a3*b3) over the four
             * signed INT8 lanes of a/b. Not FMA (6'h0C, plain scalar
             * multiply-add) -- that was silently producing a scalar
             * multiply instead of a packed dot product. */
            int a = eval_expr(g, e->dot4.a);
            int b = eval_expr(g, e->dot4.b);
            int dst = alloc_tmp(g);
            emit_dot(g->buf, dst, a, b, R0);
            return dst;
        }

        case EXPR_EXP8: {
            int xreg = eval_expr(g, e->exp8.x);
            int dst  = alloc_tmp(g);
            emit_exp8(g->buf, dst, xreg);
            return dst;
        }

        default:
            cg_err(g, e->line, e->col, "unsupported expression kind");
            return R0;
    }
}

/* ── Statement code generation ────────────────────────────────────────────── */
static void emit_stmtlist(CGen *g, const StmtList *list);

static void emit_stmt(CGen *g, const Stmt *s) {
    reset_tmp(g);
    if (g->had_error) return;

    switch (s->kind) {

        /* int name = expr; */
        case STMT_VAR_DECL: {
            int dst = syms_lookup(g->syms, s->var_decl.name);
            int src = eval_expr(g, s->var_decl.init);
            emit_mov(g->buf, dst, src);
            break;
        }

        /* name = expr; */
        case STMT_ASSIGN: {
            int dst = syms_lookup(g->syms, s->assign.name);
            int src = eval_expr(g, s->assign.val);
            emit_mov(g->buf, dst, src);
            break;
        }

        /* mem[addr] = val; */
        case STMT_MEM_STORE: {
            int val_reg  = eval_expr(g, s->mem_store.val);
            int addr_reg = eval_expr(g, s->mem_store.addr);
            emit_str(g->buf, val_reg, addr_reg, 0);
            break;
        }

        /* if (lhs op rhs) { then } [else { els }]
         *
         * Layout (taken-group-first):
         *   CMP lhs, rhs
         *   BRnzp cond_mask, S1, B1        <── backpatch: S1=B1=2+len_else
         *   [else body]                     <── NOT-TAKEN (falls through)
         *   BRnzp ALL, S2, B2               <── unconditional skip; backpatch: S2=B2=2+len_then
         *   SYNC                            <── first SYNC (TAKEN lands here, falls into then body)
         *   [then body]
         *   SYNC                            <── second SYNC (full reconvergence)
         *
         * Each thread's PC advances on its own NZP every cycle regardless of
         * the scheduler's divergence detection (core.sv: pc_en & active_mask[i]
         * gates PC update, but branch/fallthrough decision is per-thread NZP).
         * Divergence detection only decides which threads get frozen
         * afterward -- it has no bearing on whether a single/uniform thread
         * follows its own branch. So without the unconditional skip, a
         * not-taken thread has nothing to jump over the then body with: it
         * just walks CMP -> BRnzp(no-op) -> else body -> SYNC(no-op) ->
         * then body too, and the then body's write wins last. Confirmed by
         * direct hex trace of test_ifelse (a<b case): mem[2] held the THEN
         * body's result even though the ELSE body ran first.
         *
         * The added unconditional BRnzp is always taken uniformly by
         * whichever group currently holds active_mask (nzp_mask=ALL always
         * matches, since nzp_stored is never 3'b000), so taken_mask ==
         * active_mask and divergence_detected never fires for it -- it does
         * not disturb the real-divergence taken-group-first/warp-stack
         * mechanism (traced against scheduler.sv DIVERGE/SYNC_POP timing;
         * test_simt_relu's genuine per-thread divergence is unaffected).
         *
         * For no-else: else body is empty, S1=B1=2, two adjacent branches
         * before the first SYNC.
         */
        case STMT_IF: {
            const Expr *cond = s->if_stmt.cond;
            int lreg = eval_expr(g, cond->binop.left);
            int rreg = eval_expr(g, cond->binop.right);
            emit_cmp(g->buf, lreg, rreg);

            int nzp       = nzp_for_op(cond->binop.op);
            int brnzp_idx = g->buf->count;
            emit_brnzp(g->buf, nzp, 0, 0);   /* placeholder */

            /* else (not-taken) body */
            int else_start = g->buf->count;
            emit_stmtlist(g, s->if_stmt.else_body);
            int len_else = g->buf->count - else_start;

            /* unconditional skip over the then body, for the not-taken path */
            int skip_idx = g->buf->count;
            emit_brnzp(g->buf, NZP_ALL, 0, 0);   /* placeholder */

            /* NOP, not SYNC: this is only a branch-target landing pad for
             * the taken group, who stay active straight through the then
             * body. A real SYNC here would pop the warp stack before the
             * then body has run -- there's exactly one push per divergence
             * (warp_stack.sv), so the taken group must reach the *second*
             * SYNC (true reconvergence) before any pop happens. Two SYNCs
             * per if (one per landing pad) pops twice against one push;
             * the second pop hits an empty stack and defaults active_mask
             * to all-threads before the then body executes, and the
             * per-thread PCs (now genuinely different addresses) get
             * silently hijacked onto whichever thread core.sv's active_pc
             * mux happens to pick. Found via test_ifdiverge: with real
             * cross-thread divergence (never exercised before -- every
             * prior if/ifelse test used blockDim=1 or uniform conditions),
             * the then body's writes were dropped for every thread but the
             * one the mux happened to select. */
            emit_nop(g->buf);

            /* then (taken) body */
            int then_start = g->buf->count;
            emit_stmtlist(g, s->if_stmt.then_body);
            int len_then = g->buf->count - then_start;

            emit_sync(g->buf);   /* second SYNC */

            /* backpatch: cond branch targets the first SYNC (lands, falls into then body) */
            int off1 = 2 + len_else;
            patch_brnzp(g->buf, brnzp_idx, nzp, off1, off1);

            /* backpatch: unconditional skip targets the second SYNC */
            int off2 = 2 + len_then;
            patch_brnzp(g->buf, skip_idx, NZP_ALL, off2, off2);
            break;
        }

        /* for (int var = init; var < bound; var++) { body }
         *
         * Layout:
         *   [init var]
         *   CONST R_one, 1              <── dedicated increment register
         *   PC_top:
         *   [eval bound → bound_reg]
         *   CMP var_reg, bound_reg
         *   BRnzp ZP, S_exit, B_exit    <── exit if var >= bound; backpatch
         *   [body]
         *   ADD var_reg, var_reg, R_one  <── var++
         *   BRnzp ALL, S_back, B_back   <── unconditional back; backpatch
         *   PC_end:
         *
         * Hardware branch semantics (pc.sv): pc_out <= pc_out + branch_offset,
         * i.e. target = <address of the BRnzp instruction itself> + offset.
         * (NOT target = address_of_BRnzp + 1 + offset -- that was the bug.)
         * So offset = target_pc - brnzp_pc, with no extra +1/-1 fudge.
         */
        case STMT_FOR: {
            int var_reg = syms_lookup(g->syms, s->for_stmt.var);

            /* initialise loop variable */
            int init_reg = eval_expr(g, s->for_stmt.init);
            emit_mov(g->buf, var_reg, init_reg);

            /* constant 1 in dedicated register R28 for var++ */
            emit_const(g->buf, SEMA_TMP_ONE, 1);

            int pc_top = g->buf->count;

            /* CMP var, bound */
            reset_tmp(g);
            int bound_reg = eval_expr(g, s->for_stmt.bound);
            emit_cmp(g->buf, var_reg, bound_reg);

            /* BRnzp ZP → exit when var >= bound */
            int brnzp_exit = g->buf->count;
            emit_brnzp(g->buf, NZP_ZP, 0, 0);   /* placeholder */

            /* body */
            emit_stmtlist(g, s->for_stmt.body);

            /* var++ */
            emit_add(g->buf, var_reg, var_reg, SEMA_TMP_ONE);

            /* unconditional back-edge */
            int brnzp_back = g->buf->count;
            emit_brnzp(g->buf, NZP_ALL, 0, 0);   /* placeholder */

            int pc_end = g->buf->count;

            /* backpatch exit branch: target = pc_end (first instr after loop) */
            int exit_off = pc_end - brnzp_exit;
            patch_brnzp(g->buf, brnzp_exit, NZP_ZP, exit_off, exit_off);

            /* backpatch back-edge: target = pc_top (re-eval bound + CMP) */
            int back_off = pc_top - brnzp_back;   /* negative */
            patch_brnzp(g->buf, brnzp_back, NZP_ALL, back_off, back_off);
            break;
        }

        case STMT_RETURN:
            emit_ret(g->buf);
            break;

        /* mmio_matmul(a_base, b_base, c_base, M, N, K, scale);
         *
         * Uses fixed temps: R20=ctrl_base, R21=value, R22=done_poll.
         * Emits the same sequence as phase21_accel_matmul.c.
         */
        case STMT_MMIO_MATMUL: {
            int R_BASE  = SEMA_TMP_BASE;      /* R20: 0x1F0 ctrl base    */
            int R_VAL   = SEMA_TMP_BASE + 1;  /* R21: value to write     */
            int R_DONE  = SEMA_TMP_BASE + 2;  /* R22: poll DONE register */

            emit_const(g->buf, R_BASE, 0x1F0);

            /* write A_BASE, B_BASE, C_BASE, M, N, K, SCALE */
            const Expr *args[7] = {
                s->mmio.a_base, s->mmio.b_base, s->mmio.c_base,
                s->mmio.M, s->mmio.N, s->mmio.K, s->mmio.scale
            };
            for (int i = 0; i < 7; i++) {
                reset_tmp(g); g->next_tmp = SEMA_TMP_BASE + 3; /* avoid R20/R21/R22 */
                int vreg = eval_expr(g, args[i]);
                emit_mov(g->buf, R_VAL, vreg);
                emit_str(g->buf, R_VAL, R_BASE, i);
            }

            /* START = 1 */
            emit_const(g->buf, R_VAL, 1);
            emit_str  (g->buf, R_VAL, R_BASE, 7);

            /* Poll DONE:
             *   PC_poll: LDR R_DONE, R0, 0x1F8
             *            CMP R_DONE, R0
             *            BRnzp Z, off, off      (loop back to PC_poll if DONE==0)
             *
             * Same PC-relative semantics as STMT_FOR above: target = pc_poll,
             * offset = pc_poll - brnzp_poll. No +1/-1 fudge -- pc.sv adds the
             * offset to the branch instruction's own pc_out directly.
             */
            int pc_poll = g->buf->count;
            emit_ldr   (g->buf, R_DONE, R0, 0x1F8);
            emit_cmp   (g->buf, R_DONE, R0);
            int brnzp_poll = g->buf->count;
            emit_brnzp (g->buf, NZP_Z, 0, 0);
            int off = pc_poll - brnzp_poll;
            patch_brnzp(g->buf, brnzp_poll, NZP_Z, off, off);
            break;
        }

        default:
            cg_err(g, s->line, s->col, "unsupported statement kind");
    }
}

static void emit_stmtlist(CGen *g, const StmtList *list) {
    for (const StmtList *n = list; n && !g->had_error; n = n->next)
        emit_stmt(g, n->stmt);
}

/* ── Entry point ──────────────────────────────────────────────────────────── */
int codegen(const Program *prog, const SemaResult *sema, InstrBuf *out) {
    if (prog->kernel_count == 0) {
        fprintf(stderr, "codegen: no kernels\n");
        return 1;
    }
    /* For now, compile only the first kernel. */
    ibuf_init(out);

    CGen g;
    g.buf       = out;
    g.syms      = &sema->kernels[0];
    g.filename  = prog->filename;
    g.had_error = 0;
    g.next_tmp  = SEMA_TMP_BASE;

    emit_stmtlist(&g, prog->kernels[0].body);

    /* Ensure the kernel ends with RET (guard against missing return). */
    if (!g.had_error && out->count > 0) {
        uint32_t last = out->instructions[out->count - 1];
        if ((last >> 26) != 0x12)   /* 0x12 = RET opcode */
            emit_ret(out);
    }

    return g.had_error ? 1 : 0;
}