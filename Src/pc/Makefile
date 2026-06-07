TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(shell pwd)/pc.sv
TOPLEVEL = pc

COCOTB_TEST_MODULES ?= tests.test_pc_directed,tests.test_pc_random

SIM = icarus

export PYTHONPATH := $(shell pwd):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim