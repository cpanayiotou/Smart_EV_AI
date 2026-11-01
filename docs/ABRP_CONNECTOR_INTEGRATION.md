# ABRP read-only routes on the existing connector

## Last-known battery display

The connector now exposes `/v1/abrp/display` and shows a battery panel on its local setup page. Valid older Enode SoC is labelled **Stale**, with its measurement age. The display field is `last_known_soc_percent`; stale data retains `soc_percent: null` and `available: false`. `/v1/abrp/soc` continues to return HTTP 503 for stale readings. No charging behavior changes. The guided installer accepts valid display data, including stale readings, and can upgrade the original pinned adapter while preserving local authorization. This supersedes the fresh-only installation requirements below.

This change targets `local-connector-readonly` at `8b7adc5c77ac91be56061d028b6be052b45f7b9d`, where the running connector's source lives. `main` remains a scaffold. It complements the isolated ABRP adapter in [PR #8](https://github.com/cpanayiotou/Smart_EV_AI/pull/8); neither PR needs to be merged to test a review branch.

## Observed Pi state — 2026-11-01

- `smart-ev-ai.local` resolved intermittently to `10.1.1.71` on this LAN.
- Port 7080 responded as `SmartEVConnector/0.1`, Python 3.12.16.
- GET `/health` reported `status: running`, `read_only: false`, `control_capable: true`. These are existing manual-control settings; this change does not modify them.
- evcc on port 7070 responded HTTP 200. Port 80 did not respond.
- SSH as `smartai` reached the Pi but existing local keys were rejected. No password was requested, no remote commands ran, and nothing was deployed.

## What changes

With `CONNECTOR_ABRP_READONLY=true`, the existing connector exposes:

- GET `/v1/abrp/telemetry`: normalized JSON from the loopback sidecar, revalidated for freshness and schema.
- GET `/v1/abrp/soc`: plain numeric SoC only while valid.

Both request only `http://127.0.0.1:7081/v1/abrp/telemetry` using GET, without system proxies or redirects, a five-second timeout and a 16 KiB response limit. They never send credentials. Responses are uncached. Disabled, absent, stale, invalid, redirected or failing upstream data becomes HTTP 503 with null SoC. Arbitrary upstream fields, errors and credentials are not forwarded. The connector enforces a maximum freshness window of 900 seconds independently of the sidecar. The sidecar's configured age must be between 60 and 900 seconds for connector use.

The setup server's existing LAN client, Host and same-origin checks still apply. Requests cannot select an upstream URL or force a vehicle refresh. Existing evcc reads, cloud pairing and manual-control dispatch are unchanged. This does not publish ABRP into the cloud protocol or assign an evcc vehicle/loadpoint. The existing host-network Docker configuration permits access to the sidecar's loopback address.

## Deployment sequence

### Guided installer

`deploy/install_abrp.py` automates the steps below when run with `sudo python3` in the Pi's own interactive SSH terminal. It downloads the two reviewed source commits pinned inside the script, checks that the existing Compose configuration hash matches the running host-network connector, preserves its project/volumes/manual-control settings, runs the 37 connector and 17 adapter tests on the Pi, and builds before touching the running connector.

It then guides local ABRP approval and vehicle selection. It requires a fresh Enode reading before recreating only the connector. A failed connector verification triggers an attempt to restore the old tagged image using the original Compose settings. No evcc restart or charging command is performed. Six offline installer tests cover preflight, narrow overrides and rollback behavior. The installer has not been executed against the live Pi by the assistant.

Keep `/opt/smart-ev-abrp-release-<timestamp>` after installation: it contains the source, Compose override and root-only `apply-connector.sh` and `rollback-connector.sh` launchers. Use those launchers for subsequent recreation instead of running an older Compose command that omits the new override. The script prints their exact paths. Docker's restart policy retains the deployed configuration across reboot.

If the Compose hash differs, installation stops without modifying the container; resolve the original deployment configuration first. If ABRP approval or fresh telemetry is unavailable, the existing connector remains running; the isolated adapter may have been installed and can be diagnosed locally before rerunning. No secrets are printed beyond the short-lived approval link intended only for your local terminal. Do not share that link or the credential files.

### Manual alternative

1. Install and locally authorize the sidecar using [PR #8's deployment guide](https://github.com/cpanayiotou/Smart_EV_AI/blob/codex/abrp-read-only/docs/ABRP_DEPLOYMENT.md). Validate its fresh/expired SoC directly on port 7081 first.
2. Establish SSH locally as `smartai@smart-ev-ai.local` (or `smartai@10.1.1.71` if that address still belongs to this Pi). Use an existing key or type the password only into your own SSH terminal. Never send it in chat. Installing a public key is a separate local account action; this change does not create one or modify SSH settings.
3. Use the existing connector deployment checkout, documented upstream as `~/smart-ev-ai/connector-source`. Verify that it is actually the deployed checkout and that its Compose settings reproduce the existing container before recreating anything. Do not use the repository-root Compose stack.

Preparation in your Pi terminal:

```bash
cd ~/smart-ev-ai/connector-source
git status --short
git fetch origin local-connector-readonly codex/abrp-connector
git diff --exit-code origin/local-connector-readonly HEAD -- local_connector
docker inspect --format '{{.Image}}' smart-ev-connector
docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' smart-ev-connector
docker inspect --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' smart-ev-connector
curl --max-time 5 -fsS http://127.0.0.1:7080/health
curl --max-time 5 -fsS http://127.0.0.1:7081/v1/abrp/telemetry
```

Stop if tracked files have local changes, the connector diff is nonempty, the Compose working directory differs, or the sidecar is unavailable. Review any deployed differences before replacing code. Do not dump container environment variables, pairing volumes or tokens into chat.

Save the current image for rollback and record the current branch and Compose project name locally:

```bash
umask 077
BACKUP_DIR="$HOME/smart-ev-abrp-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -m 700 "$BACKUP_DIR"
git rev-parse HEAD > "$BACKUP_DIR/connector-commit"
docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' smart-ev-connector > "$BACKUP_DIR/project"
ROLLBACK_IMAGE="smart-ev-connector:before-abrp-$(date +%Y%m%d-%H%M%S)"
docker image tag "$(docker inspect --format '{{.Image}}' smart-ev-connector)" "$ROLLBACK_IMAGE"
printf '%s\n' "$ROLLBACK_IMAGE" > "$BACKUP_DIR/image"
test ! -f local_connector/.env || cp -p local_connector/.env "$BACKUP_DIR/connector.env"
cp -p local_connector/compose.example.yml "$BACKUP_DIR/compose.yml"
git switch --create review-abrp-connector origin/codex/abrp-connector
python3 -m unittest discover -s local_connector -v
cd local_connector
docker compose -f compose.example.yml build smart-ev-connector
```

The backup may contain local settings; keep it private. Building does not restart services. Before recreation, verify all current deployment settings, particularly `CONNECTOR_ALLOW_CONTROL`, `CONNECTOR_HOST`, network mode, volume name and Compose project. Keep the currently enabled manual-control value and existing paired volume exactly as deployed. If these settings are not already reproducible from this Compose file plus the existing local environment, stop and inspect the actual deployment first.

For a matching deployment, use the recorded Compose project and enable only the new read route:

```bash
PROJECT_NAME="$(cat "$BACKUP_DIR/project")"
test -n "$PROJECT_NAME" || exit 1
CONNECTOR_ABRP_READONLY=true docker compose -p "$PROJECT_NAME" -f compose.example.yml up -d --no-deps smart-ev-connector
curl --max-time 5 -fsS http://127.0.0.1:7080/health
curl --max-time 5 -i http://127.0.0.1:7080/v1/abrp/telemetry
curl --max-time 5 -i http://127.0.0.1:7080/v1/abrp/soc
curl --max-time 5 -sS -o /dev/null -w 'evcc HTTP %{http_code}\n' http://127.0.0.1:7070/
```

Only the connector is recreated, which briefly interrupts its UI/cloud polling. No evcc/Peblar restart is involved. Confirm `/health` still reports the same manual-control flags as before. Validate fresh SoC, unavailable/stale behavior and existing evcc reads. Once accepted, add `CONNECTOR_ABRP_READONLY=true` to the existing `local_connector/.env` without changing other settings so future recreations retain it. Do not enable charging automation or connect this source to a live evcc loadpoint as part of these checks.

## Rollback

For a quick reversible disable, recreate only the connector with `CONNECTOR_ABRP_READONLY=false`, retaining the same Compose project and all original settings. The API will return 503 and the independent sidecar can remain running.

To restore the previous image, create a small override and recreate only the connector, preserving the existing data volume and original settings:

```bash
ROLLBACK_IMAGE="$(cat "$BACKUP_DIR/image")"
printf 'services:\n  smart-ev-connector:\n    image: %s\n' "$ROLLBACK_IMAGE" > "$BACKUP_DIR/rollback.yml"
CONNECTOR_ABRP_READONLY=false docker compose -p "$PROJECT_NAME" \
  -f compose.example.yml -f "$BACKUP_DIR/rollback.yml" up -d --no-deps --no-build smart-ev-connector
```

Do not run `docker compose down`, remove pairing volumes, change manual-control permissions, or restart evcc. Keep the backup path and original source commit for subsequent source restoration. Adapter retirement separately uses `sudo systemctl disable --now smart-ev-abrp`.

## Tests and outstanding validation

Run `python3 -m unittest discover -s local_connector -v` (on Windows use `python -X utf8 -m unittest discover -s local_connector -v`). The new tests run a local HTTP sidecar fixture and the real connector setup handler, verifying both routes, disabled mode, no stale-cache reuse, failure redaction, freshness validation, Host/Origin protections, method restrictions and independent evcc behavior. Existing pairing/manual-control tests use mocks; no hardware commands are issued.

The deployed image/source revision, Linux runtime, live Enode response and local authorization still need Pi-side verification. The web health check alone cannot establish the exact deployed Git commit. No deployment or charging actuation has been performed.
