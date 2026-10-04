# Battery Guardian Policy

Battery Guardian is deterministic policy, not a free-form AI agent.

## Priority
1. Battery safety and health
2. Required mobility
3. Household electrical limits
4. Charging efficiency
5. PV self-consumption
6. Electricity cost

## Initial rules
- Normal daily target: **80%**.
- Above 80% requires justified mobility need and the minimum sufficient target.
- 100% is exceptional and requires explicit approval.
- Where practical, high-SoC charging should finish close to departure.
- Avoid unnecessary high-SoC dwell and unnecessary very-low-SoC exposure.
- Track DC fast charging separately from home AC charging.
- Plug-in sessions are not battery cycles.
- Never claim SoH, battery temperature, DC energy or cell data unless a reliable source actually provides it.

Any optimisation violating a hard rule is rejected before an objective reaches evcc.
