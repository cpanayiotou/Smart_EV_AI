# Audi data bridge for Raspberry Pi

Data route: Audi cloud → this Pi service → evcc custom vehicle → existing Smart EV connector → cloud telemetry.

This is a separate service. Its only Audi vehicle operation is reading stored status. It does not call lock, climate, charging or wake-up commands. It does not edit evcc or the existing connector. Compatibility with your account and e-tron must be proved on the Pi; an image build or mock test cannot prove Audi login works.

The Audi client is pinned to [John6810/myaudi-api commit afd531e](https://github.com/John6810/myaudi-api/tree/afd531e830971f042f1c0319d3614442c05009d4). The upstream server (which exposes vehicle actions) is not used. Its MIT license is included in the image. Python dependencies have bounded version ranges and are resolved at build time.

## 1. Build and approve access

Run in this directory on the Raspberry Pi, from a checkout containing this change:

```sh
sudo docker compose build audi-bridge
sudo docker compose run --rm audi-bridge configure
sudo docker compose run --rm audi-bridge probe
```

Enter the country for your Audi account. For European accounts, the client uses browser approval; open the printed Audi link privately and sign in there. The bridge does not request an Audi password for this flow. Other supported regions may prompt for credentials privately in the terminal. Select a VIN when the account has more than one car. Never paste passwords, approval links/codes or the token/config files into a chat or GitHub issue.

`configure` saves settings and removes any previous account's tokens. Run it only for initial setup or to change accounts. `probe` waits up to 15 minutes for approval, reads battery level once and exits. Exit 0 means a valid reading captured within one hour; exit 2 means Audi responded but its reading is stale. Exit 1 means authentication, storage or data parsing failed. Diagnostics intentionally omit raw upstream errors because they can contain account details. No successful probe has yet been performed against the user's car.

Tokens and settings live in the named `smart-ev-audi_audi-data` volume, owned by the non-root service user. Writes are atomic with owner-only permissions. Keep that volume when rebuilding; never run `down -v`. Only one bridge/probe may use the volume at once. To re-approve later, stop the service, run `probe`, then start it again.

## 2. Start and verify the local service

After a successful probe:

```sh
sudo docker compose up -d audi-bridge
curl --max-time 5 -i http://127.0.0.1:7081/vehicle
sudo docker compose ps
```

Initial requests may return 503 while the first read completes. It polls every 30 minutes, independently of evcc requests. Audi account limits may still apply. The listener is deliberately loopback-only because evcc is on the same Pi with host networking. No router port forwarding or LAN listener is needed. `unless-stopped` restarts the service after reboot, provided Docker starts at boot.

Endpoints:

* `/health`: process liveness only; healthy does **not** mean Audi data is fresh.
* `/soc`: numeric percent, including valid zero; 503 when missing/stale.
* `/range`: optional electric range in km with its own freshness check.
* `/vehicle`: SoC, original Audi capture timestamp (Unix seconds), age and source; optional range and its capture timestamp. No VIN or tokens.

A source capture time older than one hour, more than 60 seconds ahead, missing or timezone-free is unavailable. A failed poll invalidates the cached reading. Fetching old Audi data again does not renew its age. A sleeping car may legitimately have stale data; the service does not wake it or invent a reading.

## 3. Connect evcc after the probe passes

Use `evcc.vehicle.example.yaml` as a fragment for your existing configuration, following [evcc custom devices](https://docs.evcc.io/en/user-defined-devices/) and its [HTTP plugin](https://docs.evcc.io/en/reference/plugins/#http). Confirm the actual active evcc configuration/mount before editing. Back up that file and evcc's database. Do not replace your full configuration with the fragment or create a second `vehicles:` key.

First test the fragment separately using the **same image as your running evcc**. This command only queries the custom vehicle; it does not alter the running instance or use its database:

```sh
EVCC_IMAGE=$(sudo docker inspect --format '{{.Image}}' smart-ev-ai-evcc)
sudo docker run --rm --network host \
  -v "$PWD/evcc.vehicle.example.yaml:/etc/evcc.yaml:ro" \
  "$EVCC_IMAGE" --ignore-db vehicle audi_bridge --timeout 5s
```

Expected output includes SoC matching `/soc`. Confirm usable battery capacity before adding `capacity`. Enable optional range only when `/range` succeeds. Then add this vehicle to the existing configuration, replacing the failed Audi provider rather than leaving both polling the account. Associate `audi_bridge` with the existing loadpoint, validate the configuration using the installed evcc version, and restart evcc during a suitable maintenance window. Preserve all charger, meter and charging-mode settings. This bridge does not itself turn charging on or off.

The current deployment configuration has not been inspected as part of this change, so no automated configuration rewrite is supplied. Rollback: restore the backed-up evcc configuration, restart evcc, then `sudo docker compose stop audi-bridge` in this directory. Keep the token volume for later testing.

## Cloud/AI completion gate

The existing connector can forward evcc's `vehicleSoc` once the vehicle is assigned. This does **not** by itself complete the cloud battery cockpit or AI planner integration: they must prefer verified vehicle readings over manual input and preserve freshness. evcc may retain its last SoC after a provider error; its telemetry receipt time is not the Audi capture time. Before using this source for automated AI decisions, carry `/vehicle`'s source timestamp and unavailable status through connector telemetry and cloud storage, and reject stale readings there. This first change supplies the Pi→evcc service and connection test, not that cloud freshness contract or autonomous charging.

## Development checks

```sh
python -m unittest discover -s audi_bridge -v
```

Run from the repository root. Tests cover parsing, original timestamps, stale/future values, failed reads, multiple vehicles, local HTTP restrictions and absence of action routes. CI additionally builds the container, checks client imports and queries a synthetic reading with actual evcc. No tests use an Audi account or a physical charger.
