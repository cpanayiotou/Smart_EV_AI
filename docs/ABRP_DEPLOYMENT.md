# Read-only ABRP / Enode adapter for Raspberry Pi

Status: experimental implementation; **not deployed**. Authenticated Audi telemetry and the existing Pi connector are not yet validated. No charging actuation is implemented. No evcc/Peblar configuration is changed by these instructions.

## What was verified (2026-11-01)

- Smart_EV_AI base commit: `af8396c1369d31904007e3394dbc9db1bcc7e845`. It is a scaffold, with no source for the existing service on port 7080.
- Reviewed [MichelFR/ha-abrp](https://github.com/MichelFR/ha-abrp/tree/73526dd86d4dc51e095312fe101f6634eb06264e) at `73526dd86d4dc51e095312fe101f6634eb06264e`: `const.py`, `oauth.py`, `api.py`, `metadata.py`, `token_manager.py` and LICENSE. MIT, copyright 2026 Michel Ferreira Ribeiro; full notice is included in `THIRD_PARTY_NOTICES.md`.
- Current public ABRP website metadata was discoverable. A deliberately invalid session sent to the read endpoint was rejected with an authentication error. The unauthenticated PKCE authorization start returned a login session and CSRF cookie; its login page matched the connect-link format. No user account was logged in during these checks.
- The reviewed implementation uses `POST https://api.iternio.com/1/session/get_tlm`, `Authorization: APIKEY <public web key>`, and JSON `session_id` containing the OAuth access token. HTTP POST here is a telemetry read, not a vehicle command.
- Each result has `vehicle_id`, `tlm.soc`, `tlm.timestamps.soc` (Unix seconds), and `tlm.providers.soc`. Vehicle/cloud timestamps are not necessarily SoC measurement times. This adapter requires the per-field timestamp and the exact provider `enode`; it fails closed if the account's shape differs.
- Upstream also implements SSE and settings writes. This adapter implements neither. It polls every 600 seconds and rejects SoC older than 900 seconds. It does not wake the car or force Enode refreshes. Parked vehicles may legitimately remain unavailable for long periods.
- The private login asks for `oidc profile email offline_access` using ABRP's `app` client, not a narrowly scoped official telemetry client. The adapter's behavior is read-only; the stored session itself is **not guaranteed read-only**. MIT licensing does not grant ABRP API permission or guarantee continued service. Prefer the official access path below for long-term use.

The public checks do not prove token exchange, token rotation, authenticated `get_tlm`, Audi identity, Enode field names or measurement timing on this account. The local acceptance steps below are required. Do not label the adapter production-ready until they pass.

## Interface and integration boundary

```text
Audi → existing Enode → ABRP → adapter 127.0.0.1:7081
                                      ↑ GET only
                              existing connector :7080
evcc :7070 and Peblar: unchanged
```

The service binds only to `127.0.0.1`; it refuses ports 7070 and 7080. There are no calls to evcc, Peblar, Audi, Enode commands, ABRP settings or telemetry-upload endpoints. A positive, explicitly selected ABRP vehicle ID is mandatory. Unknown/duplicate vehicles, invalid/non-finite SoC, missing/future/regressing field timestamps, provider mismatches, upstream errors and expired authorization all withhold usable SoC.

| GET endpoint | Result |
|---|---|
| `/healthz` | HTTP 200 process liveness; inspect `telemetry_available` separately |
| `/v1/abrp/telemetry` | HTTP 200 fresh normalized JSON; HTTP 503 with `soc_percent: null` on failure/staleness |
| `/v1/abrp/soc` | HTTP 200 plain numeric percent only when fresh; otherwise HTTP 503 |

JSON includes `vehicle_id`, `soc_percent`, `soc_timestamp`, `fetched_at`, `age_seconds`, `max_age_seconds`, `source`, `available`, and `read_only` for a validated sample. Early errors omit sample fields. Timestamps are Unix UTC seconds. Freshness is recomputed on every request and uses monotonic elapsed time as well as wall time. No cached sample is exposed as usable after an upstream error. Responses use `Cache-Control: no-store`. POST/PUT/PATCH/DELETE return 405. No credentials, VIN or coordinates appear in the API or normal logs.

For port 7080, add two GET-only routes in the **existing connector's source** which request the matching 7081 paths with a 5-second timeout. Preserve upstream 503 and no-store; on timeout or invalid response return 503 and null SoC. Never return the connector's last successful numeric SoC after failure. Do not make the sidecar bind to 7080 or replace the existing process. Source access is needed to supply and test a framework-specific patch. A connector in a separate Docker network cannot use the host's `127.0.0.1`; verify its network topology before integration, and do not expose 7081 on all interfaces as a shortcut.

## Exact isolated Pi installation

Prerequisites: Raspberry Pi OS/Debian with systemd, Python **3.11+**, git and curl; synchronized clock; SSH access already configured locally. No secrets belong in this repository, chat, command arguments, shell history or screenshots. Run authorization yourself in a private terminal, not through an assistant-run tool or terminal recorder. The link is a short-lived credential; do not share it.

Obtain this change in a **new checkout**, not the running connector checkout. From the directory containing this change (the delivered ZIP's `Smart_EV_AI` folder also works), run the following on the Pi. Do not run the installation if the preflight shows an existing adapter installation; review an upgrade separately.

```bash
python3 --version
timedatectl status
sudo ss -ltnp '( sport = :7070 or sport = :7080 or sport = :7081 )'
curl --max-time 5 -sS -o /dev/null -w 'evcc HTTP %{http_code}\n' http://127.0.0.1:7070/
curl --max-time 5 -sS -o /dev/null -w 'connector HTTP %{http_code}\n' http://127.0.0.1:7080/
test ! -e /opt/smart-ev-abrp
test ! -e /etc/systemd/system/smart-ev-abrp.service
test ! -e /etc/smart-ev-abrp.conf
test ! -e /var/lib/smart-ev-abrp
```

Record baseline status codes; a connector root may legitimately be 404. **Stop if 7081 is occupied, clock synchronization is absent, Python is older than 3.11, or any `test` fails.** Nothing needs to be stopped on 7070/7080. Then:

```bash
python3 -m unittest discover -s backend -p 'test_*.py' -v
sudo useradd --system --user-group --home-dir /var/lib/smart-ev-abrp --shell /usr/sbin/nologin smart-ev-abrp
sudo install -d -m 0755 /opt/smart-ev-abrp
sudo install -m 0644 backend/abrp_adapter.py /opt/smart-ev-abrp/abrp_adapter.py
sudo install -d -m 0700 -o smart-ev-abrp -g smart-ev-abrp /var/lib/smart-ev-abrp
sudo -u smart-ev-abrp python3 /opt/smart-ev-abrp/abrp_adapter.py login \
  --credentials /var/lib/smart-ev-abrp/tokens.json
```

Open the printed private approval link on your own device signed in to your existing ABRP Premium account; approve only the login you just initiated. No Audi or ABRP password is entered into the adapter. Approval expires after approximately three minutes. Failure messages are reason codes only. `login_state_mismatch` means the private protocol differs; do not bypass the state check.

After authorization:

```bash
sudo -u smart-ev-abrp python3 /opt/smart-ev-abrp/abrp_adapter.py vehicles \
  --credentials /var/lib/smart-ev-abrp/tokens.json
read -r -p 'ABRP vehicle_id for your Audi e-tron: ' VEHICLE_ID
case "$VEHICLE_ID" in ''|*[!0-9]*) echo 'Invalid vehicle ID'; exit 1;; esac
test "$VEHICLE_ID" -gt 0 || exit 1
printf 'ABRP_VEHICLE_ID=%s\n' "$VEHICLE_ID" | sudo tee /etc/smart-ev-abrp.conf >/dev/null
sudo chmod 0644 /etc/smart-ev-abrp.conf
sudo install -m 0644 deploy/smart-ev-abrp.service /etc/systemd/system/smart-ev-abrp.service
sudo systemd-analyze verify /etc/systemd/system/smart-ev-abrp.service
sudo systemctl daemon-reload
sudo systemctl start smart-ev-abrp
```

The vehicle listing is local-only and deliberately omits tokens, VIN and location. Confirm the name/model against your Audi in ABRP; do not just take the first vehicle. The configuration file contains only its numeric ID. Refresh credentials live in a mode-0600 file under a mode-0700 directory; rotated tokens are atomically persisted before use. Only one process may use the file (Linux file lock). Do not run `vehicles` or `login` while the adapter service owns it.

## Acceptance, observation and rollback

```bash
systemctl is-active smart-ev-abrp
curl --max-time 5 -i http://127.0.0.1:7081/healthz
curl --max-time 5 -i http://127.0.0.1:7081/v1/abrp/telemetry
curl --max-time 5 -i http://127.0.0.1:7081/v1/abrp/soc
curl --max-time 5 -i -X POST http://127.0.0.1:7081/v1/abrp/soc
curl --max-time 5 -sS -o /dev/null -w 'evcc HTTP %{http_code}\n' http://127.0.0.1:7070/
curl --max-time 5 -sS -o /dev/null -w 'connector HTTP %{http_code}\n' http://127.0.0.1:7080/
sudo journalctl -u smart-ev-abrp -n 30 --no-pager
```

Expect initial 503 until the first poll succeeds. POST must be 405. Compare fresh SoC with the existing Audi/ABRP display and check `soc_timestamp`, provider and vehicle identity. Observe a parked period longer than 15 minutes: repeated polls must not reset SoC's measurement age; old data must return 503/null. Observe an actual new reading and recovery. Keep the service running beyond the access-token lifetime and restart **only this adapter** to verify refresh-token rotation persists. Compare existing service status with baseline. Do not change evcc mode, target, current, phases or loadpoint assignment during these checks.

Only after these checks pass:

```bash
sudo systemctl enable smart-ev-abrp
```

For an account authorization error, stop only this service, run the same local `login` command, then start it again. Revoked authorization stops polling rather than repeatedly using a revoked grant. Network/HTTP failures back off to at most hourly retries. An unexpected internal error leaves the API unavailable until the service is restarted after investigation. For `web_metadata_changed` or `login_protocol_changed`, review the upstream protocol; do not insert arbitrary credentials or disable validation. The service does not invent fresh timestamps when Enode omits them.

Rollback is independent of evcc and the existing connector:

```bash
sudo systemctl disable --now smart-ev-abrp
```

If port-7080 forwarding has later been added, revert only those new routes through that connector's normal deployment process. The adapter never edits evcc or Peblar. Retain or securely remove the local credential file according to your preference and revoke the ABRP session through the account's available controls if retiring it. Never publish diagnostic dumps containing credentials.

## evcc compatibility, deliberately not activated

The scalar `/v1/abrp/soc` endpoint is compatible with the documented [evcc HTTP plugin](https://docs.evcc.io/en/reference/plugins/#http). A proposed vehicle provider fragment is below, **not an instruction to insert it into the running configuration**:

```yaml
soc:
  source: http
  uri: http://127.0.0.1:7081/v1/abrp/soc
  timeout: 5s
```

After a port-7080 route is actually implemented and tested, its equivalent URI can replace 7081. Host-loopback works only when evcc shares the host network namespace. A returned 503 is an error, not 0% or the last SoC. However, evcc may cache/estimate SoC, and supplying new SoC to an active loadpoint can affect charging decisions even when the adapter is read-only. Consequently this change does **not** attach the source to any loadpoint, restart evcc or enable SoC-based automation. Integration into live charging needs separate review of the installed evcc version, caching/estimation and fallback behavior. The current test suite verifies the scalar HTTP contract, not a live evcc instance.

## Parallel official OAuth2 access request

ABRP's [official Iternio APIs support page](https://abrp.featurebase.app/help/articles/1764088-iternio-apis) directs developers to **contact@iternio.com** to set up OAuth2 with an API key, application name and redirect URL. Request application name **Smart EV AI** and only the **`get_telemetry`** scope. Ask them to confirm that existing Premium/Enode Audi readings are exposed, including the SoC-specific measurement timestamp, supported polling limits, client type/PKCE requirements, token lifecycle and revocation.

Ask whether your existing telemetry-only key can be enabled for reading or whether a new client is required. Do not assume Premium or a telemetry-upload key automatically grants this access. Identify the key via a non-secret identifier first and ask for a secure submission channel if needed; never paste secrets into this chat or the repository.

Propose a loopback callback such as `http://127.0.0.1:7082/callback` **for discussion only**, asking whether it is supported. The official callback is not implemented in this adapter; do not register the earlier suggested port-7080 `/callback` as if it exists. If a loopback callback is approved, account for the browser running on a laptop versus the Pi and implement a dedicated listener/SSH tunnel, state checks and PKCE as required. Otherwise agree an owned HTTPS callback. Do not repurpose the healthy connector's port.

The published support page describes authorization at `/oauth/auth`, an `auth_code` callback parameter and token retrieval at `api.iternio.com/1/oauth/token`, and states that `get_telemetry` permits reading latest telemetry. These are distinct from the private accounts-service flow used here. Obtain current endpoint/schema and secure token-exchange guidance from Iternio before implementing the official provider; do not assume the two tokens or response shapes are interchangeable. No access-request email has been sent by this change.

## Tests and limits

Run `python3 -m unittest discover -s backend -p 'test_*.py' -v`. Tests use synthetic payloads only. They cover SoC boundaries, missing/future timestamps, stale data despite fresh unrelated fields, aging without polling, clock rollback, vehicle selection, Enode provenance, regressions, errors/recovery, PKCE/state checks, secret-redacted failures, token rotation, and real local HTTP reads/write rejection. Linux ownership/flock and systemd hardening need verification on the Pi; the development tests ran on Windows/Python 3.14. No authenticated fixture from the user's vehicle has been collected.
