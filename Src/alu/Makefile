TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(shell pwd)/alu.sv
TOPLEVEL = alu

COCOTB_TEST_MODULES ?= tests.test_alu_directed,tests.test_alu_random

SIM = icarus

export PYTHONPATH := $(shell pwd):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim