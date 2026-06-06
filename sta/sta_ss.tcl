read_liberty /pdks/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__ss_100C_1v60.lib
read_verilog /design/nl/gpu.nl.v
link_design gpu
read_sdc /design/sdc/gpu.sdc
set_false_path -from [get_ports rst]
set_false_path -to [get_ports thread_keep_alive]
read_sdf /design/sdf/nom_ss_100C_1v60/gpu__nom_ss_100C_1v60.sdf
report_checks -path_delay max -format full_clock_expanded -digits 3 -slack_max 0.5
report_wns
report_tns
report_worst_slack -max
exit
