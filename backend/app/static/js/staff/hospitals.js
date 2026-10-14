/**
 * ============================================================
 * SahayAI Staff Hospitals Controller
 * ============================================================
 */

let hospitalsCache = [];

document.addEventListener('DOMContentLoaded', async () => {
  const user = await Auth.requireAuth();
  if (!user) return;

  Auth.renderStaffNav('hospitals');

  document.getElementById('filterTraumaOnly')?.addEventListener('change', filterAndRenderHospitals);
  document.getElementById('filterCardiacOnly')?.addEventListener('change', filterAndRenderHospitals);
  document.getElementById('filterBurnOnly')?.addEventListener('change', filterAndRenderHospitals);
  document.getElementById('btnRefreshHospitals')?.addEventListener('click', loadHospitals);

  await loadHospitals();
});

async function loadHospitals() {
  const grid = document.getElementById('hospitalsGrid');
  grid.innerHTML = `<div style="grid-column:1/-1; text-align:center; padding:40px;"><span class="spinner"></span><div style="margin-top:8px; color:var(--text-muted);">Fetching partner hospitals and bed availability…</div></div>`;

  try {
    hospitalsCache = await window.api.listHospitals({ active_only: true });
    filterAndRenderHospitals();
  } catch (err) {
    grid.innerHTML = `<div style="grid-column:1/-1;">${Utils.renderErrorState('Failed to load hospitals: ' + err.message, 'loadHospitals()')}</div>`;
  }
}

function filterAndRenderHospitals() {
  const grid = document.getElementById('hospitalsGrid');
  const traumaOnly = document.getElementById('filterTraumaOnly')?.checked;
  const cardiacOnly = document.getElementById('filterCardiacOnly')?.checked;
  const burnOnly = document.getElementById('filterBurnOnly')?.checked;

  let list = hospitalsCache;

  if (traumaOnly) list = list.filter(h => h.has_trauma_center);
  if (cardiacOnly) list = list.filter(h => h.has_cardiac_care);
  if (burnOnly) list = list.filter(h => h.has_burn_unit);

  const totalAvailBeds = hospitalsCache.reduce((sum, h) => sum + (h.available_beds || 0), 0);
  const totalICUBeds = hospitalsCache.reduce((sum, h) => sum + (h.available_icu_beds || 0), 0);
  document.getElementById('hospitalStatsLabel').textContent = `${totalAvailBeds} Total Available Beds (${totalICUBeds} ICU) across ${hospitalsCache.length} Hospitals`;

  if (!list.length) {
    grid.innerHTML = `<div style="grid-column:1/-1;">${Utils.renderEmptyState('No hospitals match the selected specialty filters.', '🏥')}</div>`;
    return;
  }

  grid.innerHTML = list.map(h => `
    <div class="card" style="border-left:4px solid var(--accent-blue); display:flex; flex-direction:column; gap:12px;">
      <div style="display:flex; justify-content:space-between; align-items:flex-start;">
        <div>
          <div style="font-size:1.15rem; font-weight:800; color:var(--text-primary);">${Utils.escapeHtml(h.name)}</div>
          <div style="font-size:0.82rem; color:var(--text-secondary); margin-top:2px;">📍 ${Utils.escapeHtml(h.address)}</div>
        </div>
      </div>

      <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; background:#090e1b; border:1px solid var(--border-color); border-radius:var(--radius-md); padding:10px 14px;">
        <div>
          <div style="font-size:0.72rem; color:var(--text-muted); text-transform:uppercase;">General Beds</div>
          <div style="font-size:1.2rem; font-weight:800; color:var(--accent-emerald);">${h.available_beds} <span style="font-size:0.75rem; color:var(--text-secondary);">/ ${h.total_beds}</span></div>
        </div>
        <div>
          <div style="font-size:0.72rem; color:var(--text-muted); text-transform:uppercase;">ICU Beds</div>
          <div style="font-size:1.2rem; font-weight:800; color:var(--accent-cyan);">${h.available_icu_beds}</div>
        </div>
      </div>

      <!-- Clinical Capabilities Tags -->
      <div>
        <div style="font-size:0.72rem; color:var(--text-muted); text-transform:uppercase; font-weight:700; margin-bottom:6px;">Emergency Capabilities</div>
        <div style="display:flex; flex-wrap:wrap; gap:4px;">
          ${h.has_trauma_center ? '<span class="badge" style="background:rgba(239,68,68,0.15); color:#fca5a5; border:1px solid rgba(239,68,68,0.3);">🚨 Trauma Center</span>' : ''}
          ${h.has_cardiac_care ? '<span class="badge" style="background:rgba(59,130,246,0.15); color:#93c5fd; border:1px solid rgba(59,130,246,0.3);">🫀 Cardiac Care</span>' : ''}
          ${h.has_burn_unit ? '<span class="badge" style="background:rgba(245,158,11,0.15); color:#fde047; border:1px solid rgba(245,158,11,0.3);">🔥 Burn Unit</span>' : ''}
          ${h.has_pediatric_icu ? '<span class="badge" style="background:rgba(16,185,129,0.15); color:#86efac; border:1px solid rgba(16,185,129,0.3);">👶 Pediatric ICU</span>' : ''}
        </div>
      </div>

      <div style="margin-top:auto; padding-top:10px; border-top:1px solid rgba(255,255,255,0.06); display:flex; justify-content:space-between; align-items:center;">
        <span style="font-size:0.78rem; color:var(--text-muted);">Coordinates: ${h.latitude.toFixed(4)}, ${h.longitude.toFixed(4)}</span>
        <a href="tel:${h.contact_phone}" class="btn btn-outline btn-sm" style="color:var(--accent-blue); border-color:var(--accent-blue);">
          📞 ${h.contact_phone}
        </a>
      </div>
    </div>
  `).join('');
}
