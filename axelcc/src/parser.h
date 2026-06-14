#ifndef PARSER_H
#define PARSER_H
#include "lexer.h"
#include "ast.h"

// Parse a complete .axelc source into a Program.
// Returns NULL on any error (messages already printed to stderr).
Program *parse(Lexer *lex);

#endif // PARSER_H