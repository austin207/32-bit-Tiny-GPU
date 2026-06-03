"""
axelbin.py — loader for .axelbin kernel binaries

.axelbin header layout (32 bytes, all fields little-endian):
  Offset  Size  Field
   0      4     magic        b'AXLB'
   4      1     version      0x01
   5      1     flags        0x00 (reserved)
   6      2     reserved     0x0000
   8      4     num_blocks
  12      4     blockDim     (threads_per_block)
  16      4     text_words   (instruction count)
  20      4     data_words   (initial data memory word count, 0 if none)
  24      4     entry_point  (PC start, always 0 for now)
  28      4     reserved     0x00000000

Text segment: text_words × uint32_t (32-bit instructions)
Data segment: data_words × uint32_t (initial data memory, signed 32-bit values)

Usage in cocotb testbench:
    from axelbin import load_axelbin
    kernel = load_axelbin("builds/phase6_simt_relu.axelbin")

    # Drive DCR
    dut.dcr_data.value = kernel['num_blocks']   # write num_blocks
    dut.dcr_data.value = kernel['blockDim']     # write blockDim

    # Load prog_mem
    for i, instr in enumerate(kernel['instructions']):
        prog_mem[i] = instr

    # Load data_mem
    for i, word in enumerate(kernel['data_mem']):
        data_mem[i] = word & 0xFFFFFFFF          # stored as unsigned in hardware
"""

import struct
import os

AXLB_MAGIC   = b'AXLB'
AXLB_HEADER  = 32          # bytes
AXLB_VERSION = 0x01


class AxelbinError(Exception):
    pass


def load_axelbin(path):
    """
    Load a .axelbin file and return a dict with all fields.

    Returns:
        {
            'version':      int,
            'num_blocks':   int,
            'blockDim':     int,
            'entry_point':  int,
            'instructions': list[int],   # unsigned 32-bit words
            'data_mem':     list[int],   # signed 32-bit values (for display)
            'data_mem_raw': list[int],   # unsigned 32-bit values (for hardware)
        }

    Raises:
        AxelbinError  if the file is missing, too short, or has wrong magic/version
        FileNotFoundError  if the file does not exist
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"axelbin: file not found: {path}")

    with open(path, 'rb') as f:
        raw = f.read()

    if len(raw) < AXLB_HEADER:
        raise AxelbinError(
            f"axelbin: file too short ({len(raw)} bytes, need at least {AXLB_HEADER}): {path}"
        )

    # Verify magic
    if raw[:4] != AXLB_MAGIC:
        raise AxelbinError(
            f"axelbin: bad magic {raw[:4]!r}, expected {AXLB_MAGIC!r}: {path}"
        )

    # Verify version
    version = raw[4]
    if version != AXLB_VERSION:
        raise AxelbinError(
            f"axelbin: unsupported version {version:#04x}, expected {AXLB_VERSION:#04x}: {path}"
        )

    # Parse header fields
    num_blocks   = struct.unpack_from('<I', raw,  8)[0]
    blockDim     = struct.unpack_from('<I', raw, 12)[0]
    text_words   = struct.unpack_from('<I', raw, 16)[0]
    data_words   = struct.unpack_from('<I', raw, 20)[0]
    entry_point  = struct.unpack_from('<I', raw, 24)[0]

    # Validate segment sizes against file length
    expected_size = AXLB_HEADER + text_words * 4 + data_words * 4
    if len(raw) < expected_size:
        raise AxelbinError(
            f"axelbin: file truncated (got {len(raw)} bytes, expected {expected_size}): {path}"
        )

    # Text segment — unsigned 32-bit instructions
    text_off     = AXLB_HEADER
    instructions = list(struct.unpack_from(f'<{text_words}I', raw, text_off))

    # Data segment — raw unsigned for hardware, signed for human display
    data_off     = text_off + text_words * 4
    data_mem_raw = list(struct.unpack_from(f'<{data_words}I', raw, data_off)) if data_words else []
    data_mem     = [v if v < 0x80000000 else v - 0x100000000 for v in data_mem_raw]

    return {
        'version':      version,
        'num_blocks':   num_blocks,
        'blockDim':     blockDim,
        'entry_point':  entry_point,
        'text_words':   text_words,
        'data_words':   data_words,
        'instructions': instructions,
        'data_mem':     data_mem,       # signed — use for printing/debug
        'data_mem_raw': data_mem_raw,   # unsigned — use for hardware assignment
    }


def dump_axelbin(path):
    """
    Human-readable dump of an .axelbin file.
    Useful for debugging: python3 -c "from axelbin import dump_axelbin; dump_axelbin('x.axelbin')"
    """
    k = load_axelbin(path)
    print(f"axelbin: {path}")
    print(f"  version     : {k['version']:#04x}")
    print(f"  num_blocks  : {k['num_blocks']}")
    print(f"  blockDim    : {k['blockDim']}")
    print(f"  entry_point : {k['entry_point']:#010x}")
    print(f"  text_words  : {k['text_words']}")
    print(f"  data_words  : {k['data_words']}")
    print()
    print("  Text segment:")
    for i, instr in enumerate(k['instructions']):
        print(f"    [{i:3d}]  {instr:08X}")
    if k['data_mem']:
        print()
        print("  Data segment:")
        for i, (raw, signed) in enumerate(zip(k['data_mem_raw'], k['data_mem'])):
            print(f"    [{i:3d}]  {raw:08X}  ({signed})")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 axelbin.py <file.axelbin>")
        sys.exit(1)
    dump_axelbin(sys.argv[1])