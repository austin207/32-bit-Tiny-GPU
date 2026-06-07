TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(shell pwd)/register_file.sv
TOPLEVEL = registers

COCOTB_TEST_MODULES ?= tests.test_registers_directed,tests.test_registers_random

SIM = icarus

export PYTHONPATH := $(shell pwd):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim