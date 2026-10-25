'use strict';
let password = '';
let timer;
const el = id => document.getElementById(id);
async function request(path, body) {
  const response = await fetch(path, {method: body ? 'POST' : 'GET', cache: 'no-store',
    headers: {'X-Setup-Password': password, ...(body ? {'Content-Type': 'application/json'} : {})},
    ...(body ? {body: JSON.stringify(body)} : {})});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}
async function refresh() {
  const data = await request('/api/setup/status');
  el('details').hidden = false;
  el('evcc').textContent = data.evcc.verified_evcc ? 'evcc connected Â· read-only access verified' : 'evcc unavailable Â· check the local evcc service and address';
  el('status').textContent = data.paired ? `Paired Â· cloud ${data.cloud_status}` : `Not paired Â· ${data.cloud_status.replaceAll('_', ' ')}`;
  el('pair').hidden = data.paired;
  if (data.cloud_url) el('cloud').value = data.cloud_url;
}
el('unlock').addEventListener('submit', async event => {
  event.preventDefault(); password = el('password').value; el('password').value = '';
  clearInterval(timer);
  try { await refresh(); el('message').textContent = ''; timer = setInterval(() => refresh().catch(() => {el('message').textContent = 'Connection lost. Unlock again to retry.';}), 10000); }
  catch (error) { password = ''; el('details').hidden = true; el('message').textContent = error.message; }
});
el('pair').addEventListener('submit', async event => {
  event.preventDefault(); el('submit').disabled = true;
  const body = {cloud_url: el('cloud').value.trim(), pairing_code: el('code').value.trim()};
  el('code').value = '';
  try { await request('/api/setup/pair', body); el('message').textContent = ''; await refresh(); }
  catch (error) { el('message').textContent = error.message; }
  finally { el('submit').disabled = false; }
});
