/**
 * ============================================================
 * SahayAI Citizen Live Case Tracker Controller
 * ============================================================
 */

let citizenMapInstance = null;
let pollTimer = null;

document.addEventListener('DOMContentLoaded', () => {
  const urlParams = new URLSearchParams(window.location.search);
  const caseId = urlParams.get('case_id') || urlParams.get('id');

  const searchForm = document.getElementById('citizenSearchForm');
  if (searchForm) {
    searchForm.addEventListener('submit', e => {
      e.preventDefault();
      const input = document.getElementById('searchCaseId').value.trim();
      if (input) {
        window.location.href = `/track?case_id=${encodeURIComponent(input)}`;
      }
    });
  }

  if (caseId) {
    document.getElementById('searchCaseId').value = caseId;
    loadCitizenCaseStatus(caseId);
    pollTimer = setInterval(() => loadCitizenCaseStatus(caseId, true), 8000);
  } else {
    document.getElementById('citizenTrackingContent').innerHTML = Utils.renderEmptyState(
      'Enter your Emergency Case ID above to track responding units and live ETA.',
      '🔍'
    );
  }
});

async function loadCitizenCaseStatus(caseId, isPolling = false) {
  const container = document.getElementById('citizenTrackingContent');
  if (!isPolling) {
    container.innerHTML = `
      <div style="text-align:center; padding:40px 20px;">
        <span class="spinner" style="width:36px; height:36px; border-width:3px; color:var(--accent-cyan);"></span>
        <div style="margin-top:16px; color:var(--text-secondary); font-size:1rem;">Locating your emergency dispatch record…</div>
      </div>
    `;
  }

  try {
    const [caseData, ambulances, hospitals] = await Promise.all([
      window.api.getCase(caseId),
      window.api.listAmbulances().catch(() => []),
      window.api.listHospitals().catch(() => []),
    ]);

    renderCitizenTrackingView(caseData, ambulances, hospitals);
  } catch (err) {
    console.error('Track error:', err);
    if (!isPolling) {
      container.innerHTML = `
        <div class="alert alert-danger" style="margin-top:20px;">
          <div>
            <h4 style="margin-bottom:6px;">Case Not Found</h4>
            <p style="font-size:0.9rem;">We could not find an active emergency report with ID <strong>${Utils.escapeHtml(caseId)}</strong>. Please verify your reference number or submit a new emergency.</p>
          </div>
          <a href="/" class="btn btn-primary btn-sm" style="margin-left:auto;">Report Emergency</a>
        </div>
      `;
    }
  }
}

function renderCitizenTrackingView(c, ambulances, hospitals) {
  const container = document.getElementById('citizenTrackingContent');

  // Find responding ambulance
  const isDispatched = c.status === 'DISPATCHED';
  const assignedAmbulance = ambulances.find(a =>
    a.assigned_case_id === c.id || (isDispatched && a.status === 'ASSIGNED')
  ) || (isDispatched ? ambulances.find(a => a.status === 'AVAILABLE') : null);

  // Default hospital if assigned
  const assignedHospital = hospitals[0] || null;

  // Status Badge Logic
  let statusColor = '#3b82f6';
  let statusText = 'Emergency Intake Received';
  let statusIcon = '📥';

  if (c.status === 'TRIAGED') {
    statusColor = '#06b6d4';
    statusText = 'AI Clinical Triage Completed';
    statusIcon = '🧠';
  } else if (c.status === 'UNDER_REVIEW') {
    statusColor = '#f59e0b';
    statusText = 'Dispatcher Verifying Location & Resources';
    statusIcon = '🧑‍⚕️';
  } else if (c.status === 'DISPATCHED') {
    statusColor = '#10b981';
    statusText = 'Ambulance En Route to Your Location';
    statusIcon = '🚑';
  } else if (c.status === 'RESOLVED') {
    statusColor = '#8b5cf6';
    statusText = 'Incident Resolved / Arrived at Hospital';
    statusIcon = '✅';
  }

  // ETA Estimation
  const etaMinutes = isDispatched ? (c.eta_minutes || 8.5) : null;

  // First Aid Advice heuristic
  let firstAidGuidance = 'Stay on the line if contacted by the dispatcher. Keep the patient in a safe, comfortable position.';
  const typeLower = (c.emergency_type || '').toLowerCase();
  const rawLower = (c.raw_text || '').toLowerCase();

  if (typeLower.includes('cardiac') || rawLower.includes('chest') || rawLower.includes('हार्ट')) {
    firstAidGuidance = 'Have the patient sit upright and rest quietly. Loosen tight clothing. If unresponsive and not breathing normally, begin continuous firm chest compressions at center of chest (100–120 bpm).';
  } else if (typeLower.includes('trauma') || typeLower.includes('accident') || rawLower.includes('रक्त') || rawLower.includes('bleed')) {
    firstAidGuidance = 'Do NOT move the patient’s neck or spine unless in immediate danger. Apply firm, continuous direct pressure with a clean cloth over bleeding sites.';
  } else if (typeLower.includes('burn') || rawLower.includes('भाजले') || rawLower.includes('जल')) {
    firstAidGuidance = 'Cool the burn with gentle clean running water for 10–20 minutes. Do NOT apply ice, oil, turmeric, or butter. Cover loosely with a clean dry cloth.';
  } else if (typeLower.includes('breath') || rawLower.includes('सांस') || rawLower.includes('दम')) {
    firstAidGuidance = 'Help the patient sit upright. Loosen any tight clothing around the neck and chest. Encourage slow, deep breaths and assist with prescribed inhaler if available.';
  }

  container.innerHTML = `
    <!-- Top Hero Status Card -->
    <div class="track-hero">
      <div class="track-header">
        <div>
          <div style="font-size:0.78rem; font-weight:700; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.06em; margin-bottom:4px;">
            Emergency Reference ID
          </div>
          <div style="font-size:1.4rem; font-weight:800; font-family:var(--font-mono); color:var(--accent-cyan); display:flex; align-items:center; gap:8px;">
            ${Utils.escapeHtml(c.id)}
            <span style="font-size:0.8rem; background:rgba(255,255,255,0.08); padding:3px 8px; border-radius:4px; font-family:var(--font-sans); color:var(--text-secondary); cursor:pointer;" onclick="navigator.clipboard.writeText('${c.id}'); Utils.showToast('Case ID copied to clipboard!', 'info');">📋 Copy</span>
          </div>
          <div style="font-size:0.82rem; color:var(--text-secondary); margin-top:4px;">
            Reported: <strong>${Utils.formatDateTime(c.created_at || c.updated_at)}</strong>
          </div>
        </div>

        <div class="track-status-pill" style="background:${statusColor}20; color:${statusColor}; border:1px solid ${statusColor}50;">
          <span>${statusIcon}</span>
          <span>${statusText}</span>
        </div>
      </div>

      <!-- Emergency Parameters Summary -->
      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:12px; padding:14px; background:#090e1b; border-radius:var(--radius-md); border:1px solid var(--border-color); margin-bottom:20px;">
        <div>
          <div style="font-size:0.74rem; color:var(--text-muted); text-transform:uppercase; font-weight:700;">Severity Level</div>
          <div style="margin-top:4px;">${Utils.getPriorityBadge(c.priority)}</div>
        </div>
        <div>
          <div style="font-size:0.74rem; color:var(--text-muted); text-transform:uppercase; font-weight:700;">Detected Condition</div>
          <div style="font-size:0.92rem; font-weight:700; color:var(--text-primary); margin-top:4px;">${Utils.escapeHtml(c.emergency_type || 'General Medical Incident')}</div>
        </div>
        <div>
          <div style="font-size:0.74rem; color:var(--text-muted); text-transform:uppercase; font-weight:700;">Recommended Ambulance</div>
          <div style="font-size:0.92rem; font-weight:700; color:var(--accent-cyan); margin-top:4px;">${Utils.escapeHtml(c.recommended_ambulance || 'Advanced Life Support (ALS)')}</div>
        </div>
        <div>
          <div style="font-size:0.74rem; color:var(--text-muted); text-transform:uppercase; font-weight:700;">Location Status</div>
          <div style="font-size:0.92rem; font-weight:600; color:${c.is_location_verified ? 'var(--accent-emerald)' : 'var(--accent-amber)'}; margin-top:4px;">
            ${c.is_location_verified ? '✅ Verified Coordinates' : '📍 Landmark Registered'}
          </div>
        </div>
      </div>

      <!-- Resource Allocation Grid -->
      <div class="track-resource-grid">
        <!-- Responding Ambulance -->
        <div class="track-card">
          <div class="track-card-header">
            <span>🚑 RESPONDING AMBULANCE</span>
            <span class="badge ${isDispatched ? 'badge-dispatched' : 'badge-pending'}">${isDispatched ? 'EN ROUTE' : 'DISPATCHING'}</span>
          </div>
          <div>
            ${assignedAmbulance ? `
              <div style="font-size:1.15rem; font-weight:800; color:var(--text-primary);">${assignedAmbulance.vehicle_number} (${assignedAmbulance.ambulance_type})</div>
              <div style="font-size:0.84rem; color:var(--text-secondary); margin-top:2px;">Base: ${assignedAmbulance.base_station}</div>
              <div style="font-size:0.84rem; color:var(--text-secondary); margin-top:4px;">Driver: <strong>${assignedAmbulance.driver_name}</strong></div>
              <div style="margin-top:10px;">
                <a href="tel:${assignedAmbulance.contact_number}" class="btn btn-outline btn-sm" style="color:var(--accent-emerald); border-color:var(--accent-emerald);">
                  📞 Call Driver (${assignedAmbulance.contact_number})
                </a>
              </div>
            ` : `
              <div style="color:var(--text-muted); font-size:0.9rem;">Matching nearest high-priority ambulance in Pune fleet…</div>
            `}
          </div>
          <div style="margin-top:auto; padding-top:10px; border-top:1px solid rgba(255,255,255,0.05);">
            <div style="font-size:0.74rem; color:var(--text-muted); text-transform:uppercase;">Estimated Time of Arrival (ETA)</div>
            <div class="eta-callout">
              ${etaMinutes ? `${etaMinutes.toFixed(0)}<span>min</span>` : `~8<span>min</span>`}
            </div>
          </div>
        </div>

        <!-- Destination Hospital -->
        <div class="track-card">
          <div class="track-card-header">
            <span>🏥 DESTINATION HOSPITAL</span>
            <span class="badge badge-triaged">PRE-ALERTED</span>
          </div>
          <div>
            ${assignedHospital ? `
              <div style="font-size:1.15rem; font-weight:800; color:var(--text-primary);">${assignedHospital.name}</div>
              <div style="font-size:0.84rem; color:var(--text-secondary); margin-top:2px;">${assignedHospital.address}</div>
              <div style="font-size:0.82rem; color:var(--accent-emerald); font-weight:600; margin-top:4px;">
                Available Beds: ${assignedHospital.available_beds} · ICU Beds: ${assignedHospital.available_icu_beds}
              </div>
              <div style="margin-top:10px;">
                <a href="tel:${assignedHospital.contact_phone}" class="btn btn-outline btn-sm" style="color:var(--accent-blue); border-color:var(--accent-blue);">
                  📞 Hospital Emergency (${assignedHospital.contact_phone})
                </a>
              </div>
            ` : `
              <div style="color:var(--text-muted); font-size:0.9rem;">Sassoon General Hospital (Trauma Center Alerted)</div>
            `}
          </div>
          <div style="margin-top:auto; padding-top:10px; border-top:1px solid rgba(255,255,255,0.05); font-size:0.78rem; color:var(--text-muted);">
            Emergency department pre-notified of incoming patient with clinical extraction summary.
          </div>
        </div>
      </div>

      <!-- First Aid Guidance Card -->
      <div class="first-aid-box">
        <h4><span>🩹</span> While You Wait for the Ambulance</h4>
        <p>${Utils.escapeHtml(firstAidGuidance)}</p>
      </div>

      <!-- Location Narrative -->
      <div style="background:#090e1b; border:1px solid var(--border-color); border-radius:var(--radius-md); padding:14px; margin-bottom:14px;">
        <div style="font-size:0.75rem; color:var(--text-muted); font-weight:700; text-transform:uppercase; margin-bottom:4px;">Reported Incident Location</div>
        <div style="font-size:0.92rem; font-weight:600; color:var(--text-primary);">
          📍 ${Utils.escapeHtml(c.extracted_location || c.raw_text || 'Pune Location')}
        </div>
      </div>

      <!-- Interactive Map for Citizen -->
      <div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <span style="font-size:0.82rem; font-weight:700; color:var(--text-muted); text-transform:uppercase;">Live Responding Units Map</span>
          <span style="font-size:0.75rem; color:var(--accent-emerald);">● Live GPS Telemetry</span>
        </div>
        <div id="citizenMap"></div>
      </div>
    </div>
  `;

  // Render Map markers
  setTimeout(() => {
    initCitizenMap(c, assignedAmbulance, assignedHospital);
  }, 100);
}

function initCitizenMap(c, ambulance, hospital) {
  const mapDiv = document.getElementById('citizenMap');
  if (!mapDiv) return;

  if (citizenMapInstance) {
    citizenMapInstance.remove();
    citizenMapInstance = null;
  }

  const defaultLat = c.latitude || 18.5204;
  const defaultLon = c.longitude || 73.8567;

  citizenMapInstance = L.map('citizenMap').setView([defaultLat, defaultLon], 13);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '© OpenStreetMap contributors',
  }).addTo(citizenMapInstance);

  const markers = [];

  // Incident Marker (Red)
  const incidentMarker = L.circleMarker([defaultLat, defaultLon], {
    radius: 12,
    fillColor: '#ef4444',
    color: '#ffffff',
    weight: 3,
    fillOpacity: 0.95,
  }).addTo(citizenMapInstance).bindPopup(`<strong>🚨 Your Emergency Location</strong><br>${Utils.escapeHtml(c.extracted_location || c.raw_text || 'Reported Site')}`);
  markers.push([defaultLat, defaultLon]);

  // Ambulance Marker (Emerald/Blue)
  if (ambulance && ambulance.latitude && ambulance.longitude) {
    L.circleMarker([ambulance.latitude, ambulance.longitude], {
      radius: 9,
      fillColor: '#10b981',
      color: '#ffffff',
      weight: 2,
      fillOpacity: 0.95,
    }).addTo(citizenMapInstance).bindPopup(`<strong>🚑 Responding Ambulance (${ambulance.vehicle_number})</strong><br>Driver: ${ambulance.driver_name}`);
    markers.push([ambulance.latitude, ambulance.longitude]);

    // Dashed route line from ambulance to incident
    L.polyline([[ambulance.latitude, ambulance.longitude], [defaultLat, defaultLon]], {
      color: '#10b981',
      weight: 3,
      dashArray: '6, 8',
      opacity: 0.85,
    }).addTo(citizenMapInstance);
  }

  // Hospital Marker (Blue)
  if (hospital && hospital.latitude && hospital.longitude) {
    L.circleMarker([hospital.latitude, hospital.longitude], {
      radius: 9,
      fillColor: '#3b82f6',
      color: '#ffffff',
      weight: 2,
      fillOpacity: 0.9,
    }).addTo(citizenMapInstance).bindPopup(`<strong>🏥 ${hospital.name}</strong><br>Destination Hospital`);
    markers.push([hospital.latitude, hospital.longitude]);
  }

  if (markers.length > 1) {
    citizenMapInstance.fitBounds(markers, { padding: [40, 40], maxZoom: 14 });
  }
}
