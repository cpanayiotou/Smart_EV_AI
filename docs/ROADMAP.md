# Roadmap

## Phase 1 — Foundation
- Verify current evcc REST/MQTT contracts.
- Build read-only evcc telemetry adapter.
- Define normalized telemetry schema.
- Add local development stack.
- Add PWA shell/live mock dashboard.
- No AI live actuation.

## Phase 2 — Install & Measure
- Validate Huawei SUN2000 + DTSU in evcc.
- Validate Peblar telemetry/control.
- Validate Audi SoC/status.
- Store trusted time-series telemetry.
- Establish safe evcc fallback.

## Phase 3 — Mobility
- Integrate ABRP/Enode after API/auth verification.
- Compare predicted and actual trip energy/arrival SoC.
- Decide whether optional OBD adds measurable value.

## Phase 4 — Intelligence
- Battery Guardian
- Mobility Agent
- Solar Agent
- Cost Agent
- Efficiency Agent
- Home/Energy Agent
- Data quality layer

## Phase 5 — Orchestrator
- Generate high-level charging objectives.
- Run simulation/shadow mode first.
- Add user approval workflow.
- Enable controlled evcc writes only after validation.

## Phase 6 — Adaptive Optimisation
- Learn from historical sessions/trips while maintaining battery-health-first policy.
