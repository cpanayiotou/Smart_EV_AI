'use strict';
const el = id => document.getElementById(id);
async function request(path, body) {
  const response = await fetch(path, {method: body ? 'POST' : 'GET', cache: 'no-store',
    headers: body ? {'Content-Type': 'application/json'} : {},
    ...(body ? {body: JSON.stringify(body)} : {})});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}
async function refresh() {
  const data = await request('/api/setup/status');
  el('details').hidden = false;
  document.querySelector('.tag').textContent = data.control_capable ? 'SMART EV AI - MANUAL CONTROL CAPABLE' : 'SMART EV AI - READ ONLY';
  el('evcc').textContent = data.evcc.verified_evcc ? (data.control_capable ? 'evcc connected - manual controls require cloud authorization' : 'evcc connected - read-only access verified') : 'evcc unavailable  -  check the local evcc service and address';
  el('status').textContent = data.paired ? `Paired  -  cloud ${data.cloud_status}` : `Not paired  -  ${data.cloud_status.replaceAll('_', ' ')}`;
  el('pair').hidden = data.paired;
  el('message').textContent = data.last_error ? data.last_error.error : '';
  if (data.cloud_url) el('cloud').value = data.cloud_url;
}
async function updateStatus() {
  try {
    const telemetry = await request('/v1/abrp/fields');
    const rows = Object.entries(telemetry.fields).sort(([a], [b]) => a.localeCompare(b)).map(([name, field]) => {
      const row = document.createElement('tr');
      const age = field.age_seconds == null ? 'Unknown' : `${Math.floor(field.age_seconds / 60)} min`;
      const value = field.last_known_value == null ? 'Not reported' : `${field.last_known_value} ${field.unit || ''}`;
      const status = field.available ? 'Available' : field.stale ? 'Older than 24 hours' : 'Unverified';
      for (const text of [name, value, age, field.provider || 'Unknown', status]) {
        const cell = document.createElement('td');
        cell.textContent = text;
        row.appendChild(cell);
      }
      return row;
    });
    el('telemetry-fields').replaceChildren(...rows);
    el('telemetry-status').textContent = `${rows.length} reported fields. ` +
      (telemetry.omitted_fields.length ? `Unsupported fields: ${telemetry.omitted_fields.join(', ')}.` : 'Missing fields are not supplied by ABRP.');
  } catch (_) {
    el('telemetry-fields').replaceChildren();
    el('telemetry-status').textContent = 'Vehicle telemetry unavailable.';
  }
  try {
    const battery = await request('/v1/abrp/display');
    const minutes = Math.floor(battery.age_seconds / 60);
    const age = minutes < 1 ? 'less than a minute ago' : `${minutes} minutes ago`;
    el('abrp').textContent = `${battery.last_known_soc_percent}% - measured ${age}. ` +
      (battery.stale ? 'Stale: last-known reading only; unavailable for charging decisions.' : 'Fresh reading.');
  } catch (_) {
    el('abrp').textContent = 'Battery reading unavailable.';
  }
  try { await refresh(); }
  catch (error) { el('message').textContent = error.message; }
}
updateStatus();
setInterval(updateStatus, 10000);
el('pair').addEventListener('submit', async event => {
  event.preventDefault(); el('submit').disabled = true;
  const body = {cloud_url: el('cloud').value.trim(), pairing_code: el('code').value.trim()};
  el('code').value = '';
  try { await request('/api/setup/pair', body); el('message').textContent = ''; await refresh(); }
  catch (error) { el('message').textContent = error.message; }
  finally { el('submit').disabled = false; }
});
