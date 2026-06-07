TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(shell pwd)/decoder.sv
TOPLEVEL = decoder

COCOTB_TEST_MODULES ?= tests.test_decoder_directed,tests.test_decoder_random

SIM = icarus

export PYTHONPATH := $(shell pwd):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim