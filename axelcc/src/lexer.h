#ifndef LEXER_H
#define LEXER_H

// ── Token types ───────────────────────────────────────────────────────────────
typedef enum {
    // Literals / names
    TOK_INT_LIT,        // 42
    TOK_IDENT,          // foo

    // Keywords
    TOK_KERNEL,         // kernel
    TOK_VOID,           // void
    TOK_INT,            // int
    TOK_RETURN,         // return
    TOK_IF,             // if
    TOK_ELSE,           // else
    TOK_FOR,            // for

    // Built-in intrinsics (keywords, not library calls)
    TOK_MEM,            // mem
    TOK_FMA,            // fma
    TOK_DOT4,           // dot4
    TOK_EXP8,           // exp8
    TOK_RELU,           // relu
    TOK_MMIO_MATMUL,    // mmio_matmul

    // GPU built-in read-only vars
    TOK_THREAD_IDX,     // threadIdx
    TOK_BLOCK_IDX,      // blockIdx
    TOK_BLOCK_DIM,      // blockDim

    // Arithmetic operators
    TOK_PLUS,           // +
    TOK_MINUS,          // -
    TOK_STAR,           // *
    TOK_SLASH,          // /
    TOK_PERCENT,        // %
    TOK_SHR,            // >>
    TOK_SHL,            // <<

    // Bitwise operators
    TOK_AMP,            // &
    TOK_PIPE,           // |
    TOK_CARET,          // ^
    TOK_TILDE,          // ~
    TOK_BANG,           // !

    // Comparison operators
    TOK_EQ,             // ==
    TOK_NEQ,            // !=
    TOK_LT,             // <
    TOK_GT,             // >
    TOK_LEQ,            // <=
    TOK_GEQ,            // >=

    // Assignment
    TOK_ASSIGN,         // =

    // Delimiters
    TOK_LPAREN,         // (
    TOK_RPAREN,         // )
    TOK_LBRACE,         // {
    TOK_RBRACE,         // }
    TOK_LBRACKET,       // [
    TOK_RBRACKET,       // ]
    TOK_SEMICOLON,      // ;
    TOK_COMMA,          // ,

    TOK_EOF,
    TOK_ERROR,
} TokenType;

// ── Token ─────────────────────────────────────────────────────────────────────
typedef struct {
    TokenType   type;
    char       *text;   // heap-allocated for TOK_IDENT; NULL otherwise
    int         ival;   // parsed value for TOK_INT_LIT
    int         line;
    int         col;
} Token;

// ── Lexer state ───────────────────────────────────────────────────────────────
typedef struct {
    const char *src;        // full source, null-terminated
    int         pos;        // current byte index into src
    int         line;       // 1-based
    int         col;        // 1-based
    const char *filename;   // for error messages
} Lexer;

// ── API ───────────────────────────────────────────────────────────────────────

// Initialise lexer over null-terminated source string.
void      lexer_init     (Lexer *lex, const char *src, const char *filename);

// Consume and return the next token.
// Caller must free tok.text when tok.type == TOK_IDENT.
Token     lexer_next     (Lexer *lex);

// Peek at the next token type without consuming it.
// Does NOT allocate; use lexer_next when you need the ident text.
TokenType lexer_peek_type(Lexer *lex);

// Human-readable name for a token type (static string, do not free).
const char *tok_name(TokenType t);

#endif // LEXER_H