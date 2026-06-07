TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(shell pwd)/dispatcher.sv
TOPLEVEL = dispatcher

COCOTB_TEST_MODULES ?= tests.test_dispatcher_directed,tests.test_dispatcher_random

SIM = icarus

export PYTHONPATH := $(shell pwd):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim