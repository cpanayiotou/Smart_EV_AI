# Daily solar telemetry

This branch builds on the existing ABRP connector release. No evcc settings or
charging commands are changed. The adapter and existing pairing are preserved.

The cloud requests `evcc.pv_daily` only when the outbound worker advertises
`X-Smart-EV-History: pv-daily-v1`. Enable with
`CONNECTOR_PV_HISTORY_READONLY=true` (the pinned installer does this).

Parameters are exactly `date`, `timezone` (`Europe/Nicosia` or its equivalent
`Asia/Nicosia` alias), `from`, `to`,
`aggregate` (`15m`), `group` (`pv`). Only the current Cyprus-local calendar day
is accepted; stale dates, arbitrary ranges, extra parameters and URLs are rejected
before evcc is contacted. The fixed GET endpoint is `/api/history/energy`.

The result contains `date`, `timezone`, `energy_kwh`, `period_start`, `period_end`,
`last_interval_end`, `fetched_at`, `source` (`evcc_history_energy`). Only actual
PV interval energy is summed; the cumulative `pvEnergy` and forecast are not used.
For the updated cloud contract requesting `Asia/Nicosia`, the source is
`evcc/history/pv` and `complete_through_last_interval` is also returned. The
Europe alias preserves the initial eight-field cloud response format. Both
versions require complete coverage of all completed intervals.
Missing intervals fail the cloud read instead of presenting a partial total as
the full total. In-progress intervals are not estimated. The local inspection
route `/v1/evcc/solar/daily` additionally exposes coverage information and labels
its source `evcc/history/pv`.

The container includes timezone data for the 23/25-hour daylight-saving days.
The existing HTTP reader caps evcc responses at 2 MiB. Errors returned to the
cloud and local dashboard do not include private upstream response details.

Deployment uses `deploy/install_abrp.py`, pinned to the tested connector commit.
It verifies the running Compose deployment, builds the new image, preserves a
rollback image, and recreates only the connector with automatic rollback if
its health/ABRP checks fail. Keep the generated release directory and use its
printed rollback script if needed. No PR merge is required or authorised.

Cloud build validation and publication are separate. A successful local install
does not prove the cloud receiver is live. Verify the date, units, interval end
and displayed daily total after both parts are deployed.
