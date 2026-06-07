TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(shell pwd)/fetcher.sv
TOPLEVEL = fetcher

COCOTB_TEST_MODULES ?= tests.test_fetcher_directed,tests.test_fetcher_random

SIM = icarus

export PYTHONPATH := $(shell pwd):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim