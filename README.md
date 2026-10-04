# Smart EV AI

Local-first AI energy management and smart charging platform for an Audi e-tron home charging system.

## Architecture

**evcc + ABRP → AI Energy Manager → Battery Guardian → Energy Orchestrator → evcc → Peblar → Audi**

- **evcc** is the primary live operational telemetry hub and deterministic real-time charging controller.
- **ABRP** supplies mobility, route and predicted energy requirements.
- **AI Energy Manager** makes high-level charging decisions.
- **Battery Guardian** is a deterministic hard-policy layer with veto authority.
- **Energy Orchestrator** combines specialist recommendations into one approved objective.
- **PWA** provides one dashboard across phone, tablet and desktop.

## Core priorities

1. Battery safety and health
2. Required mobility
3. Household electrical limits
4. Charging efficiency
5. PV self-consumption
6. Electricity cost

Normal daily battery target: **80%**. Higher targets require a justified mobility need and explicit approval under the Battery Guardian policy.

## Development principle

Use official/upstream evcc as the proven charging foundation. Smart EV AI is a separate intelligence/UI layer using supported evcc interfaces. Start read-only, validate telemetry and safety behaviour, then introduce controlled high-level actuation.

## Status

Initial project scaffold.
