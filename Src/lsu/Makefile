TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(shell pwd)/lsu.sv
TOPLEVEL = lsu

COCOTB_TEST_MODULES ?= tests.test_lsu_directed,tests.test_lsu_random

SIM = icarus

export PYTHONPATH := $(shell pwd):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim