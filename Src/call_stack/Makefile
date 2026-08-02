TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(shell pwd)/call_stack.sv
TOPLEVEL = call_stack

COCOTB_TEST_MODULES ?= tests.test_call_stack_directed,tests.test_call_stack_random

SIM = icarus

export PYTHONPATH := $(shell pwd):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
