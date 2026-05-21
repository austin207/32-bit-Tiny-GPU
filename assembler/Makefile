# assembler/Makefile
CC     = gcc
CFLAGS = -Wall -Iinclude
SRCS   = src/axel.c src/gpu_asm.c
BUILD  = builds

EXAMPLES = test_add test_axel

.PHONY: all clean $(EXAMPLES)

all: $(EXAMPLES)

$(BUILD):
	mkdir -p $(BUILD)

# Compile each example binary into builds/, then run it FROM there
# so any hex output (relative paths) lands in builds/ automatically
test_add: $(BUILD)
	$(CC) $(CFLAGS) examples/test_add.c $(SRCS) -o $(BUILD)/test_add
	cd $(BUILD) && ./test_add

test_axel: $(BUILD)
	$(CC) $(CFLAGS) examples/test_axel.c $(SRCS) -o $(BUILD)/test_axel
	cd $(BUILD) && ./test_axel

clean:
	rm -rf $(BUILD)