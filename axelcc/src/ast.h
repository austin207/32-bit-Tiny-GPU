#ifndef AST_H
#define AST_H

// ── Expression kinds ──────────────────────────────────────────────────────────
typedef enum {
    EXPR_INT_LIT,       // 42
    EXPR_IDENT,         // foo
    EXPR_THREAD_IDX,    // threadIdx  (read-only)
    EXPR_BLOCK_IDX,     // blockIdx   (read-only)
    EXPR_BLOCK_DIM,     // blockDim   (read-only)
    EXPR_BINOP,         // a + b, a >> n, a < b, ...
    EXPR_UNOP,          // -a, ~a
    EXPR_MEM_LOAD,      // mem[addr]
    EXPR_FMA,           // fma(a, b, c)
    EXPR_DOT4,          // dot4(a, b)
    EXPR_EXP8,          // exp8(x)
    EXPR_RELU,          // relu(x)  — single-value ReLU, no divergence
    EXPR_CLAMP,         // clamp(x) — saturate to int8 range [-128, 127]
    EXPR_CALL,          // name(args...) — call a `func`-declared subroutine
} ExprKind;

typedef struct Expr Expr;
struct Expr {
    ExprKind kind;
    int line, col;
    union {
        // EXPR_INT_LIT
        int ival;

        // EXPR_IDENT
        char *name;

        // EXPR_BINOP
        struct { int op; Expr *left; Expr *right; } binop;

        // EXPR_UNOP
        struct { int op; Expr *operand; } unop;

        // EXPR_MEM_LOAD
        struct { Expr *addr; } mem_load;

        // EXPR_FMA
        struct { Expr *a; Expr *b; Expr *c; } fma;

        // EXPR_DOT4
        struct { Expr *a; Expr *b; } dot4;

        // EXPR_EXP8
        struct { Expr *x; } exp8;

        // EXPR_RELU
        struct { Expr *x; } relu;

        // EXPR_CLAMP
        struct { Expr *x; } clamp;

        // EXPR_CALL: name(args...) — args is a heap array of arg_count Expr*
        struct { char *name; Expr **args; int arg_count; } call;
    };
};

// ── Statement kinds ───────────────────────────────────────────────────────────
typedef enum {
    STMT_VAR_DECL,      // int x = expr;
    STMT_ASSIGN,        // x = expr;
    STMT_MEM_STORE,     // mem[addr] = expr;
    STMT_IF,            // if (cond) { ... } else { ... }
    STMT_FOR,           // for (int i = init; i < bound; i++) { ... }
    STMT_RETURN,        // return; (kernel, no value) or return expr; (func, has value)
    STMT_MMIO_MATMUL,   // mmio_matmul(a_base, b_base, c_base, M, N, K, scale);
} StmtKind;

typedef struct Stmt     Stmt;
typedef struct StmtList StmtList;

// Intrusive linked list of statements (arena-friendly)
struct StmtList {
    Stmt        *stmt;
    StmtList    *next;
};

struct Stmt {
    StmtKind kind;
    int line, col;
    union {
        // STMT_VAR_DECL: int name = init;
        struct { char *name; Expr *init; } var_decl;

        // STMT_ASSIGN: name = val;
        struct { char *name; Expr *val; } assign;

        // STMT_MEM_STORE: mem[addr] = val;
        struct { Expr *addr; Expr *val; } mem_store;

        // STMT_IF: if (cond) { then } else { els }
        // else_body is NULL when no else branch
        // cond must be a EXPR_BINOP with a comparison op
        struct {
            Expr     *cond;
            StmtList *then_body;
            StmtList *else_body;
        } if_stmt;

        // STMT_FOR: for (int var = init; var < bound; var++) { body }
        // Only form supported: single variable, < comparison, ++ increment.
        struct {
            char     *var;
            Expr     *init;
            Expr     *bound;
            StmtList *body;
        } for_stmt;

        // STMT_MMIO_MATMUL: mmio_matmul(a, b, c, M, N, K, scale);
        struct {
            Expr *a_base;
            Expr *b_base;
            Expr *c_base;
            Expr *M, *N, *K;
            Expr *scale;
        } mmio;

        // STMT_RETURN: val is NULL for a kernel's bare `return;`,
        // non-NULL for a func's `return expr;`.
        struct { Expr *val; } ret;
    };
};

// ── Kernel ────────────────────────────────────────────────────────────────────
typedef struct {
    char *name;
} Param;

typedef struct {
    char    *name;          // kernel function name
    Param   *params;        // array of parameters
    int      param_count;
    StmtList *body;
    int      line, col;
} Kernel;

// ── Func (subroutine, callable via CALL/SRET) ───────────────────────────────
// Same shape as Kernel, but: (1) params/locals are register-allocated into a
// small reserved window shared by every func (only one call is ever "in
// flight" at a time — no nesting, see sema.c), not the kernel's normal
// SEMA_MAX_VARS range; (2) the body must end with `return expr;`, not fall
// off the end; (3) a func's body may not itself contain a call expression
// (sema-enforced — see the register-window rationale in sema.c).
typedef struct {
    char     *name;
    Param    *params;
    int       param_count;
    StmtList *body;
    int       line, col;
} Func;

// ── Program ───────────────────────────────────────────────────────────────────
typedef struct {
    Kernel  *kernels;       // array of top-level kernels
    int      kernel_count;
    Func    *funcs;         // array of top-level func (subroutine) declarations
    int      func_count;
    char    *filename;
} Program;

// ── Constructors (in ast.c) ───────────────────────────────────────────────────
Expr     *ast_int_lit    (int val, int line, int col);
Expr     *ast_ident      (const char *name, int line, int col);
Expr     *ast_binop      (int op, Expr *l, Expr *r, int line, int col);
Expr     *ast_unop       (int op, Expr *operand, int line, int col);
Expr     *ast_mem_load   (Expr *addr, int line, int col);
Expr     *ast_fma        (Expr *a, Expr *b, Expr *c, int line, int col);
Expr     *ast_dot4       (Expr *a, Expr *b, int line, int col);
Expr     *ast_exp8       (Expr *x, int line, int col);
Expr     *ast_clamp      (Expr *x, int line, int col);
Expr     *ast_call       (const char *name, Expr **args, int arg_count, int line, int col);

Stmt     *ast_var_decl   (const char *name, Expr *init, int line, int col);
Stmt     *ast_assign     (const char *name, Expr *val, int line, int col);
Stmt     *ast_mem_store  (Expr *addr, Expr *val, int line, int col);
Stmt     *ast_if         (Expr *cond, StmtList *then_body, StmtList *else_body,
                          int line, int col);
Stmt     *ast_for        (const char *var, Expr *init, Expr *bound,
                          StmtList *body, int line, int col);
Stmt     *ast_return     (Expr *val, int line, int col);
Stmt     *ast_mmio       (Expr *a, Expr *b, Expr *c,
                          Expr *M, Expr *N, Expr *K, Expr *scale,
                          int line, int col);

StmtList *ast_stmtlist_append(StmtList *list, Stmt *stmt);

void      ast_free_program(Program *prog);

// Debug printer
void      ast_print_program(const Program *prog);

#endif // AST_H