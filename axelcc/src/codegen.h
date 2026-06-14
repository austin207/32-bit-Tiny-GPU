#ifndef CODEGEN_H
#define CODEGEN_H
#include "ast.h"
#include "emit.h"
#include "sema.h"

// Compile all kernels in prog into a single InstrBuf.
// Returns 0 on success, non-zero on error.
int codegen(const Program *prog, const SemaResult *sema, InstrBuf *out);

#endif