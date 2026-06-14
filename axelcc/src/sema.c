#define _POSIX_C_SOURCE 200809L
#include "sema.h"
#include "lexer.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int syms_lookup(const KernelSyms *k, const char *name) {
    for (int i = 0; i < k->var_count; i++)
        if (strcmp(k->vars[i].name, name) == 0)
            return k->vars[i].reg;
    return -1;
}

static int syms_add(KernelSyms *k, const char *name, int line, int col) {
    if (syms_lookup(k, name) >= 0) {
        fprintf(stderr, "%s:%d:%d: sema: variable '%s' already declared\n",
                k->filename, line, col, name);
        return -1;
    }
    if (k->next_reg > SEMA_MAX_VARS) {
        fprintf(stderr, "%s:%d:%d: sema: too many variables (max %d)\n",
                k->filename, line, col, SEMA_MAX_VARS);
        return -1;
    }
    k->vars[k->var_count].name = strdup(name);
    k->vars[k->var_count].reg  = k->next_reg;
    k->var_count++;
    return k->next_reg++;
}

/* ── expression checker: verify all identifiers are declared ─────────────── */
static int check_expr(KernelSyms *k, const Expr *e) {
    if (!e) return 0;
    switch (e->kind) {
        case EXPR_IDENT:
            if (syms_lookup(k, e->name) < 0) {
                fprintf(stderr, "%s:%d:%d: sema: undefined variable '%s'\n",
                        k->filename, e->line, e->col, e->name);
                return 1;
            }
            return 0;
        case EXPR_INT_LIT: case EXPR_THREAD_IDX:
        case EXPR_BLOCK_IDX: case EXPR_BLOCK_DIM:
            return 0;
        case EXPR_BINOP:
            return check_expr(k, e->binop.left) | check_expr(k, e->binop.right);
        case EXPR_UNOP:
            return check_expr(k, e->unop.operand);
        case EXPR_MEM_LOAD:
            return check_expr(k, e->mem_load.addr);
        case EXPR_FMA:
            return check_expr(k, e->fma.a) | check_expr(k, e->fma.b)
                 | check_expr(k, e->fma.c);
        case EXPR_DOT4:
            return check_expr(k, e->dot4.a) | check_expr(k, e->dot4.b);
        case EXPR_EXP8:  return check_expr(k, e->exp8.x);
        case EXPR_RELU:  return check_expr(k, e->relu.x);
        default: return 0;
    }
}

/* Validate that an if-condition is a comparison expression. */
static int check_if_cond(KernelSyms *k, const Expr *cond) {
    if (!cond || cond->kind != EXPR_BINOP) {
        fprintf(stderr, "%s:%d:%d: sema: if condition must be a comparison (e.g. val > 0)\n",
                k->filename, cond ? cond->line : 0, cond ? cond->col : 0);
        return 1;
    }
    switch (cond->binop.op) {
        case TOK_LT: case TOK_GT: case TOK_LEQ:
        case TOK_GEQ: case TOK_EQ: case TOK_NEQ:
            return check_expr(k, cond->binop.left) | check_expr(k, cond->binop.right);
        default:
            fprintf(stderr, "%s:%d:%d: sema: if condition must use a comparison operator\n",
                    k->filename, cond->line, cond->col);
            return 1;
    }
}

static int check_stmtlist(KernelSyms *k, const StmtList *list, int if_depth);

static int check_stmt(KernelSyms *k, const Stmt *s, int if_depth) {
    switch (s->kind) {
        case STMT_VAR_DECL:
            if (check_expr(k, s->var_decl.init)) return 1;
            return syms_add(k, s->var_decl.name, s->line, s->col) < 0;

        case STMT_ASSIGN: {
            int r = syms_lookup(k, s->assign.name);
            if (r < 0) {
                fprintf(stderr, "%s:%d:%d: sema: assignment to undeclared variable '%s'\n",
                        k->filename, s->line, s->col, s->assign.name);
                return 1;
            }
            return check_expr(k, s->assign.val);
        }
        case STMT_MEM_STORE:
            return check_expr(k, s->mem_store.addr) | check_expr(k, s->mem_store.val);

        case STMT_IF:
            if (if_depth >= 1) {
                fprintf(stderr, "%s:%d:%d: sema: nested if not supported\n",
                        k->filename, s->line, s->col);
                return 1;
            }
            if (check_if_cond(k, s->if_stmt.cond)) return 1;
            if (check_stmtlist(k, s->if_stmt.then_body, if_depth + 1)) return 1;
            if (check_stmtlist(k, s->if_stmt.else_body, if_depth + 1)) return 1;
            return 0;

        case STMT_FOR:
            if (check_expr(k, s->for_stmt.init))  return 1;
            if (check_expr(k, s->for_stmt.bound)) return 1;
            /* add loop variable to scope */
            if (syms_add(k, s->for_stmt.var, s->line, s->col) < 0) return 1;
            return check_stmtlist(k, s->for_stmt.body, if_depth);

        case STMT_RETURN:
            return 0;

        case STMT_MMIO_MATMUL:
            return check_expr(k, s->mmio.a_base) | check_expr(k, s->mmio.b_base)
                 | check_expr(k, s->mmio.c_base) | check_expr(k, s->mmio.M)
                 | check_expr(k, s->mmio.N)      | check_expr(k, s->mmio.K)
                 | check_expr(k, s->mmio.scale);

        default: return 0;
    }
}

static int check_stmtlist(KernelSyms *k, const StmtList *list, int if_depth) {
    int err = 0;
    for (const StmtList *n = list; n; n = n->next)
        err |= check_stmt(k, n->stmt, if_depth);
    return err;
}

SemaResult *sema_check(Program *prog) {
    SemaResult *res = calloc(1, sizeof *res);
    res->count   = prog->kernel_count;
    res->kernels = calloc(prog->kernel_count, sizeof *res->kernels);

    int err = 0;
    for (int ki = 0; ki < prog->kernel_count; ki++) {
        const Kernel *kern = &prog->kernels[ki];
        KernelSyms   *k    = &res->kernels[ki];
        k->next_reg  = 1;
        k->filename  = prog->filename;

        /* register kernel parameters first */
        for (int pi = 0; pi < kern->param_count; pi++) {
            if (syms_add(k, kern->params[pi].name, kern->line, kern->col) < 0)
                err = 1;
        }
        err |= check_stmtlist(k, kern->body, 0);
    }

    if (err) { sema_free(res); return NULL; }
    return res;
}

void sema_free(SemaResult *res) {
    if (!res) return;
    for (int i = 0; i < res->count; i++) {
        KernelSyms *k = &res->kernels[i];
        for (int j = 0; j < k->var_count; j++)
            free(k->vars[j].name);
    }
    free(res->kernels);
    free(res);
}