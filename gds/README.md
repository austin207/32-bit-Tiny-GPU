# OpenLane / Sky130A GDS

## Overview

This folder contains the ASIC layout output for the 32-bit Tiny GPU.

The full GPU RTL was taken through the open-source RTL-to-GDSII flow using OpenLane 2.3.10 and the SkyWater Sky130A PDK.

The target design is:

```text
Design name: gpu
Process: SkyWater Sky130A
Standard cell library: sky130_fd_sc_hd
Tool flow: OpenLane 2.3.10 / OpenROAD
Clock target: 40 MHz
Clock period: 25 ns
```

The result is a synthesized and routed GDSII layout for the GPU core.

---

## Layout Preview

![GPU Layout](../assets/gds/gpu_layout.png)

The layout image shows the routed GPU with visible metal layers. The dense logic region contains the compute-core logic, scheduler/control path, register files, ALUs, LSUs, and supporting datapath/control modules.

If the image path changes, update the path above to match the actual file inside:

```text
assets/gds/
```

---

## Output Files

Expected layout-related files:

```text
gds/
└── gpu.klayout.gds
```

Related reports:

```text
reports/
├── chk.rpt
├── latch.rpt
├── manufacturability.rpt
├── post_dff.rpt
├── pre_synth_chk.rpt
├── pre_techmap.rpt
└── stat.rpt
```

Related image assets:

```text
assets/gds/
└── gpu_layout.png
```

---

## Final ASIC Results

| Metric                  |                      Value |
| ----------------------- | -------------------------: |
| Standard cells          |                    204,938 |
| Chip area               |                  1.977 mm² |
| Flip-flops              |                     16,138 |
| Clock target            |                     40 MHz |
| Clock period            |                      25 ns |
| Worst setup slack       |                   +8.01 ns |
| Estimated max frequency |                    ~59 MHz |
| Total negative slack    |                       0 ps |
| LVS result              |                     Passed |
| LVS devices matched     |                    171,278 |
| LVS nets matched        |                    171,969 |
| PDK                     |           SkyWater Sky130A |
| Standard cell library   |            sky130_fd_sc_hd |
| Tool flow               | OpenLane 2.3.10 / OpenROAD |

---

## Status Summary

```text
Synthesis:        passed
Placement:        passed
CTS:              passed
Global routing:   passed
Detailed routing: passed
Timing:           passed
LVS:              passed
GDS generated:    yes
```

Known physical verification note:

```text
DRC showed a small number of violations:
  Magic:   5 violations
  KLayout: 1 violation
```

These were minor routing/spacing issues from the open-source routing flow. Timing and LVS passed, and the final GDS was generated.

---

## Design Scale

This was not a tiny toy netlist by open-source ASIC-flow standards.

The GPU contained:

```text
204,938 standard cells
16,138 flip-flops
~1.977 mm² chip area
```

The design was large enough that routing, memory usage, OpenROAD stability, and resizer behavior became major practical issues.

---

## RTL Preparation Before ASIC Flow

Before running the ASIC flow, the FPGA/synthesis-ready combined Verilog was prepared.

Important preparation steps:

```text
1. Removed simulation-only constructs.
2. Removed $dumpfile / $dumpvars from synthesis-target RTL.
3. Replaced DIV and MOD with 32'b0 in the synthesis target.
4. Used a synthesis-friendly combined Verilog file.
```

Why DIV/MOD were disabled:

```text
DIV and MOD synthesize into large combinational dividers.
They create deep timing paths and heavy area/routing pressure.
For this ASIC run, they were replaced with 32'b0 and documented as future multi-cycle units.
```

Future improvement:

```text
Implement DIV/MOD as iterative multi-cycle units instead of single-cycle combinational operators.
```

---

## Final Working OpenLane 2 Config

The final working OpenLane 2 configuration was:

```json
{
    "DESIGN_NAME": "gpu",
    "VERILOG_FILES": "dir::src/*.v",
    "CLOCK_PORT": "clk",
    "CLOCK_NET": "clk",
    "CLOCK_PERIOD": 25,
    "FP_CORE_UTIL": 25,
    "PL_TARGET_DENSITY_PCT": 35,
    "SYNTH_STRATEGY": "AREA 0",
    "MAX_FANOUT_CONSTRAINT": 8,
    "RUN_POST_GPL_DESIGN_REPAIR": false,
    "RUN_POST_CTS_RESIZER_TIMING": false,
    "GRT_RESIZER_DESIGN_OPTIMIZATIONS": false,
    "GRT_RESIZER_TIMING_OPTIMIZATIONS": false,
    "GRT_ADJUSTMENT": 0.1,
    "DRT_THREADS": 1,
    "PDK": "sky130A",
    "STD_CELL_LIBRARY": "sky130_fd_sc_hd"
}
```

---

## Why Resizers Were Disabled

The most important physical-design issue was excessive buffer insertion by OpenLane/OpenROAD resizer stages.

The design already had strong positive slack after synthesis:

```text
Worst setup slack: +8.01 ns
```

Despite that, the default flow inserted tens of thousands of timing/repair buffers.

Observed behavior:

```text
Synthesis result: ~204k cells
After resizer bloat: ~293k cells
```

This made routing harder without providing useful timing benefit.

Final decision:

```text
Disable all major post-placement/post-CTS/global-routing resizer optimization passes.
Route the synthesized netlist directly.
```

Disabled settings:

```json
{
    "RUN_POST_GPL_DESIGN_REPAIR": false,
    "RUN_POST_CTS_RESIZER_TIMING": false,
    "GRT_RESIZER_DESIGN_OPTIMIZATIONS": false,
    "GRT_RESIZER_TIMING_OPTIMIZATIONS": false
}
```

This reduced routing congestion and allowed the design to complete.

---

## Routing Adjustment

The final flow used:

```json
"GRT_ADJUSTMENT": 0.1
```

This gave the global router access to more available routing tracks.

Earlier default-style routing adjustment values were too conservative for this design and contributed to routing congestion.

With the final setting, global routing passed cleanly.

---

## Detailed Routing Settings

Detailed routing was run conservatively:

```json
"DRT_THREADS": 1
```

Reason:

```text
The design was large for a consumer laptop.
Running detailed routing with one thread reduced memory pressure and improved stability.
```

Detailed routing took approximately several hours but completed.

---

## OpenLane 1 Attempt

The first flow attempts used OpenLane 1.

Synthesis consistently passed:

```text
Standard cells: 204,938
Area: 1.977 mm²
Worst setup slack: +8.01 ns
```

But physical implementation failed.

Initial issue:

```text
Placement failed with GPL-0302 due to density settings.
```

Increasing placement/core density fixed placement.

Next issue:

```text
Global routing failed with GRT-0119 due to congestion.
```

Root cause:

```text
Post-placement resizer inserted ~44,920 timing repair buffers.
This bloated the design from ~204k cells to ~293k cells.
```

After disabling resizers and lowering routing adjustment, global routing passed.

However, OpenROAD then crashed with a deterministic FastRoute segmentation fault.

Conclusion:

```text
OpenLane 1 / that OpenROAD binary was not stable enough for this design.
The issue was a tool binary/code bug, not an RTL configuration problem.
```

---

## WSL2 Issue

Several runs on WSL2 caused severe system instability.

Observed problems:

```text
WSL2 memory pressure
Docker/OpenROAD peak RAM usage
GPU driver/overlay conflicts
system hangs under long routing runs
```

The practical conclusion was:

```text
Do not run this 200k+ cell OpenLane flow under WSL2.
Use native Ubuntu for serious OpenLane runs.
```

Switching to native Ubuntu dual boot eliminated the instability.

---

## OpenLane 2 Success

The successful flow used:

```text
OpenLane 2.3.10
Native Ubuntu
Docker
Sky130A PDK
```

OpenLane 2 used a newer OpenROAD binary, and the deterministic FastRoute crash from OpenLane 1 did not reappear.

After disabling resizers, global routing passed.

The flow later hit an antenna-report crash after global routing. The workaround was:

```text
Disable the antenna checker/report step.
Resume from the saved global-routing state.
Continue into detailed routing.
```

Detailed routing completed, LVS passed, and GDS was generated.

---

## Final Verification Result

### Timing

Timing passed:

```text
Worst setup slack: +8.01 ns
Total negative slack: 0 ps
Clock period: 25 ns
Clock target: 40 MHz
Estimated max frequency: ~59 MHz
```

### LVS

LVS passed:

```text
171,278 devices matched
171,969 nets matched
```

This means the final layout matched the intended netlist.

### DRC

DRC had a small number of violations:

```text
Magic:   5 violations
KLayout: 1 violation
```

Current status:

```text
GDS is generated and LVS/timing clean.
DRC is not fully clean yet.
```

Future work should resolve the remaining DRC violations before treating the layout as tapeout-clean.

---

## Lessons Learned

## 1. Positive synthesis slack does not mean resizers should run

The design already had timing margin after synthesis.

Letting the flow insert tens of thousands of buffers made the physical design worse:

```text
more cells
more congestion
harder routing
longer runtime
```

For this GPU, disabling resizers was the correct move.

## 2. OpenLane 2 is better for large designs

OpenLane 1 reached a deterministic OpenROAD crash during routing.

OpenLane 2.3.10 used a newer OpenROAD build and completed the flow.

For future Sky130 work, start with OpenLane 2.

## 3. Native Ubuntu was more stable than WSL2

A 200k+ cell design can push consumer hardware hard.

Native Ubuntu gave Docker/OpenROAD direct access to system resources and avoided WSL2-related instability.

## 4. Detailed routing needs memory discipline

Using:

```text
DRT_THREADS = 1
```

made the run slower but more stable.

For this design, stability mattered more than parallel speed.

## 5. DIV/MOD should become multi-cycle hardware

Single-cycle combinational DIV/MOD are not a good fit for ASIC physical implementation at this scale.

Future versions should use iterative dividers or remove DIV/MOD from the synthesis target.

---

## How to Inspect the GDS

Open the generated GDS in KLayout:

```bash
klayout gds/gpu.klayout.gds
```

Or from the repository root:

```bash
klayout ./gds/gpu.klayout.gds
```

Expected file:

```text
gds/gpu.klayout.gds
```

Expected preview image:

```text
assets/gds/gpu_layout.png
```

---

## Related Documentation

| Document                   | Path                      |
| -------------------------- | ------------------------- |
| Root project README        | `../README.md`            |
| Architecture documentation | `../docs/architecture.md` |
| ISA documentation          | `../docs/isa.md`          |
| Memory map                 | `../docs/memory_map.md`   |
| Debug log                  | `../docs/debug_log.md`    |
| FPGA documentation         | `../fpga/README.md`       |
| Reports folder             | `../reports/`             |

---

## Recommended Future Work

1. Fix remaining Magic/KLayout DRC violations.
2. Re-run OpenLane on the latest SIMT RTL if the current GDS was built from an older combined file.
3. Keep DIV/MOD disabled until iterative units exist.
4. Add a clean OpenLane 2 run directory or script to reproduce the flow.
5. Add exact commit hash / RTL version used for this GDS.
6. Add final DRC screenshots and summary.
7. Add die/core dimensions from final OpenLane reports.
8. Add power numbers if available from reports.
9. Add area breakdown by module if Yosys/OpenROAD reports are available.
10. Add a short tapeout-readiness checklist.

---

## Tapeout Readiness Checklist

Current state:

| Item                      | Status                           |
| ------------------------- | -------------------------------- |
| RTL synthesis             | Done                             |
| Timing closure            | Done                             |
| Global routing            | Done                             |
| Detailed routing          | Done                             |
| LVS                       | Passed                           |
| GDS generated             | Done                             |
| DRC fully clean           | Not yet                          |
| Antenna report            | Needs clean rerun / verification |
| Power signoff             | Not documented yet               |
| Final run reproducibility | Needs script/config archive      |
| Tapeout-ready             | Not yet                          |

The current layout is a successful educational GDS result, but it should not be described as tapeout-ready until the remaining DRC/antenna/signoff items are resolved.

---

## Summary

This GDS run proves that the Tiny GPU RTL is large but physically implementable in Sky130A using the open-source ASIC flow.

The important result:

```text
204,938-cell GPU
1.977 mm²
40 MHz target met
+8.01 ns setup slack
LVS passed
GDS generated
```

The important caveat:

```text
Remaining DRC/antenna/signoff cleanup is still required before tapeout readiness.
```

The most important flow lesson:

```text
For this design, disabling aggressive OpenLane/OpenROAD resizers was essential.
The resizers created congestion instead of improving timing.
```
