TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(shell pwd)/warp_stack.sv
TOPLEVEL = warp_stack

COCOTB_TEST_MODULES ?= tests.test_warp_stack_directed,tests.test_warp_stack_random

SIM = icarus

export PYTHONPATH := $(shell pwd):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim