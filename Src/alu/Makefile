TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(shell pwd)/alu.sv
TOPLEVEL = alu
COCOTB_TEST_MODULES = test_alu
SIM = icarus
export PYTHONPATH := $(shell pwd):$(PYTHONPATH)
include $(shell cocotb-config --makefiles)/Makefile.sim
