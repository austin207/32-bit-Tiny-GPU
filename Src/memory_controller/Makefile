TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(shell pwd)/mem_controller.sv
TOPLEVEL = mem_controller

COCOTB_TEST_MODULES ?= tests.test_mem_controller_directed,tests.test_mem_controller_random

SIM = icarus

export PYTHONPATH := $(shell pwd):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim