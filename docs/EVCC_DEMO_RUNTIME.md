# Upstream evcc demo runtime

This stack runs the real upstream evcc container with **demo-only** meter, charger and offline vehicle templates.

- UI: port 7070
- AI API reads evcc at `http://evcc:7070`.
- `EVCC_WRITE_ENABLED=false` remains the hard development default.
- The demo charger has 6–16 A limits and advertises 1P/3P switching.
- No Peblar, Huawei, Audi account, Modbus address, sponsor token, or physical-device credential exists in this configuration.
- Demo meter values are fixed by evcc's official demo templates. This validates the software contract, not physical energy behaviour.
- Real hardware must be commissioned separately and only after telemetry/sign/phase checks.

Official evcc docs explicitly provide demo charger/meter templates for demonstration and recommend replacing demo devices with real devices after validation.
