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
