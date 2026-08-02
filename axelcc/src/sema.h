#ifndef SEMA_H
#define SEMA_H
#include "ast.h"

#define SEMA_MAX_VARS       19   // R1..R19 kernel-level user variables (no funcs declared)
#define SEMA_TMP_BASE       20   // R20..R28 compiler temporaries (shared by kernels and funcs --
                                  // safe since only one call is ever "in flight", see sema.c)
#define SEMA_TMP_ONE        28   // R28 = dedicated "constant 1" for loop increment

// Subroutine (func) register convention: every func shares the SAME fixed
// window R14..R19 for its params/locals/return value (only one CALL is ever
// active at a time -- funcs cannot call other funcs, so there's no nesting
// to alias). When a program declares any funcs, kernel-level code gives up
// R14..R19 for its own variables (capped at R1..R13 instead of R1..R19) so
// a CALL can never clobber a live kernel variable.
#define SEMA_FUNC_REG_BASE  14   // R14 = first func param/local register
#define SEMA_FUNC_MAX_VARS  5    // R14..R18 = up to 5 params+locals per func
#define SEMA_FUNC_REG_RET   19   // R19 = dedicated return-value register
#define SEMA_KERNEL_MAX_VARS_WITH_FUNCS (SEMA_FUNC_REG_BASE - 1)  // R1..R13

typedef struct { char *name; int reg; } VarBinding;

typedef struct {
    VarBinding vars[SEMA_MAX_VARS + 10];
    int        var_count;
    int        next_reg;     // next user register to assign (starts at 1, or SEMA_FUNC_REG_BASE for funcs)
    int        max_reg;      // highest register next_reg may reach (inclusive upper bound check)
    const char *filename;
    const Func *funcs;       // program's func table, for resolving EXPR_CALL (not owned)
    int         func_count;
} KernelSyms;

typedef struct {
    KernelSyms *kernels;    // one per prog->kernels[i]
    int         count;
    KernelSyms *funcs;      // one per prog->funcs[i]
    int         func_count;
} SemaResult;

SemaResult *sema_check (Program *prog);
void        sema_free  (SemaResult *res);
int         syms_lookup(const KernelSyms *k, const char *name); // reg or -1

#endif