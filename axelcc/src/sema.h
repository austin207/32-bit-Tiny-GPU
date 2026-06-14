#ifndef SEMA_H
#define SEMA_H
#include "ast.h"

#define SEMA_MAX_VARS   19   // R1..R19 user variables
#define SEMA_TMP_BASE   20   // R20..R28 compiler temporaries
#define SEMA_TMP_ONE    28   // R28 = dedicated "constant 1" for loop increment

typedef struct { char *name; int reg; } VarBinding;

typedef struct {
    VarBinding vars[SEMA_MAX_VARS + 10];
    int        var_count;
    int        next_reg;     // next user register to assign (starts at 1)
    const char *filename;
} KernelSyms;

typedef struct {
    KernelSyms *kernels;    // one per prog->kernels[i]
    int         count;
} SemaResult;

SemaResult *sema_check (Program *prog);
void        sema_free  (SemaResult *res);
int         syms_lookup(const KernelSyms *k, const char *name); // reg or -1

#endif