TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(shell pwd)/pc.sv
TOPLEVEL = pc
COCOTB_TEST_MODULES = test_pc
SIM = icarus
export PYTHONPATH := $(shell pwd):$(PYTHONPATH)
include $(shell cocotb-config --makefiles)/Makefile.sim
