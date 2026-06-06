# assembler/Makefile
CC     = gcc
CFLAGS = -Wall -Iinclude
SRCS   = src/axel.c src/gpu_asm.c
BUILD  = builds
HEX    = builds/hex
BIN    = builds/bin

.PHONY: all clean test_add test_axel phase1 phase2 phase3 phase4 phase5 phase6 phase7 phase8

all: phase1 phase2 phase3 phase4 phase5 phase6 phase7 phase8

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

clean:
	rm -rf $(BUILD)
