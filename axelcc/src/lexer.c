#include "lexer.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// ── Internal helpers ──────────────────────────────────────────────────────────

static char cur(const Lexer *lex)  { return lex->src[lex->pos]; }
static char nxt(const Lexer *lex)  { return lex->src[lex->pos + 1]; }

static char advance(Lexer *lex) {
    char c = lex->src[lex->pos++];
    if (c == '\n') { lex->line++; lex->col = 1; }
    else           { lex->col++; }
    return c;
}

static void skip_whitespace_and_comments(Lexer *lex) {
    for (;;) {
        // skip blanks
        while (cur(lex) != '\0' && isspace((unsigned char)cur(lex)))
            advance(lex);
        // skip // line comments
        if (cur(lex) == '/' && nxt(lex) == '/') {
            while (cur(lex) != '\0' && cur(lex) != '\n')
                advance(lex);
            continue;
        }
        break;
    }
}

static Token make(TokenType type, int line, int col) {
    Token t;
    t.type = type;
    t.text = NULL;
    t.ival = 0;
    t.line = line;
    t.col  = col;
    return t;
}

// ── Keyword table ─────────────────────────────────────────────────────────────

typedef struct { const char *kw; TokenType tok; } KWEntry;

static const KWEntry KEYWORDS[] = {
    {"kernel",      TOK_KERNEL},
    {"func",        TOK_FUNC},
    {"void",        TOK_VOID},
    {"int",         TOK_INT},
    {"return",      TOK_RETURN},
    {"if",          TOK_IF},
    {"else",        TOK_ELSE},
    {"for",         TOK_FOR},
    {"mem",         TOK_MEM},
    {"fma",         TOK_FMA},
    {"dot4",        TOK_DOT4},
    {"exp8",        TOK_EXP8},
    {"relu",        TOK_RELU},
    {"clamp",       TOK_CLAMP},
    {"mmio_matmul", TOK_MMIO_MATMUL},
    {"threadIdx",   TOK_THREAD_IDX},
    {"blockIdx",    TOK_BLOCK_IDX},
    {"blockDim",    TOK_BLOCK_DIM},
    {NULL,          TOK_ERROR}
};

static Token lex_ident_or_keyword(Lexer *lex, int line, int col) {
    int start = lex->pos - 1;   // we already consumed one char
    while (isalnum((unsigned char)cur(lex)) || cur(lex) == '_')
        advance(lex);
    int len = lex->pos - start;

    // check keyword table first
    for (int i = 0; KEYWORDS[i].kw; i++) {
        if ((int)strlen(KEYWORDS[i].kw) == len &&
            memcmp(lex->src + start, KEYWORDS[i].kw, len) == 0)
        {
            return make(KEYWORDS[i].tok, line, col);
        }
    }

    // user identifier
    Token t = make(TOK_IDENT, line, col);
    t.text  = malloc(len + 1);
    memcpy(t.text, lex->src + start, len);
    t.text[len] = '\0';
    return t;
}

static Token lex_int_lit(Lexer *lex, int line, int col) {
    int start = lex->pos - 1;
    while (isdigit((unsigned char)cur(lex)))
        advance(lex);
    int len = lex->pos - start;
    // safe parse; max int fits in 32 chars
    char buf[40];
    if (len >= 40) len = 39;
    memcpy(buf, lex->src + start, len);
    buf[len] = '\0';
    Token t = make(TOK_INT_LIT, line, col);
    t.ival  = atoi(buf);
    return t;
}

// ── Public API ────────────────────────────────────────────────────────────────

void lexer_init(Lexer *lex, const char *src, const char *filename) {
    lex->src      = src;
    lex->pos      = 0;
    lex->line     = 1;
    lex->col      = 1;
    lex->filename = filename;
}

Token lexer_next(Lexer *lex) {
    skip_whitespace_and_comments(lex);

    int  line = lex->line;
    int  col  = lex->col;
    char c    = advance(lex);

    if (c == '\0') return make(TOK_EOF, line, col);

    if (isalpha((unsigned char)c) || c == '_')
        return lex_ident_or_keyword(lex, line, col);
    if (isdigit((unsigned char)c))
        return lex_int_lit(lex, line, col);

    switch (c) {
        case '+': return make(TOK_PLUS,      line, col);
        case '-': return make(TOK_MINUS,     line, col);
        case '*': return make(TOK_STAR,      line, col);
        case '/': return make(TOK_SLASH,     line, col);
        case '%': return make(TOK_PERCENT,   line, col);
        case '~': return make(TOK_TILDE,     line, col);
        case '^': return make(TOK_CARET,     line, col);
        case '|': return make(TOK_PIPE,      line, col);
        case '(': return make(TOK_LPAREN,    line, col);
        case ')': return make(TOK_RPAREN,    line, col);
        case '{': return make(TOK_LBRACE,    line, col);
        case '}': return make(TOK_RBRACE,    line, col);
        case '[': return make(TOK_LBRACKET,  line, col);
        case ']': return make(TOK_RBRACKET,  line, col);
        case ';': return make(TOK_SEMICOLON, line, col);
        case ',': return make(TOK_COMMA,     line, col);

        case '>':
            if (cur(lex) == '>') { advance(lex); return make(TOK_SHR, line, col); }
            if (cur(lex) == '=') { advance(lex); return make(TOK_GEQ, line, col); }
            return make(TOK_GT, line, col);

        case '<':
            if (cur(lex) == '<') { advance(lex); return make(TOK_SHL, line, col); }
            if (cur(lex) == '=') { advance(lex); return make(TOK_LEQ, line, col); }
            return make(TOK_LT, line, col);

        case '=':
            if (cur(lex) == '=') { advance(lex); return make(TOK_EQ, line, col); }
            return make(TOK_ASSIGN, line, col);

        case '!':
            if (cur(lex) == '=') { advance(lex); return make(TOK_NEQ, line, col); }
            return make(TOK_BANG, line, col);

        case '&':
            return make(TOK_AMP, line, col);

        default:
            fprintf(stderr, "%s:%d:%d: error: unexpected character '%c' (0x%02x)\n",
                    lex->filename, line, col, isprint(c) ? c : '?', (unsigned char)c);
            return make(TOK_ERROR, line, col);
    }
}

// Peek: save/restore position; free any ident text (caller only needs type).
TokenType lexer_peek_type(Lexer *lex) {
    int saved_pos  = lex->pos;
    int saved_line = lex->line;
    int saved_col  = lex->col;

    Token t = lexer_next(lex);
    if (t.text) free(t.text);

    lex->pos  = saved_pos;
    lex->line = saved_line;
    lex->col  = saved_col;
    return t.type;
}

const char *tok_name(TokenType t) {
    switch (t) {
        case TOK_INT_LIT:    return "INT_LIT";
        case TOK_IDENT:      return "IDENT";
        case TOK_KERNEL:     return "kernel";
        case TOK_FUNC:       return "func";
        case TOK_VOID:       return "void";
        case TOK_INT:        return "int";
        case TOK_RETURN:     return "return";
        case TOK_IF:         return "if";
        case TOK_ELSE:       return "else";
        case TOK_FOR:        return "for";
        case TOK_MEM:        return "mem";
        case TOK_FMA:        return "fma";
        case TOK_DOT4:       return "dot4";
        case TOK_EXP8:       return "exp8";
        case TOK_RELU:       return "relu";
        case TOK_CLAMP:      return "clamp";
        case TOK_MMIO_MATMUL:return "mmio_matmul";
        case TOK_THREAD_IDX: return "threadIdx";
        case TOK_BLOCK_IDX:  return "blockIdx";
        case TOK_BLOCK_DIM:  return "blockDim";
        case TOK_PLUS:       return "+";
        case TOK_MINUS:      return "-";
        case TOK_STAR:       return "*";
        case TOK_SLASH:      return "/";
        case TOK_PERCENT:    return "%";
        case TOK_SHR:        return ">>";
        case TOK_SHL:        return "<<";
        case TOK_AMP:        return "&";
        case TOK_PIPE:       return "|";
        case TOK_CARET:      return "^";
        case TOK_TILDE:      return "~";
        case TOK_BANG:       return "!";
        case TOK_EQ:         return "==";
        case TOK_NEQ:        return "!=";
        case TOK_LT:         return "<";
        case TOK_GT:         return ">";
        case TOK_LEQ:        return "<=";
        case TOK_GEQ:        return ">=";
        case TOK_ASSIGN:     return "=";
        case TOK_LPAREN:     return "(";
        case TOK_RPAREN:     return ")";
        case TOK_LBRACE:     return "{";
        case TOK_RBRACE:     return "}";
        case TOK_LBRACKET:   return "[";
        case TOK_RBRACKET:   return "]";
        case TOK_SEMICOLON:  return ";";
        case TOK_COMMA:      return ",";
        case TOK_EOF:        return "EOF";
        case TOK_ERROR:      return "ERROR";
        default:             return "?";
    }
}