TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(shell pwd)/lsu.sv
TOPLEVEL = lsu
COCOTB_TEST_MODULES = test_lsu
SIM = icarus
export PYTHONPATH := $(shell pwd):$(PYTHONPATH)
include $(shell cocotb-config --makefiles)/Makefile.sim
