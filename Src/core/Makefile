TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(shell pwd)/core.sv \
                  $(shell pwd)/../warp_stack/warp_stack.sv \
                  $(shell pwd)/../memory_controller/mem_controller.sv \
                  $(shell pwd)/../scheduler/scheduler.sv \
                  $(shell pwd)/../fetcher/fetcher.sv \
                  $(shell pwd)/../decoder/decoder.sv \
                  $(shell pwd)/../alu/alu.sv \
                  $(shell pwd)/../lsu/lsu.sv \
                  $(shell pwd)/../pc/pc.sv \
                  $(shell pwd)/../registers/register_file.sv

TOPLEVEL = core

COCOTB_TEST_MODULES ?= tests.test_core_directed,tests.test_core_random

SIM = icarus

export PYTHONPATH := $(shell pwd):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim