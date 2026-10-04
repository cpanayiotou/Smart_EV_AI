# Digital Twin

Phase 1 can run without physical hardware. The stateful simulator advances a virtual Cyprus day and integrates simulated PV, grid import/export, AC charging energy and Audi SoC.

## Safety boundary
The twin is development-only. Battery capacity, AC-to-battery efficiency and service limit are configurable assumptions, not measured Audi/EAC values. No command is sent to evcc or Peblar.

## API
- GET /api/v1/simulation
- POST /api/v1/simulation/advance with {"minutes": 60}
- POST /api/v1/simulation/reset
- GET /api/v1/plan

The advance endpoint also returns a shadow plan so UI experiments can observe telemetry and planning together.

## Persistence
PostgreSQL is already provisioned in Docker Compose. Durable telemetry/session persistence is the next storage step; Phase 1 currently keeps simulator state in-process so the simulation contract can settle before database migrations are introduced.
