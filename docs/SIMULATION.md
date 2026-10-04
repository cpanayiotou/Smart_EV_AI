# Simulation Mode

Until the real Huawei DTSU, Peblar and evcc installation is available, development uses a deterministic home simulator.

## Purpose
- build the PWA without hardware
- test telemetry normalization
- test Battery Guardian and future agents safely
- create repeatable scenarios for automated tests
- develop shadow-mode orchestration before live actuation

## Model
The initial simulator represents:
- Cyprus local time
- a ~5 kW PV system with a simple daylight production curve
- repeatable household base/morning/evening demand
- Audi e-tron 55 with configurable SoC/target
- plugged-at-home windows
- approximate PV-surplus charging
- 1P/3P charging state
- grid import/export derived from home + EV - PV

It is intentionally a development model, not a claim of exact solar production, battery capacity, charger efficiency or household behaviour.

## Safety
Simulation is always marked `source=simulator` and `read_only=true`. No simulator path sends commands to physical hardware.

## Progression
Simulation -> automated tests -> AI shadow mode -> real hardware read-only -> validated real control.
