TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(shell pwd)/register_file.sv
TOPLEVEL = registers
COCOTB_TEST_MODULES = test_registers
SIM = icarus
export PYTHONPATH := $(shell pwd):$(PYTHONPATH)
include $(shell cocotb-config --makefiles)/Makefile.sim
