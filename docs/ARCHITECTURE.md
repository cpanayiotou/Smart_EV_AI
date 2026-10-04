# Architecture

Smart EV AI is an independent intelligence and UI layer built around official/upstream evcc.

```text
Huawei + DTSU ─┐
Peblar ─────────┼─> evcc ──> telemetry ──> Smart EV AI <── ABRP
Audi ──────────┘                              │
                                             ▼
                                     Battery Guardian
                                             ▼
                                     Energy Orchestrator
                                             ▼
                                            evcc
                                             ▼
                                           Peblar
                                             ▼
                                            Audi
```

## Control boundaries

**Fast loop — evcc:** seconds-scale PV/grid response, EVSE current, phase switching, start/stop and configured electrical constraints.

**Planning loop — Smart EV AI:** minutes/event-driven target SoC, deadline, PV/grid strategy, trip readiness and cost optimisation.

**Learning loop:** session/daily/weekly comparison of predicted versus actual trip energy, PV, cost and charging results.

## Fail-safe

Smart EV AI is an optimisation layer, not a prerequisite for basic charging. Loss of AI, ABRP or the PWA must not remove evcc's ability to operate using independently configured safe defaults.
