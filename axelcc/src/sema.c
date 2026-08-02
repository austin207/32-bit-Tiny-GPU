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
    if (k->next_reg > k->max_reg) {
        fprintf(stderr, "%s:%d:%d: sema: too many variables (max %d)\n",
                k->filename, line, col, k->max_reg - k->next_reg + k->var_count + 1);
        return -1;
    }
    k->vars[k->var_count].name = strdup(name);
    k->vars[k->var_count].reg  = k->next_reg;
    k->var_count++;
    return k->next_reg++;
}

/* Find a declared func by name, or NULL. */
static const Func *find_func(const KernelSyms *k, const char *name) {
    for (int i = 0; i < k->func_count; i++)
        if (strcmp(k->funcs[i].name, name) == 0) return &k->funcs[i];
    return NULL;
}

/* Does this expression tree contain a call anywhere? (func bodies may not
 * call other funcs -- see the register-window rationale in sema.h.) */
static int expr_has_call(const Expr *e) {
    if (!e) return 0;
    switch (e->kind) {
        case EXPR_CALL: return 1;
        case EXPR_BINOP: return expr_has_call(e->binop.left) || expr_has_call(e->binop.right);
        case EXPR_UNOP:  return expr_has_call(e->unop.operand);
        case EXPR_MEM_LOAD: return expr_has_call(e->mem_load.addr);
        case EXPR_FMA:  return expr_has_call(e->fma.a) || expr_has_call(e->fma.b) || expr_has_call(e->fma.c);
        case EXPR_DOT4: return expr_has_call(e->dot4.a) || expr_has_call(e->dot4.b);
        case EXPR_EXP8:  return expr_has_call(e->exp8.x);
        case EXPR_RELU:  return expr_has_call(e->relu.x);
        case EXPR_CLAMP: return expr_has_call(e->clamp.x);
        default: return 0;
    }
}
static int stmtlist_has_call(const StmtList *list);
static int stmt_has_call(const Stmt *s) {
    switch (s->kind) {
        case STMT_VAR_DECL: return expr_has_call(s->var_decl.init);
        case STMT_ASSIGN:   return expr_has_call(s->assign.val);
        case STMT_MEM_STORE: return expr_has_call(s->mem_store.addr) || expr_has_call(s->mem_store.val);
        case STMT_IF:
            return expr_has_call(s->if_stmt.cond)
                 || stmtlist_has_call(s->if_stmt.then_body)
                 || stmtlist_has_call(s->if_stmt.else_body);
        case STMT_FOR:
            return expr_has_call(s->for_stmt.init) || expr_has_call(s->for_stmt.bound)
                 || stmtlist_has_call(s->for_stmt.body);
        case STMT_RETURN: return expr_has_call(s->ret.val);
        default: return 0;
    }
}
static int stmtlist_has_call(const StmtList *list) {
    for (const StmtList *n = list; n; n = n->next)
        if (stmt_has_call(n->stmt)) return 1;
    return 0;
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
        case EXPR_CLAMP: return check_expr(k, e->clamp.x);
        case EXPR_CALL: {
            const Func *f = find_func(k, e->call.name);
            if (!f) {
                fprintf(stderr, "%s:%d:%d: sema: call to undeclared func '%s'\n",
                        k->filename, e->line, e->col, e->call.name);
                return 1;
            }
            if (e->call.arg_count != f->param_count) {
                fprintf(stderr,
                        "%s:%d:%d: sema: '%s' expects %d argument(s), got %d\n",
                        k->filename, e->line, e->col, e->call.name,
                        f->param_count, e->call.arg_count);
                return 1;
            }
            int err = 0;
            for (int i = 0; i < e->call.arg_count; i++)
                err |= check_expr(k, e->call.args[i]);
            return err;
        }
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
            return s->ret.val ? check_expr(k, s->ret.val) : 0;

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

/* Walk a statement list to its last node (NULL if empty). */
static const StmtList *stmtlist_last(const StmtList *list) {
    if (!list) return NULL;
    while (list->next) list = list->next;
    return list;
}

SemaResult *sema_check(Program *prog) {
    SemaResult *res = calloc(1, sizeof *res);
    res->count      = prog->kernel_count;
    res->kernels    = calloc(prog->kernel_count, sizeof *res->kernels);
    res->func_count = prog->func_count;
    res->funcs      = calloc(prog->func_count, sizeof *res->funcs);

    int err = 0;

    /* Funcs first: each gets its own register window (R14..R18 for
     * params/locals, R19 for the return value -- see sema.h), and two
     * checks with no equivalent for kernels: the body must not itself
     * contain a call (no nesting -- every func shares the same physical
     * register window, so two calls can never be "in flight" at once),
     * and the body must end with `return expr;` (codegen relies on the
     * last statement being the SRET-with-value point). */
    for (int fi = 0; fi < prog->func_count; fi++) {
        const Func *fn = &prog->funcs[fi];
        KernelSyms *k  = &res->funcs[fi];
        k->next_reg    = SEMA_FUNC_REG_BASE;
        k->max_reg     = SEMA_FUNC_REG_BASE + SEMA_FUNC_MAX_VARS - 1;
        k->filename    = prog->filename;
        k->funcs       = prog->funcs;
        k->func_count  = prog->func_count;

        for (int pi = 0; pi < fn->param_count; pi++) {
            if (syms_add(k, fn->params[pi].name, fn->line, fn->col) < 0)
                err = 1;
        }
        err |= check_stmtlist(k, fn->body, 0);

        if (stmtlist_has_call(fn->body)) {
            fprintf(stderr,
                    "%s:%d:%d: sema: func '%s' body may not call another func "
                    "(no nested calls -- every func shares the same register window)\n",
                    prog->filename, fn->line, fn->col, fn->name);
            err = 1;
        }

        const StmtList *last = stmtlist_last(fn->body);
        if (!last || last->stmt->kind != STMT_RETURN || !last->stmt->ret.val) {
            fprintf(stderr,
                    "%s:%d:%d: sema: func '%s' must end with 'return expr;'\n",
                    prog->filename, fn->line, fn->col, fn->name);
            err = 1;
        }
    }

    int kernel_max_reg = prog->func_count > 0
        ? SEMA_KERNEL_MAX_VARS_WITH_FUNCS : SEMA_MAX_VARS;

    for (int ki = 0; ki < prog->kernel_count; ki++) {
        const Kernel *kern = &prog->kernels[ki];
        KernelSyms   *k    = &res->kernels[ki];
        k->next_reg  = 1;
        k->max_reg   = kernel_max_reg;
        k->filename  = prog->filename;
        k->funcs     = prog->funcs;
        k->func_count = prog->func_count;

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
    for (int i = 0; i < res->func_count; i++) {
        KernelSyms *k = &res->funcs[i];
        for (int j = 0; j < k->var_count; j++)
            free(k->vars[j].name);
    }
    free(res->funcs);
    free(res);
}