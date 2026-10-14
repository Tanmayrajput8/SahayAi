/**
 * ============================================================
 * SahayAI Staff Geospatial Fleet & Emergency Map Controller
 * ============================================================
 */

let staffMapInstance = null;
let currentFocusedCaseId = null;
let activeCasesCache = [];
let ambulancesCache = [];
let hospitalsCache = [];

document.addEventListener('DOMContentLoaded', async () => {
  const user = await Auth.requireAuth();
  if (!user) return;

  Auth.renderStaffNav('map');

  initStaffMap();

  const urlParams = new URLSearchParams(window.location.search);
  currentFocusedCaseId = urlParams.get('focus') || urlParams.get('case_id') || null;

  document.getElementById('selectFocusCase')?.addEventListener('change', e => {
    currentFocusedCaseId = e.target.value || null;
    renderMapLayers();
  });

  document.getElementById('btnRefreshMap')?.addEventListener('click', loadMapData);

  await loadMapData();
});

function initStaffMap() {
  if (staffMapInstance) return;

  staffMapInstance = L.map('staffMapViewport').setView([18.5204, 73.8567], 12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap contributors',
  }).addTo(staffMapInstance);
}

async function loadMapData() {
  try {
    const [cases, ambulances, hospitals] = await Promise.all([
      window.api.listCases({ limit: 50 }).catch(() => []),
      window.api.listAmbulances().catch(() => []),
      window.api.listHospitals().catch(() => []),
    ]);

    activeCasesCache = cases;
    ambulancesCache = ambulances;
    hospitalsCache = hospitals;

    // Populate incident focus dropdown
    const select = document.getElementById('selectFocusCase');
    if (select) {
      select.innerHTML = '<option value="">All Incidents & Fleet</option>' +
        activeCasesCache.map(c => `
          <option value="${c.id}" ${c.id === currentFocusedCaseId ? 'selected' : ''}>
            ${c.id.substring(0, 8)}… (${c.priority} · ${Utils.escapeHtml(c.emergency_type || 'Incident')})
          </option>
        `).join('');
    }

    renderMapLayers();
  } catch (err) {
    console.error('Map loading error:', err);
    Utils.showToast('Failed to load map fleet data: ' + err.message, 'danger');
  }
}

function renderMapLayers() {
  if (!staffMapInstance) initStaffMap();

  // Clear existing markers & lines
  staffMapInstance.eachLayer(l => {
    if (l instanceof L.Marker || l instanceof L.CircleMarker || l instanceof L.Polyline) {
      staffMapInstance.removeLayer(l);
    }
  });

  const bounds = [];

  // 1. Render Hospitals (Blue circles)
  hospitalsCache.forEach(h => {
    const marker = L.circleMarker([h.latitude, h.longitude], {
      radius: 10,
      fillColor: '#3b82f6',
      color: '#1d4ed8',
      weight: 2,
      opacity: 1,
      fillOpacity: 0.85,
    }).addTo(staffMapInstance);

    marker.bindPopup(`
      <div style="font-family:sans-serif; min-width:180px;">
        <div style="font-weight:800; font-size:0.95rem; color:#1d4ed8; margin-bottom:4px;">🏥 ${Utils.escapeHtml(h.name)}</div>
        <div style="font-size:0.8rem; color:#64748b;">${Utils.escapeHtml(h.address)}</div>
        <div style="margin-top:6px; font-size:0.82rem;">
          Available Beds: <strong>${h.available_beds}</strong> (ICU: <strong>${h.available_icu_beds}</strong>)
        </div>
        <div style="margin-top:4px; font-size:0.75rem;">
          ${h.has_trauma_center ? '🚨 Trauma Center ' : ''}
          ${h.has_cardiac_care ? '🫀 Cardiac Care' : ''}
        </div>
      </div>
    `);
    bounds.push([h.latitude, h.longitude]);
  });

  // 2. Render Fleet Ambulances (Green = Available, Red/Amber = Busy/Dispatched)
  ambulancesCache.forEach(a => {
    const isAvail = a.status === 'AVAILABLE';
    const marker = L.circleMarker([a.latitude, a.longitude], {
      radius: 8,
      fillColor: isAvail ? '#10b981' : '#ef4444',
      color: '#ffffff',
      weight: 2,
      opacity: 1,
      fillOpacity: 0.9,
    }).addTo(staffMapInstance);

    marker.bindPopup(`
      <div style="font-family:sans-serif; min-width:160px;">
        <div style="font-weight:800; font-size:0.92rem; color:${isAvail ? '#059669' : '#dc2626'};">
          🚑 ${Utils.escapeHtml(a.vehicle_number)} (${a.ambulance_type})
        </div>
        <div style="font-size:0.8rem; color:#475569;">Base: ${Utils.escapeHtml(a.base_station)}</div>
        <div style="font-size:0.8rem; margin-top:2px;">Status: <strong>${a.status}</strong></div>
        <div style="font-size:0.78rem; color:#64748b;">Driver: ${Utils.escapeHtml(a.driver_name)} (${a.contact_number})</div>
      </div>
    `);
    bounds.push([a.latitude, a.longitude]);
  });

  // 3. Render Emergency Incidents (Pulsing Red)
  const activeEmergencies = activeCasesCache.filter(c => c.latitude && c.longitude && c.status !== 'RESOLVED' && c.status !== 'CANCELLED');

  activeEmergencies.forEach(c => {
    const isFocused = currentFocusedCaseId && c.id === currentFocusedCaseId;

    const marker = L.circleMarker([c.latitude, c.longitude], {
      radius: isFocused ? 14 : 10,
      fillColor: '#ef4444',
      color: isFocused ? '#fde047' : '#ffffff',
      weight: isFocused ? 4 : 2,
      opacity: 1,
      fillOpacity: 0.95,
    }).addTo(staffMapInstance);

    marker.bindPopup(`
      <div style="font-family:sans-serif; min-width:200px;">
        <div style="font-weight:800; font-size:0.95rem; color:#ef4444; margin-bottom:4px;">
          🚨 Emergency Case ${c.id.substring(0, 8)}…
        </div>
        <div>Priority: <strong>${c.priority}</strong> (${Utils.escapeHtml(c.emergency_type || 'Incident')})</div>
        <div>Status: <strong>${c.status}</strong></div>
        <div>Location: ${Utils.escapeHtml(c.extracted_location || c.raw_text)}</div>
        <div style="margin-top:8px;">
          <a href="/staff/cases/${encodeURIComponent(c.id)}" style="color:#0284c7; font-weight:700; font-size:0.82rem;">Inspect Full Dossier →</a>
        </div>
      </div>
    `);

    bounds.push([c.latitude, c.longitude]);
  });

  // 4. If a specific case is focused, draw route line from closest/assigned ambulance -> incident -> hospital
  const focusBanner = document.getElementById('mapFocusBanner');
  if (currentFocusedCaseId) {
    const focusedCase = activeCasesCache.find(c => c.id === currentFocusedCaseId);
    if (focusedCase && focusedCase.latitude && focusedCase.longitude) {
      const caseLatLng = [focusedCase.latitude, focusedCase.longitude];
      const assignedAmb = ambulancesCache.find(a => a.assigned_case_id === focusedCase.id || (focusedCase.status === 'DISPATCHED' && a.status === 'ASSIGNED'))
        || ambulancesCache[0];
      const targetHosp = hospitalsCache[0];

      if (assignedAmb) {
        L.polyline([[assignedAmb.latitude, assignedAmb.longitude], caseLatLng], {
          color: '#10b981',
          weight: 4,
          dashArray: '8, 8',
          opacity: 0.9,
        }).addTo(staffMapInstance);
      }

      if (targetHosp) {
        L.polyline([caseLatLng, [targetHosp.latitude, targetHosp.longitude]], {
          color: '#3b82f6',
          weight: 3,
          dashArray: '5, 8',
          opacity: 0.8,
        }).addTo(staffMapInstance);
      }

      staffMapInstance.setView(caseLatLng, 13);

      if (focusBanner) {
        focusBanner.style.display = 'block';
        focusBanner.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
              <strong>Focused on Incident:</strong> Case ${focusedCase.id.substring(0,8)}… ·
              <span style="color:var(--accent-red); font-weight:700;">${focusedCase.priority}</span> ·
              ${Utils.escapeHtml(focusedCase.emergency_type || 'Emergency')}
              (${Utils.escapeHtml(focusedCase.extracted_location || 'Pune')})
            </div>
            <a href="/staff/cases/${encodeURIComponent(focusedCase.id)}" class="btn btn-outline btn-sm">Inspect Case →</a>
          </div>
        `;
      }
      return;
    }
  }

  if (focusBanner) focusBanner.style.display = 'none';

  if (bounds.length > 0) {
    staffMapInstance.fitBounds(bounds, { padding: [40, 40], maxZoom: 13 });
  }
}
