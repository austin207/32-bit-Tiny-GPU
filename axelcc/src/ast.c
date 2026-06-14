#define _POSIX_C_SOURCE 200809L
#include "ast.h"
#include "lexer.h"   // tok_name for op names

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// ── Expressions ───────────────────────────────────────────────────────────────

static Expr *new_expr(ExprKind kind, int line, int col) {
    Expr *e = calloc(1, sizeof *e);
    e->kind = kind;
    e->line = line;
    e->col  = col;
    return e;
}

Expr *ast_int_lit(int val, int line, int col) {
    Expr *e = new_expr(EXPR_INT_LIT, line, col);
    e->ival = val;
    return e;
}

Expr *ast_ident(const char *name, int line, int col) {
    Expr *e = new_expr(EXPR_IDENT, line, col);
    e->name = strdup(name);
    return e;
}

Expr *ast_binop(int op, Expr *l, Expr *r, int line, int col) {
    Expr *e = new_expr(EXPR_BINOP, line, col);
    e->binop.op    = op;
    e->binop.left  = l;
    e->binop.right = r;
    return e;
}

Expr *ast_unop(int op, Expr *operand, int line, int col) {
    Expr *e = new_expr(EXPR_UNOP, line, col);
    e->unop.op      = op;
    e->unop.operand = operand;
    return e;
}

Expr *ast_mem_load(Expr *addr, int line, int col) {
    Expr *e = new_expr(EXPR_MEM_LOAD, line, col);
    e->mem_load.addr = addr;
    return e;
}

Expr *ast_fma(Expr *a, Expr *b, Expr *c, int line, int col) {
    Expr *e = new_expr(EXPR_FMA, line, col);
    e->fma.a = a; e->fma.b = b; e->fma.c = c;
    return e;
}

Expr *ast_dot4(Expr *a, Expr *b, int line, int col) {
    Expr *e = new_expr(EXPR_DOT4, line, col);
    e->dot4.a = a; e->dot4.b = b;
    return e;
}

Expr *ast_exp8(Expr *x, int line, int col) {
    Expr *e = new_expr(EXPR_EXP8, line, col);
    e->exp8.x = x;
    return e;
}

// ── Statements ────────────────────────────────────────────────────────────────

static Stmt *new_stmt(StmtKind kind, int line, int col) {
    Stmt *s = calloc(1, sizeof *s);
    s->kind = kind;
    s->line = line;
    s->col  = col;
    return s;
}

Stmt *ast_var_decl(const char *name, Expr *init, int line, int col) {
    Stmt *s = new_stmt(STMT_VAR_DECL, line, col);
    s->var_decl.name = strdup(name);
    s->var_decl.init = init;
    return s;
}

Stmt *ast_assign(const char *name, Expr *val, int line, int col) {
    Stmt *s = new_stmt(STMT_ASSIGN, line, col);
    s->assign.name = strdup(name);
    s->assign.val  = val;
    return s;
}

Stmt *ast_mem_store(Expr *addr, Expr *val, int line, int col) {
    Stmt *s = new_stmt(STMT_MEM_STORE, line, col);
    s->mem_store.addr = addr;
    s->mem_store.val  = val;
    return s;
}

Stmt *ast_if(Expr *cond, StmtList *then_body, StmtList *else_body,
             int line, int col)
{
    Stmt *s = new_stmt(STMT_IF, line, col);
    s->if_stmt.cond      = cond;
    s->if_stmt.then_body = then_body;
    s->if_stmt.else_body = else_body;
    return s;
}

Stmt *ast_for(const char *var, Expr *init, Expr *bound,
              StmtList *body, int line, int col)
{
    Stmt *s = new_stmt(STMT_FOR, line, col);
    s->for_stmt.var   = strdup(var);
    s->for_stmt.init  = init;
    s->for_stmt.bound = bound;
    s->for_stmt.body  = body;
    return s;
}

Stmt *ast_return(int line, int col) {
    return new_stmt(STMT_RETURN, line, col);
}

Stmt *ast_mmio(Expr *a, Expr *b, Expr *c,
               Expr *M, Expr *N, Expr *K, Expr *scale,
               int line, int col)
{
    Stmt *s = new_stmt(STMT_MMIO_MATMUL, line, col);
    s->mmio.a_base = a; s->mmio.b_base = b; s->mmio.c_base = c;
    s->mmio.M = M; s->mmio.N = N; s->mmio.K = K; s->mmio.scale = scale;
    return s;
}

// ── StmtList ──────────────────────────────────────────────────────────────────

StmtList *ast_stmtlist_append(StmtList *list, Stmt *stmt) {
    StmtList *node = calloc(1, sizeof *node);
    node->stmt = stmt;
    node->next = NULL;
    if (!list) return node;
    // walk to tail
    StmtList *tail = list;
    while (tail->next) tail = tail->next;
    tail->next = node;
    return list;
}

// ── Free ─────────────────────────────────────────────────────────────────────

static void free_expr(Expr *e) {
    if (!e) return;
    switch (e->kind) {
        case EXPR_IDENT:    free(e->name); break;
        case EXPR_BINOP:    free_expr(e->binop.left); free_expr(e->binop.right); break;
        case EXPR_UNOP:     free_expr(e->unop.operand); break;
        case EXPR_MEM_LOAD: free_expr(e->mem_load.addr); break;
        case EXPR_FMA:      free_expr(e->fma.a); free_expr(e->fma.b); free_expr(e->fma.c); break;
        case EXPR_DOT4:     free_expr(e->dot4.a); free_expr(e->dot4.b); break;
        case EXPR_EXP8:     free_expr(e->exp8.x); break;
        case EXPR_RELU:     free_expr(e->relu.x); break;
        default: break;
    }
    free(e);
}

static void free_stmtlist(StmtList *list);

static void free_stmt(Stmt *s) {
    if (!s) return;
    switch (s->kind) {
        case STMT_VAR_DECL:   free(s->var_decl.name); free_expr(s->var_decl.init); break;
        case STMT_ASSIGN:     free(s->assign.name);   free_expr(s->assign.val);   break;
        case STMT_MEM_STORE:  free_expr(s->mem_store.addr); free_expr(s->mem_store.val); break;
        case STMT_IF:
            free_expr(s->if_stmt.cond);
            free_stmtlist(s->if_stmt.then_body);
            free_stmtlist(s->if_stmt.else_body);
            break;
        case STMT_FOR:
            free(s->for_stmt.var);
            free_expr(s->for_stmt.init);
            free_expr(s->for_stmt.bound);
            free_stmtlist(s->for_stmt.body);
            break;
        case STMT_MMIO_MATMUL:
            free_expr(s->mmio.a_base); free_expr(s->mmio.b_base);
            free_expr(s->mmio.c_base);
            free_expr(s->mmio.M); free_expr(s->mmio.N);
            free_expr(s->mmio.K); free_expr(s->mmio.scale);
            break;
        default: break;
    }
    free(s);
}

static void free_stmtlist(StmtList *list) {
    while (list) {
        StmtList *next = list->next;
        free_stmt(list->stmt);
        free(list);
        list = next;
    }
}

void ast_free_program(Program *prog) {
    if (!prog) return;
    for (int i = 0; i < prog->kernel_count; i++) {
        Kernel *k = &prog->kernels[i];
        free(k->name);
        for (int j = 0; j < k->param_count; j++)
            free(k->params[j].name);
        free(k->params);
        free_stmtlist(k->body);
    }
    free(prog->kernels);
    free(prog->filename);
    free(prog);
}

// ── Debug printer ─────────────────────────────────────────────────────────────

static void print_indent(int depth) {
    for (int i = 0; i < depth * 2; i++) putchar(' ');
}

static void print_expr(const Expr *e, int depth) {
    print_indent(depth);
    if (!e) { printf("(null)\n"); return; }
    switch (e->kind) {
        case EXPR_INT_LIT:   printf("INT(%d)\n", e->ival); break;
        case EXPR_IDENT:     printf("IDENT(%s)\n", e->name); break;
        case EXPR_THREAD_IDX:printf("threadIdx\n"); break;
        case EXPR_BLOCK_IDX: printf("blockIdx\n"); break;
        case EXPR_BLOCK_DIM: printf("blockDim\n"); break;
        case EXPR_BINOP:
            printf("BINOP(%s)\n", tok_name((TokenType)e->binop.op));
            print_expr(e->binop.left,  depth + 1);
            print_expr(e->binop.right, depth + 1);
            break;
        case EXPR_UNOP:
            printf("UNOP(%s)\n", tok_name((TokenType)e->unop.op));
            print_expr(e->unop.operand, depth + 1);
            break;
        case EXPR_MEM_LOAD:
            printf("MEM_LOAD\n");
            print_expr(e->mem_load.addr, depth + 1);
            break;
        case EXPR_FMA:
            printf("FMA\n");
            print_expr(e->fma.a, depth + 1);
            print_expr(e->fma.b, depth + 1);
            print_expr(e->fma.c, depth + 1);
            break;
        case EXPR_DOT4:
            printf("DOT4\n");
            print_expr(e->dot4.a, depth + 1);
            print_expr(e->dot4.b, depth + 1);
            break;
        case EXPR_EXP8:
            printf("EXP8\n");
            print_expr(e->exp8.x, depth + 1);
            break;
        case EXPR_RELU:
            printf("RELU\n");
            print_expr(e->relu.x, depth + 1);
            break;
    }
}

static void print_stmtlist(const StmtList *list, int depth);

static void print_stmt(const Stmt *s, int depth) {
    print_indent(depth);
    if (!s) { printf("(null stmt)\n"); return; }
    switch (s->kind) {
        case STMT_VAR_DECL:
            printf("VAR_DECL %s =\n", s->var_decl.name);
            print_expr(s->var_decl.init, depth + 1);
            break;
        case STMT_ASSIGN:
            printf("ASSIGN %s =\n", s->assign.name);
            print_expr(s->assign.val, depth + 1);
            break;
        case STMT_MEM_STORE:
            printf("MEM_STORE\n");
            print_indent(depth + 1); printf("addr:\n");
            print_expr(s->mem_store.addr, depth + 2);
            print_indent(depth + 1); printf("val:\n");
            print_expr(s->mem_store.val, depth + 2);
            break;
        case STMT_IF:
            printf("IF\n");
            print_indent(depth + 1); printf("cond:\n");
            print_expr(s->if_stmt.cond, depth + 2);
            print_indent(depth + 1); printf("then:\n");
            print_stmtlist(s->if_stmt.then_body, depth + 2);
            if (s->if_stmt.else_body) {
                print_indent(depth + 1); printf("else:\n");
                print_stmtlist(s->if_stmt.else_body, depth + 2);
            }
            break;
        case STMT_FOR:
            printf("FOR %s\n", s->for_stmt.var);
            print_indent(depth + 1); printf("init:\n");
            print_expr(s->for_stmt.init, depth + 2);
            print_indent(depth + 1); printf("bound:\n");
            print_expr(s->for_stmt.bound, depth + 2);
            print_indent(depth + 1); printf("body:\n");
            print_stmtlist(s->for_stmt.body, depth + 2);
            break;
        case STMT_RETURN:
            printf("RETURN\n");
            break;
        case STMT_MMIO_MATMUL:
            printf("MMIO_MATMUL\n");
            break;
    }
}

static void print_stmtlist(const StmtList *list, int depth) {
    for (const StmtList *n = list; n; n = n->next)
        print_stmt(n->stmt, depth);
}

void ast_print_program(const Program *prog) {
    printf("Program: %s\n", prog->filename ? prog->filename : "<unknown>");
    for (int i = 0; i < prog->kernel_count; i++) {
        const Kernel *k = &prog->kernels[i];
        printf("  kernel %s(", k->name);
        for (int j = 0; j < k->param_count; j++) {
            if (j) printf(", ");
            printf("int %s", k->params[j].name);
        }
        printf(") {\n");
        print_stmtlist(k->body, 2);
        printf("  }\n");
    }
}