#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "lexer.h"
#include "ast.h"
#include "parser.h"
#include "sema.h"
#include "codegen.h"
#include "emit.h"
#include "writer.h"

static void usage(const char *argv0) {
    fprintf(stderr,
        "Usage: %s [options] <input.axelc>\n"
        "Options:\n"
        "  --tokens       dump token stream and exit\n"
        "  --ast          dump AST and exit\n"
        "  -o <base>      output base path (default: input stem)\n",
        argv0);
    exit(1);
}

static char *read_file(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) { perror(path); return NULL; }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    rewind(f);
    char *buf = malloc(sz + 1);
    if (!buf) { fclose(f); return NULL; }
    if (fread(buf, 1, sz, f) != (size_t)sz) {
        fclose(f); free(buf); return NULL;
    }
    buf[sz] = '\0';
    fclose(f);
    return buf;
}

static void stem(const char *path, char *out, int outlen) {
    const char *base = strrchr(path, '/');
    base = base ? base + 1 : path;
    int len = (int)strlen(base);
    const char *dot = strrchr(base, '.');
    if (dot) len = (int)(dot - base);
    if (len >= outlen) len = outlen - 1;
    memcpy(out, base, len);
    out[len] = '\0';
}

int main(int argc, char **argv) {
    const char *infile      = NULL;
    const char *outbase_arg = NULL;
    int         dump_tokens = 0;
    int         dump_ast    = 0;

    for (int i = 1; i < argc; i++) {
        if      (strcmp(argv[i], "--tokens") == 0) dump_tokens = 1;
        else if (strcmp(argv[i], "--ast")    == 0) dump_ast    = 1;
        else if (strcmp(argv[i], "-o")       == 0) {
            if (++i >= argc) usage(argv[0]);
            outbase_arg = argv[i];
        }
        else if (argv[i][0] == '-') {
            fprintf(stderr, "axelcc: unknown option '%s'\n", argv[i]);
            usage(argv[0]);
        }
        else infile = argv[i];
    }

    if (!infile) usage(argv[0]);

    char *src = read_file(infile);
    if (!src) return 1;

    Lexer lex;
    lexer_init(&lex, src, infile);

    // ── --tokens mode ─────────────────────────────────────────────────────────
    if (dump_tokens) {
        printf("%-6s %-4s  %-16s  %s\n", "LINE", "COL", "TYPE", "VALUE");
        printf("%-6s %-4s  %-16s  %s\n", "----", "---", "----", "-----");
        Token t;
        while ((t = lexer_next(&lex)).type != TOK_EOF && t.type != TOK_ERROR) {
            if      (t.type == TOK_INT_LIT) printf("%-6d %-4d  %-16s  %d\n", t.line, t.col, tok_name(t.type), t.ival);
            else if (t.type == TOK_IDENT)   printf("%-6d %-4d  %-16s  %s\n", t.line, t.col, tok_name(t.type), t.text);
            else                            printf("%-6d %-4d  %s\n",         t.line, t.col, tok_name(t.type));
            if (t.text) free(t.text);
        }
        free(src);
        return 0;
    }

    // ── Parse ─────────────────────────────────────────────────────────────────
    Program *prog = parse(&lex);
    if (!prog) { free(src); return 1; }

    // ── --ast mode ────────────────────────────────────────────────────────────
    if (dump_ast) {
        ast_print_program(prog);
        ast_free_program(prog);
        free(src);
        return 0;
    }

    // ── Sema ──────────────────────────────────────────────────────────────────
    SemaResult *sema = sema_check(prog);
    if (!sema) {
        ast_free_program(prog);
        free(src);
        return 1;
    }

    // ── Codegen ───────────────────────────────────────────────────────────────
    InstrBuf ibuf;
    if (codegen(prog, sema, &ibuf) != 0) {
        sema_free(sema);
        ast_free_program(prog);
        free(src);
        return 1;
    }

    // ── Write output ──────────────────────────────────────────────────────────
    char default_outbase[256];
    const char *outbase = outbase_arg;
    if (!outbase) {
        stem(infile, default_outbase, sizeof default_outbase);
        outbase = default_outbase;
    }

    if (writer_write(&ibuf, outbase) != 0) {
        sema_free(sema);
        ast_free_program(prog);
        free(src);
        return 1;
    }

    fprintf(stderr, "axelcc: %d instructions -> %s.hex + %s.axelbin\n",
            ibuf.count, outbase, outbase);

    sema_free(sema);
    ast_free_program(prog);
    free(src);
    return 0;
}