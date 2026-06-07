TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(shell pwd)/dcr.sv
TOPLEVEL = dcr

COCOTB_TEST_MODULES ?= tests.test_dcr_directed,tests.test_dcr_random

SIM = icarus

export PYTHONPATH := $(shell pwd):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim