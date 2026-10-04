# Backend

Responsibilities: consume evcc telemetry, consume ABRP mobility data, normalize/validate and persist data, run Battery Guardian and specialist agents, orchestrate charging objectives, expose one API/WebSocket stream to the PWA, and eventually send approved high-level objectives to evcc.

**First milestone: read-only telemetry.** Live actuation is deliberately deferred until API contracts, safety rules and fallback behaviour are tested.
