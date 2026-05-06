TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(shell pwd)/scheduler.sv
TOPLEVEL = scheduler
COCOTB_TEST_MODULES = test_scheduler
SIM = icarus
export PYTHONPATH := $(shell pwd):$(PYTHONPATH)
include $(shell cocotb-config --makefiles)/Makefile.sim
