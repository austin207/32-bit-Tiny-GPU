TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(shell pwd)/dcr.sv
TOPLEVEL = dcr
COCOTB_TEST_MODULES = test_dcr
SIM = icarus
export PYTHONPATH := $(shell pwd):$(PYTHONPATH)
include $(shell cocotb-config --makefiles)/Makefile.sim
