# SIMT Design Notes

## Scheduler FSM — Current States
000 IDLE
001 FETCH
010 DECODE
011 REQUEST
100 WAIT
101 EXECUTE
110 UPDATE

## Scheduler FSM — New SIMT States
111 DIVERGE
    - entry: EXECUTE state, branch_en=1, divergence=1
    - action: stack_push=1, active_mask <= taken_mask
    - next: FETCH

1000 SYNC_POP  
    - entry: DECODE state, sync_en=1, stack not empty
    - action: stack_pop=1, active_mask <= saved_mask from stack top
    - next: FETCH

1001 RECONVERGE
    - entry: SYNC_POP when stack empty after pop
    - action: active_mask <= ALL_ONES
    - next: FETCH

## New Signals

### Scheduler inputs (new)
- branch_en           [1]   already decoded, needs routing
- nzp_results         [T]   per-thread NZP from each ALU
- sync_en             [1]   new opcode 0x15 decoded
- stack_empty         [1]   from warp_stack
- saved_mask          [T]   from warp_stack top

### Scheduler outputs (new)
- active_mask         [T]   registered, gates w_en per thread
- stack_push          [1]   single-cycle pulse
- stack_pop           [1]   single-cycle pulse
- taken_mask          [T]   threads where branch was taken

## Divergence Detection (in core.sv)
wire [T-1:0] thread_branch_taken;
// each thread: (nzp_result[i] & nzp_mask) != 0
wire divergence = branch_en & (|taken) & (|(~taken));
// passes to scheduler

## Warp Stack Interface
push:  sync_pc_in[31:0], not_taken_mask[T-1:0]
pop:   sync_pc_out[31:0], saved_mask_out[T-1:0]
depth: 4 entries (handles 4 levels of nesting)

## ISA Change — BRnzp encoding revised
[31:26] opcode  = 0x0E
[25:23] nzp_mask
[22:12] branch_offset  (11 bits, was 23)
[11:0]  sync_offset    (12 bits, NEW — PC-relative addr of SYNC)

## New opcodes
0x15  SYNC  — reconvergence point, no operands (N-format)
