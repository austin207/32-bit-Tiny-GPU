TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(shell pwd)/fetcher.sv
TOPLEVEL = fetcher
COCOTB_TEST_MODULES = test_fetcher
SIM = icarus
export PYTHONPATH := $(shell pwd):$(PYTHONPATH)
include $(shell cocotb-config --makefiles)/Makefile.sim
