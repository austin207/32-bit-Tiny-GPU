TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(shell pwd)/top_level_gpu.sv \
                  $(shell pwd)/../warp_stack/warp_stack.sv \
                  $(shell pwd)/../memory_controller/mem_controller.sv \
                  $(shell pwd)/../device_control_register/dcr.sv \
                  $(shell pwd)/../dispatcher/dispatcher.sv \
                  $(shell pwd)/../core/core.sv \
                  $(shell pwd)/../scheduler/scheduler.sv \
                  $(shell pwd)/../fetcher/fetcher.sv \
                  $(shell pwd)/../decoder/decoder.sv \
                  $(shell pwd)/../alu/alu.sv \
                  $(shell pwd)/../lsu/lsu.sv \
                  $(shell pwd)/../pc/pc.sv \
                  $(shell pwd)/../registers/register_file.sv

TOPLEVEL = gpu
SIM = icarus

export PYTHONPATH := $(shell pwd):$(PYTHONPATH)

COCOTB_TEST_MODULES ?= test_top_level_gpu,tests.test_phase08_mlp,tests.test_phase09_ldr,tests.test_phase10_mlp_8out,tests.test_phase11_mlp_8in,tests.test_phase12_mlp_q6,tests.test_phase13_digit_hidden,tests.test_phase14_digit_output,tests.test_phase15_digit64_hidden,tests.test_phase16_digit64_classifier

include $(shell cocotb-config --makefiles)/Makefile.sim

infer:
	rm -f results.xml
	$(MAKE) results.xml COCOTB_TEST_MODULES=inference