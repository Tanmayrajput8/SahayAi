/**
 * ============================================================
 * SahayAI Staff Ambulance Fleet Controller
 * ============================================================
 */

let ambulancesCache = [];

document.addEventListener('DOMContentLoaded', async () => {
  const user = await Auth.requireAuth();
  if (!user) return;

  Auth.renderStaffNav('ambulances');

  document.getElementById('filterAmbType')?.addEventListener('change', filterAndRenderAmbulances);
  document.getElementById('filterAmbStatus')?.addEventListener('change', filterAndRenderAmbulances);
  document.getElementById('btnRefreshAmbulances')?.addEventListener('click', loadAmbulances);

  await loadAmbulances();
});

async function loadAmbulances() {
  const grid = document.getElementById('ambulancesGrid');
  grid.innerHTML = `<div style="grid-column:1/-1; text-align:center; padding:40px;"><span class="spinner"></span><div style="margin-top:8px; color:var(--text-muted);">Querying live Pune ambulance fleet…</div></div>`;

  try {
    ambulancesCache = await window.api.listAmbulances();
    filterAndRenderAmbulances();
  } catch (err) {
    grid.innerHTML = `<div style="grid-column:1/-1;">${Utils.renderErrorState('Failed to load fleet: ' + err.message, 'loadAmbulances()')}</div>`;
  }
}

function filterAndRenderAmbulances() {
  const grid = document.getElementById('ambulancesGrid');
  const typeFilter = document.getElementById('filterAmbType')?.value || '';
  const statusFilter = document.getElementById('filterAmbStatus')?.value || '';

  let list = ambulancesCache;

  if (typeFilter) {
    list = list.filter(a => a.ambulance_type === typeFilter);
  }

  if (statusFilter) {
    list = list.filter(a => a.status === statusFilter);
  }

  const availableCount = ambulancesCache.filter(a => a.status === 'AVAILABLE').length;
  document.getElementById('fleetStatsLabel').textContent = `${availableCount} Available of ${ambulancesCache.length} Total Units`;

  if (!list.length) {
    grid.innerHTML = `<div style="grid-column:1/-1;">${Utils.renderEmptyState('No ambulances match the selected filters.', '🚑')}</div>`;
    return;
  }

  grid.innerHTML = list.map(a => {
    const isAvail = a.status === 'AVAILABLE';
    const isDispatched = a.status === 'DISPATCHED' || a.status === 'ASSIGNED';
    let statusClass = 'badge-pending';
    if (isAvail) statusClass = 'badge-low';
    else if (isDispatched) statusClass = 'badge-critical';

    return `
      <div class="card" style="border-left:4px solid ${isAvail ? 'var(--accent-emerald)' : isDispatched ? 'var(--accent-red)' : 'var(--accent-amber)'}; display:flex; flex-direction:column; gap:12px;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
          <div>
            <div style="font-size:1.15rem; font-weight:800; font-family:var(--font-mono); color:var(--text-primary);">${Utils.escapeHtml(a.vehicle_number)}</div>
            <div style="font-size:0.8rem; color:var(--accent-cyan); font-weight:700;">${a.ambulance_type === 'ALS' ? '🚑 Advanced Life Support (ALS)' : '🚐 Basic Life Support (BLS)'}</div>
          </div>
          <span class="badge ${statusClass}">${Utils.escapeHtml(a.status)}</span>
        </div>

        <div style="font-size:0.82rem; color:var(--text-secondary); display:flex; flex-direction:column; gap:4px;">
          <div>Base Station: <strong>${Utils.escapeHtml(a.base_station)}</strong></div>
          <div>Driver: <strong>${Utils.escapeHtml(a.driver_name)}</strong> (<a href="tel:${a.contact_number}">${a.contact_number}</a>)</div>
          <div>Location: <strong>${a.latitude.toFixed(4)}, ${a.longitude.toFixed(4)}</strong></div>
          ${a.assigned_case_id ? `
            <div style="margin-top:4px;">
              Assigned Case: <a href="/staff/cases/${encodeURIComponent(a.assigned_case_id)}" style="font-family:var(--font-mono); font-weight:700;">${a.assigned_case_id.substring(0,8)}…</a>
            </div>
          ` : ''}
        </div>

        ${a.equipment && a.equipment.length ? `
          <div style="margin-top:auto; padding-top:10px; border-top:1px solid rgba(255,255,255,0.06);">
            <div style="font-size:0.72rem; color:var(--text-muted); text-transform:uppercase; font-weight:700; margin-bottom:4px;">Onboard Equipment</div>
            <div style="display:flex; flex-wrap:wrap; gap:4px;">
              ${a.equipment.map(eq => `<span class="badge" style="background:#090e1b; color:#94a3b8; font-size:0.68rem; text-transform:none;">${Utils.escapeHtml(eq)}</span>`).join('')}
            </div>
          </div>
        ` : ''}
      </div>
    `;
  }).join('');
}
