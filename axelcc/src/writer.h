#ifndef WRITER_H
#define WRITER_H
#include "emit.h"

// Write outbase.hex (one 8-digit hex word per line).
// Write outbase.axelbin (simple binary format readable by axelbin.py).
// Returns 0 on success.
int writer_write(const InstrBuf *buf, const char *outbase);

#endif