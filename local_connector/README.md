# Smart EV local setup (Raspberry Pi / Linux)

This connector reads the existing evcc installation at `http://127.0.0.1:7070`.
It does not configure Huawei/Peblar, change charging, or start/stop evcc.

## Safe deployment

Use only the Compose file in **local_connector/**. The repository-root Compose
file is a different stack and must not be used on the running installation.
Save the current connector image ID and deployment settings for rollback first.
From `~/smart-ev-ai/connector-source`:

```sh
git fetch origin local-connector-readonly
git switch local-connector-readonly
git pull --ff-only origin local-connector-readonly
cd local_connector
docker compose -f compose.example.yml build smart-ev-connector
docker compose -f compose.example.yml up -d --no-deps smart-ev-connector
```

Resolve any existing connector container-name conflict by stopping/removing only
the old **smart-ev-connector** container after recording its settings. Never use
`docker compose down` on the main stack. No evcc restart is needed.

The connector listens on `0.0.0.0:7080` by default. Open
`http://smart-ev-ai.local:7080/` (when mDNS is available) or
`http://PI_LAN_IP:7080/`. `/setup` opens the same wizard. There is no local setup
password or Raspberry Pi account login. Anyone on the reachable trusted LAN can
view status and pair an unpaired connector. Use only on a trusted network; do not
forward port 7080 to the internet. HTTP is not encrypted.

Private/loopback client checks, numeric LAN or `.local` Host validation, and
same-origin protection remain enabled. Charging commands remain disabled.
Set `CONNECTOR_HOST` in `local_connector/.env` to a specific private IP to limit
the listening interface, or to `127.0.0.1` for SSH tunnelling.

Check evcc health, enter the exact HTTPS cloud API origin (no path or query),
then enter a freshly generated one-time pairing code. Cloud URLs use port 443.
Existing pairing data is preserved across this upgrade.

## Persistence and status

The named `connector-data` volume stores `connector.json`. Legacy `setup-password` files are ignored.
Files use Linux mode 0600, directory 0700, owned by UID 10001. Writes are atomic
and fsynced before polling starts. The container runs unprivileged with a read-only
root filesystem. Keep the volume across rebuilds; never use `down -v`. Protect
host access and encrypt backups: the token is protected by filesystem permissions,
not encrypted against the host administrator. Never commit or share the volume.

The pairing code is not persisted. The token is never returned by the UI or
logged. Pairing is locked after success; stored credentials are tied to their
cloud origin. On restart the connector resumes polling from the volume.
Legacy pairing/token environment variables are no longer consumed by cloud_main;
existing installations must pair once through the wizard using a fresh code.

`/health` reports only local service liveness. `/api/setup/status`
reports evcc health, pairing and cloud polling separately. "Paired" means a token
was securely saved; "online" means a work request succeeded, not that every cloud
result was accepted. Cloud failures retry; a revoked token needs a local reset.

## Reset / rollback

Revoke the connector in the cloud first. Stop only the connector, make a protected
backup of its volume, then remove only `/data/connector.json` using a temporary
container mounting the same volume. Restart and use a fresh pairing code. Do not delete
the entire volume or any evcc files. If pairing succeeded remotely but disk saving
failed, revoke that orphaned connector and request a fresh code before retrying.

For rollback, stop only the connector and restore the previously recorded image
and deployment settings. Keep its data backup. Older versions cannot read the new
credential store and may require their previous secret provisioning process.

## Protocol verification and tests

See [cloud-api-contract.md](cloud-api-contract.md). This branch contains no cloud
pairing server implementation; compatibility is based on the existing v0.2 client
and its tests, not a live cloud test. No real pairing or evcc access is performed
by the tests:

```sh
python -m unittest discover -s local_connector -v
```

Run this from the repository root. Linux CI also checks real POSIX file modes.
The tests cover password-free access, hostile Host/Origin, pairing and restart,
redaction, storage failure, redirects, retry throttling and read-only allowlists.
