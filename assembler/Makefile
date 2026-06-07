# assembler/Makefile
CC     = gcc
CFLAGS = -Wall -Iinclude
SRCS   = src/axel.c src/gpu_asm.c
BUILD  = builds
HEX    = builds/hex
BIN    = builds/bin

.PHONY: all clean test_add test_axel phase1 phase2 phase3 phase4 phase5 phase6 phase7 phase8 phase9_single phase9_broadcast phase10 phase11 phase12 phase13 phase14

all: phase1 phase2 phase3 phase4 phase5 phase6 phase7 phase8 phase9_single phase9_broadcast phase10 phase11 phase12 phase13 phase14

$(BUILD):
	mkdir -p $(BUILD)
	mkdir -p $(HEX)
	mkdir -p $(BIN)

test_add: $(BUILD)
	$(CC) $(CFLAGS) examples/test_add.c $(SRCS) -o $(BUILD)/test_add
	cd $(BUILD) && ./test_add

test_axel: $(BUILD)
	$(CC) $(CFLAGS) examples/test_axel.c $(SRCS) -o $(BUILD)/test_axel
	cd $(BUILD) && ./test_axel

phase1: $(BUILD)
	$(CC) $(CFLAGS) examples/phase1_ldr_test.c $(SRCS) -o $(BUILD)/phase1
	cd $(BUILD) && ./phase1

phase2: $(BUILD)
	$(CC) $(CFLAGS) examples/phase2_matmul.c $(SRCS) -o $(BUILD)/phase2
	cd $(BUILD) && ./phase2

phase3: $(BUILD)
	$(CC) $(CFLAGS) examples/phase3_relu.c $(SRCS) -o $(BUILD)/phase3
	cd $(BUILD) && ./phase3

phase4: $(BUILD)
	$(CC) $(CFLAGS) examples/phase4_forward.c $(SRCS) -o $(BUILD)/phase4
	cd $(BUILD) && ./phase4

phase5: $(BUILD)
	$(CC) $(CFLAGS) examples/phase5_weight_update.c $(SRCS) -o $(BUILD)/phase5
	cd $(BUILD) && ./phase5

phase6: $(BUILD)
	$(CC) $(CFLAGS) examples/phase6_simt_relu.c $(SRCS) -o $(BUILD)/phase6
	cd $(BUILD) && ./phase6

phase7: $(BUILD)
	$(CC) $(CFLAGS) examples/phase7_dot4_test.c $(SRCS) -o $(BUILD)/phase7
	cd $(BUILD) && ./phase7

phase8: $(BUILD)
	$(CC) $(CFLAGS) examples/phase8_mlp_inference.c $(SRCS) -o $(BUILD)/phase8
	cd $(BUILD) && ./phase8

phase9_single: $(BUILD)
	$(CC) $(CFLAGS) examples/phase9_ldr_regbase_single.c $(SRCS) -o $(BUILD)/phase9_single
	cd $(BUILD) && ./phase9_single

phase9_broadcast: $(BUILD)
	$(CC) $(CFLAGS) examples/phase9_ldr_regbase_broadcast.c $(SRCS) -o $(BUILD)/phase9_broadcast
	cd $(BUILD) && ./phase9_broadcast

phase10: $(BUILD)
	$(CC) $(CFLAGS) examples/phase10_mlp_8out.c $(SRCS) -o $(BUILD)/phase10
	cd $(BUILD) && ./phase10

phase11: $(BUILD)
	$(CC) $(CFLAGS) examples/phase11_mlp_8in.c $(SRCS) -o $(BUILD)/phase11
	cd $(BUILD) && ./phase11

phase12: $(BUILD)
	$(CC) $(CFLAGS) examples/phase12_mlp_q6.c $(SRCS) -o $(BUILD)/phase12
	cd $(BUILD) && ./phase12

phase13: $(BUILD)
	$(CC) $(CFLAGS) examples/phase13_digit_hidden.c $(SRCS) -o $(BUILD)/phase13
	cd $(BUILD) && ./phase13

phase14: $(BUILD)
	$(CC) $(CFLAGS) examples/phase14_digit_output.c $(SRCS) -o $(BUILD)/phase14
	cd $(BUILD) && ./phase14

clean:
	rm -rf $(BUILD)
