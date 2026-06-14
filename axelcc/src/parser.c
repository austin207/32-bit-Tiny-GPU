#define _POSIX_C_SOURCE 200809L
#include "parser.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    Lexer      *lex;
    Token       cur;
    int         had_error;
    const char *filename;
} Parser;

static void parser_init(Parser *p, Lexer *lex) {
    p->lex = lex; p->had_error = 0;
    p->filename = lex->filename;
    p->cur = lexer_next(lex);
}

static void error_tok(Parser *p, const char *msg) {
    fprintf(stderr, "%s:%d:%d: error: %s\n",
            p->filename, p->cur.line, p->cur.col, msg);
    p->had_error = 1;
}

static void error_expected(Parser *p, const char *what) {
    char buf[256];
    snprintf(buf, sizeof buf, "expected %s, got '%s'", what, tok_name(p->cur.type));
    error_tok(p, buf);
}

static Token adv(Parser *p) {
    Token prev = p->cur;
    if (prev.type != TOK_EOF) p->cur = lexer_next(p->lex);
    return prev;
}

static int check(const Parser *p, TokenType t) { return p->cur.type == t; }

static int expect(Parser *p, TokenType t) {
    if (check(p, t)) { free(p->cur.text); p->cur = lexer_next(p->lex); return 1; }
    error_expected(p, tok_name(t));
    return 0;
}

static char *eat_ident(Parser *p) {
    if (!check(p, TOK_IDENT)) { error_expected(p, "identifier"); return NULL; }
    char *name = p->cur.text; p->cur.text = NULL;
    p->cur = lexer_next(p->lex);
    return name;
}

/* ── forward decls ──────────────────────────────────────────────────────────── */
static Expr     *parse_expr    (Parser *p);
static StmtList *parse_stmtlist(Parser *p);
static Stmt     *parse_stmt    (Parser *p);

/* ── expressions ────────────────────────────────────────────────────────────── */
static Expr *parse_add  (Parser *p);
static Expr *parse_mul  (Parser *p);
static Expr *parse_unary(Parser *p);
static Expr *parse_primary(Parser *p);

static Expr *parse_expr(Parser *p) {
    Expr *left = parse_add(p);
    if (!left) return NULL;
    int op;
    switch (p->cur.type) {
        case TOK_LT:  case TOK_GT:  case TOK_LEQ:
        case TOK_GEQ: case TOK_EQ:  case TOK_NEQ:
            op = p->cur.type; break;
        default: return left;
    }
    int line = p->cur.line, col = p->cur.col; adv(p);
    Expr *right = parse_add(p);
    if (!right) return NULL;
    return ast_binop(op, left, right, line, col);
}

static Expr *parse_add(Parser *p) {
    Expr *left = parse_mul(p); if (!left) return NULL;
    while (check(p, TOK_PLUS) || check(p, TOK_MINUS)) {
        int op = p->cur.type, line = p->cur.line, col = p->cur.col; adv(p);
        Expr *right = parse_mul(p); if (!right) return NULL;
        left = ast_binop(op, left, right, line, col);
    }
    return left;
}

static Expr *parse_mul(Parser *p) {
    Expr *left = parse_unary(p); if (!left) return NULL;
    for (;;) {
        int op;
        switch (p->cur.type) {
            case TOK_STAR: case TOK_SLASH: case TOK_PERCENT:
            case TOK_SHR:  case TOK_SHL:
            case TOK_AMP:  case TOK_PIPE:  case TOK_CARET:
                op = p->cur.type; break;
            default: return left;
        }
        int line = p->cur.line, col = p->cur.col; adv(p);
        Expr *right = parse_unary(p); if (!right) return NULL;
        left = ast_binop(op, left, right, line, col);
    }
}

static Expr *parse_unary(Parser *p) {
    if (check(p, TOK_MINUS) || check(p, TOK_TILDE)) {
        int op = p->cur.type, line = p->cur.line, col = p->cur.col; adv(p);
        Expr *operand = parse_unary(p); if (!operand) return NULL;
        return ast_unop(op, operand, line, col);
    }
    return parse_primary(p);
}

static Expr **parse_args(Parser *p, int n) {
    if (!expect(p, TOK_LPAREN)) return NULL;
    Expr **a = malloc(n * sizeof *a);
    for (int i = 0; i < n; i++) {
        a[i] = parse_expr(p);
        if (!a[i]) { free(a); return NULL; }
        if (i < n-1 && !expect(p, TOK_COMMA)) { free(a); return NULL; }
    }
    if (!expect(p, TOK_RPAREN)) { free(a); return NULL; }
    return a;
}

static Expr *parse_primary(Parser *p) {
    int line = p->cur.line, col = p->cur.col;
    switch (p->cur.type) {
        case TOK_INT_LIT: { int v = p->cur.ival; adv(p); return ast_int_lit(v,line,col); }

        case TOK_THREAD_IDX: { adv(p); Expr *e=calloc(1,sizeof*e);
            e->kind=EXPR_THREAD_IDX;e->line=line;e->col=col; return e; }
        case TOK_BLOCK_IDX:  { adv(p); Expr *e=calloc(1,sizeof*e);
            e->kind=EXPR_BLOCK_IDX;e->line=line;e->col=col; return e; }
        case TOK_BLOCK_DIM:  { adv(p); Expr *e=calloc(1,sizeof*e);
            e->kind=EXPR_BLOCK_DIM;e->line=line;e->col=col; return e; }

        case TOK_MEM: {
            adv(p);
            if (!expect(p, TOK_LBRACKET)) return NULL;
            Expr *addr = parse_expr(p); if (!addr) return NULL;
            if (!expect(p, TOK_RBRACKET)) return NULL;
            return ast_mem_load(addr, line, col);
        }
        case TOK_FMA: { adv(p);
            Expr **a=parse_args(p,3); if (!a) return NULL;
            Expr *e=ast_fma(a[0],a[1],a[2],line,col); free(a); return e; }
        case TOK_DOT4: { adv(p);
            Expr **a=parse_args(p,2); if (!a) return NULL;
            Expr *e=ast_dot4(a[0],a[1],line,col); free(a); return e; }
        case TOK_EXP8: { adv(p);
            Expr **a=parse_args(p,1); if (!a) return NULL;
            Expr *e=ast_exp8(a[0],line,col); free(a); return e; }
        case TOK_RELU: { adv(p);
            Expr **a=parse_args(p,1); if (!a) return NULL;
            Expr *e=calloc(1,sizeof*e); e->kind=EXPR_RELU;
            e->line=line;e->col=col; e->relu.x=a[0]; free(a); return e; }

        case TOK_IDENT: {
            char *name=p->cur.text; p->cur.text=NULL; adv(p);
            Expr *e=ast_ident(name,line,col); free(name); return e; }

        case TOK_LPAREN: {
            adv(p); Expr *e=parse_expr(p); if (!e) return NULL;
            if (!expect(p, TOK_RPAREN)) return NULL;
            return e;
        }

        default:
            error_expected(p, "expression"); return NULL;
    }
}

/* ── statements ─────────────────────────────────────────────────────────────── */

static Stmt *parse_if(Parser *p) {
    int line=p->cur.line, col=p->cur.col; adv(p);
    if (!expect(p,TOK_LPAREN)) return NULL;
    Expr *cond=parse_expr(p); if (!cond) return NULL;
    if (!expect(p,TOK_RPAREN)) return NULL;
    if (!expect(p,TOK_LBRACE)) return NULL;
    StmtList *then_body=parse_stmtlist(p);
    if (p->had_error) return NULL;
    if (!expect(p,TOK_RBRACE)) return NULL;
    StmtList *else_body=NULL;
    if (check(p,TOK_ELSE)) {
        adv(p);
        if (!expect(p,TOK_LBRACE)) return NULL;
        else_body=parse_stmtlist(p);
        if (p->had_error) return NULL;
        if (!expect(p,TOK_RBRACE)) return NULL;
    }
    return ast_if(cond,then_body,else_body,line,col);
}

static Stmt *parse_for(Parser *p) {
    int line=p->cur.line, col=p->cur.col; adv(p);
    if (!expect(p,TOK_LPAREN)) return NULL;
    if (!expect(p,TOK_INT))    return NULL;
    char *var=eat_ident(p); if (!var) return NULL;
    if (!expect(p,TOK_ASSIGN)) { free(var); return NULL; }
    Expr *init=parse_expr(p); if (!init) { free(var); return NULL; }
    if (!expect(p,TOK_SEMICOLON)) { free(var); return NULL; }
    /* condition: IDENT < expr */
    if (!check(p,TOK_IDENT)||strcmp(p->cur.text,var)) {
        error_tok(p,"for: condition must use loop variable");
        free(var); return NULL;
    }
    adv(p);
    if (!expect(p,TOK_LT)) { free(var); return NULL; }
    Expr *bound=parse_expr(p); if (!bound) { free(var); return NULL; }
    if (!expect(p,TOK_SEMICOLON)) { free(var); return NULL; }
    /* increment: IDENT ++ */
    if (!check(p,TOK_IDENT)||strcmp(p->cur.text,var)) {
        error_tok(p,"for: increment must use loop variable");
        free(var); return NULL;
    }
    adv(p);
    if (!expect(p,TOK_PLUS)) { free(var); return NULL; }
    if (!expect(p,TOK_PLUS)) { free(var); return NULL; }
    if (!expect(p,TOK_RPAREN)) { free(var); return NULL; }
    if (!expect(p,TOK_LBRACE)) { free(var); return NULL; }
    StmtList *body=parse_stmtlist(p);
    if (p->had_error) { free(var); return NULL; }
    if (!expect(p,TOK_RBRACE)) { free(var); return NULL; }
    Stmt *s=ast_for(var,init,bound,body,line,col); free(var); return s;
}

static Stmt *parse_stmt(Parser *p) {
    int line=p->cur.line, col=p->cur.col;
    switch (p->cur.type) {
        case TOK_INT: {
            adv(p); char *name=eat_ident(p); if (!name) return NULL;
            if (!expect(p,TOK_ASSIGN)) { free(name); return NULL; }
            Expr *init=parse_expr(p); if (!init) { free(name); return NULL; }
            if (!expect(p,TOK_SEMICOLON)) { free(name); return NULL; }
            Stmt *s=ast_var_decl(name,init,line,col); free(name); return s;
        }
        case TOK_MEM: {
            adv(p);
            if (!expect(p,TOK_LBRACKET)) return NULL;
            Expr *addr=parse_expr(p); if (!addr) return NULL;
            if (!expect(p,TOK_RBRACKET)) return NULL;
            if (!expect(p,TOK_ASSIGN)) return NULL;
            Expr *val=parse_expr(p); if (!val) return NULL;
            if (!expect(p,TOK_SEMICOLON)) return NULL;
            return ast_mem_store(addr,val,line,col);
        }
        case TOK_IDENT: {
            char *name=p->cur.text; p->cur.text=NULL; adv(p);
            if (!expect(p,TOK_ASSIGN)) { free(name); return NULL; }
            Expr *val=parse_expr(p); if (!val) { free(name); return NULL; }
            if (!expect(p,TOK_SEMICOLON)) { free(name); return NULL; }
            Stmt *s=ast_assign(name,val,line,col); free(name); return s;
        }
        case TOK_IF:          return parse_if(p);
        case TOK_FOR:         return parse_for(p);
        case TOK_MMIO_MATMUL: {
            int ln=line, cl=col; adv(p);
            Expr **a=parse_args(p,7); if (!a) return NULL;
            if (!expect(p,TOK_SEMICOLON)) { free(a); return NULL; }
            Stmt *s=ast_mmio(a[0],a[1],a[2],a[3],a[4],a[5],a[6],ln,cl);
            free(a); return s;
        }
        case TOK_RETURN:
            adv(p);
            if (!expect(p,TOK_SEMICOLON)) return NULL;
            return ast_return(line,col);
        default:
            error_expected(p,"statement"); adv(p); return NULL;
    }
}

static StmtList *parse_stmtlist(Parser *p) {
    StmtList *list=NULL;
    while (!check(p,TOK_RBRACE) && !check(p,TOK_EOF)) {
        Stmt *s=parse_stmt(p);
        if (!s) {
            while (!check(p,TOK_SEMICOLON)&&!check(p,TOK_RBRACE)&&!check(p,TOK_EOF))
                adv(p);
            if (check(p,TOK_SEMICOLON)) adv(p);
            continue;
        }
        list=ast_stmtlist_append(list,s);
    }
    return list;
}

/* ── kernel + program ────────────────────────────────────────────────────────── */

static Kernel *parse_kernel(Parser *p) {
    int line=p->cur.line, col=p->cur.col;
    if (!expect(p,TOK_KERNEL)) return NULL;
    if (!expect(p,TOK_VOID))   return NULL;
    char *name=eat_ident(p); if (!name) return NULL;
    if (!expect(p,TOK_LPAREN)) { free(name); return NULL; }
    Param *params=NULL; int pc=0;
    while (!check(p,TOK_RPAREN)&&!check(p,TOK_EOF)) {
        if (!expect(p,TOK_INT)) { free(name); free(params); return NULL; }
        char *pn=eat_ident(p);
        if (!pn) { free(name); free(params); return NULL; }
        params=realloc(params,(pc+1)*sizeof*params);
        params[pc++].name=pn;
        if (!check(p,TOK_RPAREN)&&!expect(p,TOK_COMMA)) {
            free(name); free(params); return NULL;
        }
    }
    if (!expect(p,TOK_RPAREN)) { free(name); free(params); return NULL; }
    if (!expect(p,TOK_LBRACE)) { free(name); free(params); return NULL; }
    StmtList *body=parse_stmtlist(p);
    if (!expect(p,TOK_RBRACE)) { free(name); free(params); return NULL; }
    Kernel *k=calloc(1,sizeof*k);
    k->name=name; k->params=params; k->param_count=pc;
    k->body=body; k->line=line; k->col=col;
    return k;
}

Program *parse(Lexer *lex) {
    Parser p; parser_init(&p,lex);
    Program *prog=calloc(1,sizeof*prog);
    prog->filename=lex->filename?strdup(lex->filename):NULL;
    while (!check(&p,TOK_EOF)) {
        if (!check(&p,TOK_KERNEL)) { error_tok(&p,"expected 'kernel'"); break; }
        Kernel *k=parse_kernel(&p);
        if (!k) { p.had_error=1; break; }
        prog->kernels=realloc(prog->kernels,(prog->kernel_count+1)*sizeof*prog->kernels);
        prog->kernels[prog->kernel_count++]=*k;
        free(k);
    }
    if (p.had_error) { ast_free_program(prog); return NULL; }
    return prog;
}