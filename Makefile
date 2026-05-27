# Root-level Makefile for running all cocotb RTL tests

TEST_DIRS := \
	Src/alu \
	Src/registers \
	Src/pc \
	Src/decoder \
	Src/fetcher \
	Src/lsu \
	Src/memory_controller \
	Src/scheduler \
	Src/core \
	Src/dispatcher \
	Src/device_control_register \
	Src/Top_level_GPU

.PHONY: test clean

test:
	@set -e; \
	for dir in $(TEST_DIRS); do \
		echo "========================================"; \
		echo "Running test in $$dir"; \
		echo "========================================"; \
		$(MAKE) -C $$dir; \
	done

clean:
	@for dir in $(TEST_DIRS); do \
		echo "Cleaning $$dir"; \
		$(MAKE) -C $$dir clean || true; \
	done
	find . -type d -name sim_build -exec rm -rf {} +
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "results.xml" -delete
	find . -name "*.vcd" -delete
	find . -name "*.fst" -delete