TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(shell pwd)/matmul_accelerator.sv
TOPLEVEL = matmul_accelerator
COCOTB_TEST_MODULES ?= tests.test_matmul_directed,tests.test_matmul_random,tests.test_matmul_edge
SIM = icarus
export PYTHONPATH := $(shell pwd):$(PYTHONPATH)
include $(shell cocotb-config --makefiles)/Makefile.sim