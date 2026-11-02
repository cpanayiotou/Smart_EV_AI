# Verified evcc session target (target-v1)

The Plan screen must distinguish saving a cloud plan from applying its target to evcc.
No target is sent on page load, suggestion generation, or connector installation.
The user explicitly applies the saved target. This does not start charging.

## Wire contract

The work poll advertises `X-Smart-EV-Target: target-v1` only when local
`CONNECTOR_ALLOW_CONTROL=true`. The LAN health response includes `target_capable`.

Command `evcc.set_target`, canonical UUID request ID, exact parameters:

```json
{
  "loadpoint": 1,
  "target_soc": 74,
  "expected_limit_soc": 80,
  "expires_at": "2026-11-02T20:00:45Z"
}
```

Loadpoint is an integer 1–20; daily target is an integer 1–80; expected effective
limit is an integer 1–100. Expiry is timezone-aware and at most 60 seconds ahead
(Pi accepts five seconds clock tolerance). Extra fields, booleans and string
numbers are rejected. No URLs, currents, phases or global vehicle limits are accepted.

The Pi uses the existing durable one-attempt journal and one-use cloud authorization.
Before and after authorization it requires: controls enabled, no local automation
lease, connected true, charging false, mode off, and effectiveLimitSoc equal to the
expected value. It serializes with other connector writes and the watchdog.

The fixed local POST is `/api/loadpoints/{id}/limitsoc/{target_soc}` with no proxies
or redirects. Success requires readback of both limitSoc and effectiveLimitSoc equal
to the requested target, connected true, charging false and mode off. Result:

```json
{"loadpoint":1,"target_soc":74,"verified":true,"mode":"off"}
```

An ambiguous timeout is not retried automatically. An acknowledgement is evidence
of the setting at that moment, not permanent state. External evcc clients are not
locked by this connector; concurrent external edits can still invalidate the result.

## Cloud requirements

Enqueue and the one-use database grant must check owner, active connector, current
controls consent, target capability, fresh charger state, no active automation run,
unchanged plan settings, target equal to the saved target, and expected effective limit.
Automation start must require the current effective limit equals the saved target.
Stop must remain usable without a fresh battery reading or target match.

evcc resets the loadpoint session limit on disconnect. The vehicle's normal default
is left unchanged. UI readiness must derive from current connected charger state,
not a stored applied flag; require reapplication when the session limit no longer
matches. This is a session target, not a persistent vehicle default.

## Validation and installation

`python -m unittest discover -s local_connector` includes mocked target tests;
no tests send commands to real hardware. Installer `--automation-support` upgrades
only the connector and checks both automation and target capabilities. It leaves
evcc and ABRP running and does not enable the cloud plan or apply a target.

Official endpoint reference: https://docs.evcc.io/en/docs/integrations/rest-api/
