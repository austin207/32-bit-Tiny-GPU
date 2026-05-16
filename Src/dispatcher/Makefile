TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(shell pwd)/dispatcher.sv
TOPLEVEL = dispatcher
COCOTB_TEST_MODULES = test_dispatcher
SIM = icarus
export PYTHONPATH := $(shell pwd):$(PYTHONPATH)
include $(shell cocotb-config --makefiles)/Makefile.sim
