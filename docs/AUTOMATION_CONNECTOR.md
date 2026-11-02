# Bounded automatic charging connector

This is a separate opt-in from ABRP read-only telemetry. The cloud must implement
the matching protocol and an owner-approved plan. Installing support never enables
a cloud plan, changes evcc configuration, or starts a charge by itself.

## Contract

`X-Smart-EV-Automation: lease-v1` is sent only on work polls while both
`CONNECTOR_ALLOW_CONTROL=true` and `CONNECTOR_ALLOW_AUTOMATION=true`, with a healthy
local watchdog. Existing manual `mode-v1` commands remain unchanged.

`evcc.automation` has exactly these params:

```json
{
  "loadpoint": 1,
  "action": "start",
  "run_id": "c9c825ac-f60a-40c0-ae82-670b8c1fb362",
  "expires_at": "2026-11-03T05:00:45Z",
  "lease_until": "2026-11-03T05:01:30Z",
  "deadline": "2026-11-03T05:20:00Z"
}
```

The envelope `id` is a unique UUID. Actions are start, renew and stop. Each command
uses the same one-use `/authorize` endpoint and durable command journal as manual
control. Commands expire within 60 seconds (5-second clock tolerance). A lease
lasts at most 120 seconds and never extends beyond its immutable deadline, at most
24 hours from start. Renew with a new command ID about every 45 seconds only after
revalidating consent, plan, live state, energy/SoC budget and deadline. Stop may
carry the original expired lease/deadline, but its command expiry must be current.

The result contains exactly loadpoint, run_id, action, mode, verified,
lease_until and deadline. `verified: true` confirms the MODE, never charging power.
Observe a later fresh evcc state with charging=true and positive chargePower
before reporting that charging started.

Start requires a connected loadpoint, charging=false and mode=off. It cannot take
over a manual or PV charge. One run can own the connector. Renew/stop must match
the stored run, loadpoint and exact original deadline. A finished run ID cannot
restart. An ambiguous command write retains ownership until a stop is confirmed.

## Local fail-safe and limits

The watchdog checks every two seconds, subject to bounded local HTTP calls and
writer serialization. An expired lease, disconnect, disabled local control or
restart stops an owned `now` session. Both wall and monotonic clocks enforce expiry.
Unavailable evcc reads/writes retain the stop obligation and retry; they do not
claim successful stop. If the Pi, connector process, network or evcc itself fails,
software cannot guarantee a physical stop: retain the car/evcc target limit and
electrical protections, and require a bounded approved energy/time plan.

Observed external mode changes relinquish ownership without changing that mode.
Explicit cloud manual commands relinquish the matching local lease after evcc
accepts the write. A failed manual write retains watchdog protection. Changes
made directly in evcc that switch off then back to now between two samples cannot
be distinguished from the owned run. **Pause automation before taking over directly
in evcc.** The app must explain this; do not claim perfect external ownership detection.

## Upgrade

Use the pinned release's `deploy/install_abrp.py --automation-support` on the Pi.
This path upgrades only the existing connector, preserving Compose settings,
pairing and data. It leaves ABRP and evcc running, runs tests/build first, rejects
active local leases, and restores the previous image/settings on failed health.
The explicit flag enables local control capability; cloud consent is still required.

Before any later upgrade or rollback, disable the cloud plan, wait for the owned
charge to stop, and verify it in evcc. Keep the release directory because Compose
uses its override. The printed rollback command restores the prior connector.

## Tests

Run `python -m unittest discover -s local_connector -v` and
`python -m unittest discover -s deploy -p test_install_abrp.py -v`.
Tests use mocked charging controls. No real charger command is part of verification.
