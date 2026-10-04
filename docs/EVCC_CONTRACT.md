# evcc Integration Contract — Phase 1

Verified against current evcc documentation before implementation.

## Read path

Initial backend uses the documented REST system-state endpoint and normalizes only fields required by the first dashboard.

The documented MQTT API will be added as the continuous telemetry path. Current documented topics include site home/PV/grid power and loadpoint connected/charging/mode/chargePower/vehicleSoc/phasesActive/sessionEnergy fields.

## Write path

**Disabled in Phase 1.**

evcc documents writable MQTT topics by appending `/set`, including loadpoint mode, SoC limits, phase/current limits and planning fields. Smart EV AI will not publish to them until Battery Guardian, approvals, simulation/shadow mode and fallback tests are implemented.

## Compatibility

evcc is actively developed and can introduce breaking API/MQTT changes. The adapter isolates evcc-specific field names from the rest of Smart EV AI. Pin/test an evcc version for production and run contract tests before upgrades.
