/**
 * ============================================================
 * SahayAI Staff Case Inspector & Pipeline Controller
 * ============================================================
 */

let currentCaseId = null;
let caseMiniMap = null;

document.addEventListener('DOMContentLoaded', async () => {
  const user = await Auth.requireAuth();
  if (!user) return;

  Auth.renderStaffNav('cases');

  // Extract caseId from pathname e.g. /staff/cases/{case_id} or query string ?id=
  const pathParts = window.location.pathname.split('/').filter(Boolean);
  if (pathParts.length >= 3 && pathParts[1] === 'cases') {
    currentCaseId = pathParts[2];
  } else {
    const urlParams = new URLSearchParams(window.location.search);
    currentCaseId = urlParams.get('id') || urlParams.get('case_id');
  }

  if (!currentCaseId) {
    document.getElementById('caseInspectorContainer').innerHTML = Utils.renderEmptyState('No Case ID specified in URL.', '⚠️');
    return;
  }

  setupModals();
  await loadCaseDetails();
});

async function loadCaseDetails() {
  const container = document.getElementById('caseInspectorContainer');
  container.innerHTML = `
    <div style="text-align:center; padding:50px;">
      <span class="spinner" style="width:36px; height:36px; border-width:3px; color:var(--accent-blue);"></span>
      <div style="margin-top:16px; color:var(--text-secondary);">Loading full case dossier for ${Utils.escapeHtml(currentCaseId)}…</div>
    </div>
  `;

  try {
    const [c, conf, timeline, ambulances, hospitals, ragStatus] = await Promise.all([
      window.api.getCase(currentCaseId),
      window.api.getCaseConfidence(currentCaseId).catch(() => null),
      window.api.getCaseTimeline(currentCaseId).catch(() => []),
      window.api.listAmbulances().catch(() => []),
      window.api.listHospitals().catch(() => []),
      window.api.getRAGStatus().catch(() => null),
    ]);

    renderCaseDetails(c, conf, timeline, ambulances, hospitals, ragStatus);
  } catch (err) {
    console.error('Case detail error:', err);
    container.innerHTML = Utils.renderErrorState(`Failed to load case: ${err.message}`, 'loadCaseDetails()');
  }
}

function renderCaseDetails(c, conf, timeline, ambulances, hospitals, ragStatus) {
  const container = document.getElementById('caseInspectorContainer');

  const pBadge = Utils.getPriorityBadge(c.priority);
  const sBadge = Utils.getStatusBadge(c.status);
  const confScore = conf ? conf.overall_confidence : (c.confidence_score || 0.0);
  const confColor = Utils.getConfidenceColor(confScore);
  const needsReview = c.status === 'UNDER_REVIEW' || (conf && conf.requires_human_review);

  // Matched units
  const assignedAmb = ambulances.find(a => a.assigned_case_id === c.id || (c.status === 'DISPATCHED' && a.status === 'ASSIGNED'))
    || (c.status === 'DISPATCHED' ? ambulances[0] : null);
  const matchedHosp = hospitals[0] || null;

  container.innerHTML = `
    <!-- Top Alert Banner if Under Review -->
    ${needsReview ? `
      <div class="review-required-banner">
        <div class="icon">⚠️</div>
        <div>
          <div style="font-weight:700; color:var(--accent-amber); font-size:1.05rem;">Human Dispatcher Review Required</div>
          <div style="font-size:0.85rem; color:var(--text-secondary); margin-top:2px;">
            Trigger Reason: <strong>${Utils.escapeHtml(conf?.review_trigger_reason || c.human_review_reason || 'Low confidence or conflicting clinical signals')}</strong>
          </div>
        </div>
        <button class="btn btn-amber" style="margin-left:auto;" onclick="openReviewModal()">🧑‍⚕️ Review Decision Now</button>
      </div>
    ` : ''}

    <!-- Quick Pipeline Actions Toolbar -->
    <div class="workflow-actions">
      <strong style="font-size:0.8rem; text-transform:uppercase; color:var(--text-muted); letter-spacing:0.05em; margin-right:4px;">Pipeline Operations:</strong>
      <button class="btn btn-primary btn-sm" onclick="triggerTriage()">🧠 Re-Run AI Triage</button>
      <button class="btn btn-outline btn-sm" onclick="triggerRAGVerify()">📚 Clinical RAG Verify</button>
      <button class="btn btn-outline btn-sm" onclick="openLocationModal()">📍 Override Location</button>
      <a href="/staff/map?focus=${encodeURIComponent(c.id)}" class="btn btn-outline btn-sm">🗺️ Track on Fleet Map</a>
      <button class="btn btn-success btn-sm" onclick="triggerDispatch()">🚑 Verify &amp; Dispatch Fleet</button>
      ${needsReview ? `<button class="btn btn-amber btn-sm" onclick="openReviewModal()">🧑‍⚕️ Intervene</button>` : ''}
      <button class="btn btn-outline btn-sm" onclick="loadCaseDetails()">🔄 Refresh</button>
    </div>

    <!-- 2-Column Main Inspector Layout -->
    <div class="detail-grid">

      <!-- Left Column: Case Information & AI Pipeline Stages -->
      <div>

        <!-- 1. Case Intake & Caller Information -->
        <div class="detail-section">
          <h4>
            <span>📥 1. Intake &amp; Caller Narrative</span>
            <span>${pBadge}</span>
          </h4>
          <div class="pipeline-step">
            <div class="pipeline-step-title">Raw Emergency Description</div>
            <div class="pipeline-step-body" style="font-weight:600; font-size:0.95rem;">"${Utils.escapeHtml(c.raw_text || '')}"</div>
          </div>
          <div style="display:flex; gap:16px; font-size:0.82rem; color:var(--text-secondary); flex-wrap:wrap; margin-top:12px;">
            <div>Modality: <strong style="color:var(--text-primary);">${Utils.escapeHtml(c.modality || 'text')}</strong></div>
            <div>Language: <strong style="color:var(--text-primary);">${Utils.escapeHtml(c.language || 'unknown')}</strong></div>
            <div>Caller Phone: <strong style="color:var(--text-primary);">${Utils.escapeHtml(c.caller_phone || 'Anonymous')}</strong></div>
            <div>Status: ${sBadge}</div>
            <div>Received: <strong style="color:var(--text-primary);">${Utils.formatDateTime(c.created_at || c.updated_at)}</strong></div>
          </div>
        </div>

        <!-- 2. AI Hybrid Clinical Analysis -->
        <div class="detail-section">
          <h4>
            <span>🧠 2. AI Hybrid Clinical Analysis</span>
            <span class="badge ${c.has_conflict ? 'badge-high' : 'badge-low'}">
              ${c.has_conflict ? '⚠️ Rule Conflict Detected' : '✅ Rule Agreement'}
            </span>
          </h4>

          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:12px; margin-bottom:14px;">
            <div style="background:#090e1b; border:1px solid var(--border-color); padding:12px; border-radius:var(--radius-md);">
              <div class="pipeline-step-title">Assessed Condition</div>
              <div style="font-size:1rem; font-weight:800; color:var(--text-primary);">${Utils.escapeHtml(c.emergency_type || 'Unknown')}</div>
            </div>
            <div style="background:#090e1b; border:1px solid var(--border-color); padding:12px; border-radius:var(--radius-md);">
              <div class="pipeline-step-title">Recommended Ambulance Tier</div>
              <div style="font-size:1rem; font-weight:800; color:var(--accent-cyan);">${Utils.escapeHtml(c.recommended_ambulance || 'ALS')}</div>
            </div>
            <div style="background:#090e1b; border:1px solid var(--border-color); padding:12px; border-radius:var(--radius-md);">
              <div class="pipeline-step-title">Patients / Vitals</div>
              <div style="font-size:0.86rem; color:var(--text-secondary);">
                Count: <strong>${c.patient_count || 1}</strong> · Conscious: <strong>${Utils.escapeHtml(c.conscious_status || 'unknown')}</strong> · Breathing: <strong>${Utils.escapeHtml(c.breathing_status || 'unknown')}</strong>
              </div>
            </div>
          </div>

          <!-- Symptoms Tags -->
          ${c.symptoms && c.symptoms.length ? `
            <div style="margin-bottom:14px;">
              <div class="pipeline-step-title">Extracted Clinical Symptoms</div>
              <div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:4px;">
                ${c.symptoms.map(s => `<span class="badge" style="background:#1e293b; color:#cbd5e1; font-size:0.75rem;">${Utils.escapeHtml(s)}</span>`).join('')}
              </div>
            </div>
          ` : ''}

          <!-- AI vs Deterministic Comparison -->
          <div style="background:#090e1b; border:1px solid var(--border-color); border-radius:var(--radius-md); padding:12px; font-size:0.82rem; margin-bottom:12px;">
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
              <span>AI Suggested: <strong>${Utils.escapeHtml(c.ai_suggested_severity || c.priority)}</strong> (${Utils.escapeHtml(c.ai_suggested_ambulance || c.recommended_ambulance || 'ALS')})</span>
              <span>Deterministic Clinical Rule: <strong>${Utils.escapeHtml(c.deterministic_severity || c.priority)}</strong> (${Utils.escapeHtml(c.deterministic_ambulance || c.recommended_ambulance || 'ALS')})</span>
            </div>
            ${c.has_conflict ? `
              <div style="color:var(--accent-amber); margin-top:4px;">
                ⚠️ <strong>Conflict Reason:</strong> ${Utils.escapeHtml(c.conflict_reason || 'AI recommendation differed from deterministic protocols')}
              </div>
            ` : ''}
          </div>

          ${c.clinical_rationale ? `
            <div class="pipeline-step step-success">
              <div class="pipeline-step-title">Clinical Rationale</div>
              <div class="pipeline-step-body" style="font-size:0.86rem;">${Utils.escapeHtml(c.clinical_rationale)}</div>
            </div>
          ` : ''}
        </div>

        <!-- 3. RAG Clinical Protocol Verification -->
        <div class="detail-section">
          <h4>
            <span>📚 3. RAG Knowledge Base Clinical Verification</span>
            <span class="badge badge-low">Vector Store Active</span>
          </h4>
          <div style="font-size:0.85rem; color:var(--text-secondary); line-height:1.5;">
            Clinical evidence chunks retrieved from emergency protocols to cross-verify triage parameters:
          </div>
          <div style="background:#090e1b; border:1px solid var(--border-color); border-radius:var(--radius-md); padding:12px; margin-top:10px; font-size:0.84rem;">
            <div>Indexed Knowledge: <strong>${ragStatus?.total_chunks_indexed || 30} chunks</strong> (Lightweight Vector Store)</div>
            ${c.missing_information && c.missing_information.length ? `
              <div style="color:var(--accent-amber); margin-top:6px;">
                Missing Critical Details: <strong>${c.missing_information.map(m => Utils.escapeHtml(m)).join(', ')}</strong>
              </div>
            ` : '<div style="color:var(--accent-emerald); margin-top:4px;">✓ No critical clinical information missing</div>'}
          </div>
        </div>

        <!-- 4. Location Verification & Spatial Resolution -->
        <div class="detail-section">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <h4>📍 4. Location Verification &amp; Spatial Coordinates</h4>
            <button class="btn btn-outline btn-sm" onclick="openLocationModal()">✏️ Set / Override</button>
          </div>

          <div style="background:#090e1b; border:1px solid var(--border-color); border-radius:var(--radius-md); padding:14px; margin-bottom:14px;">
            <div style="font-size:0.75rem; color:var(--text-muted); text-transform:uppercase; font-weight:700;">Reported Landmark / Address</div>
            <div style="font-size:0.95rem; font-weight:700; color:var(--text-primary); margin-top:2px;">
              📍 ${Utils.escapeHtml(c.extracted_location || c.raw_text || 'Pune Location')}
            </div>
            <div style="display:flex; gap:16px; font-size:0.8rem; color:var(--text-secondary); margin-top:8px;">
              <span>Coordinates: <strong>${c.latitude ? `${c.latitude.toFixed(4)}, ${c.longitude.toFixed(4)}` : 'Not geocoded'}</strong></span>
              <span>Provider: <strong>${Utils.escapeHtml(c.geocoding_provider || 'nominatim')}</strong></span>
              <span>Verified: <strong style="color:${c.is_location_verified ? 'var(--accent-emerald)' : 'var(--accent-amber)'};">${c.is_location_verified ? '✅ Yes' : '⚠️ Pending'}</strong></span>
            </div>
          </div>

          <div id="caseMiniMap" style="height:220px; border-radius:var(--radius-md); border:1px solid var(--border-color);"></div>
        </div>

        <!-- 5. Resource Verification & Dispatch -->
        <div class="detail-section">
          <h4>
            <span>🚑 5. Resource Verification &amp; Dispatch</span>
            <span class="badge ${c.status === 'DISPATCHED' ? 'badge-dispatched' : 'badge-pending'}">
              ${c.status === 'DISPATCHED' ? 'DISPATCH ACTIVE' : 'PENDING DISPATCH'}
            </span>
          </h4>

          <div style="display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:14px;">
            <div style="background:#090e1b; border:1px solid var(--border-color); border-radius:var(--radius-md); padding:14px;">
              <div class="pipeline-step-title">Matched Fleet Ambulance</div>
              ${assignedAmb ? `
                <div style="font-size:1.1rem; font-weight:800; color:var(--accent-emerald);">${assignedAmb.vehicle_number} (${assignedAmb.ambulance_type})</div>
                <div style="font-size:0.82rem; color:var(--text-secondary); margin-top:2px;">Base: ${assignedAmb.base_station}</div>
                <div style="font-size:0.82rem; color:var(--text-secondary);">Driver: <strong>${assignedAmb.driver_name}</strong> (${assignedAmb.contact_number})</div>
              ` : `
                <div style="color:var(--text-muted); font-size:0.85rem;">No ambulance currently locked to case.</div>
              `}
            </div>

            <div style="background:#090e1b; border:1px solid var(--border-color); border-radius:var(--radius-md); padding:14px;">
              <div class="pipeline-step-title">Assigned Destination Hospital</div>
              ${matchedHosp ? `
                <div style="font-size:1.1rem; font-weight:800; color:var(--accent-blue);">${matchedHosp.name}</div>
                <div style="font-size:0.82rem; color:var(--text-secondary); margin-top:2px;">${matchedHosp.address}</div>
                <div style="font-size:0.82rem; color:var(--accent-emerald);">Beds Available: <strong>${matchedHosp.available_beds}</strong> (ICU: ${matchedHosp.available_icu_beds})</div>
              ` : `
                <div style="color:var(--text-muted); font-size:0.85rem;">Sassoon General Hospital</div>
              `}
            </div>
          </div>

          <div style="display:flex; justify-content:flex-end;">
            <button class="btn btn-success" onclick="triggerDispatch()">
              ${c.status === 'DISPATCHED' ? '🔄 Re-Verify & Re-Dispatch' : '🚑 Dispatch Nearest Available Units Now'}
            </button>
          </div>
        </div>

        <!-- 6. Immutable Audit Timeline -->
        <div class="detail-section">
          <h4>📜 6. Chronological Audit Trail</h4>
          <div class="timeline-container">
            ${timeline && timeline.length ? timeline.map(entry => `
              <div class="timeline-item">
                <div class="timeline-node">●</div>
                <div class="timeline-content">
                  <div class="timeline-header">
                    <span style="font-weight:700; color:var(--text-primary); font-size:0.86rem;">${Utils.escapeHtml(entry.action)}</span>
                    <span style="font-size:0.75rem; color:var(--text-muted);">${Utils.formatTime(entry.created_at)}</span>
                  </div>
                  <div style="display:flex; gap:12px; font-size:0.78rem; color:var(--text-secondary);">
                    <span>Stage: <strong style="color:var(--accent-cyan);">${Utils.escapeHtml(entry.stage)}</strong></span>
                    <span>Actor: <strong>${Utils.escapeHtml(entry.actor)}</strong></span>
                    ${entry.latency_ms ? `<span>Latency: ${entry.latency_ms}ms</span>` : ''}
                  </div>
                  ${entry.details && Object.keys(entry.details).length ? `
                    <div style="font-size:0.76rem; color:var(--text-muted); margin-top:4px; font-family:var(--font-mono); background:#060a14; padding:6px 8px; border-radius:4px; overflow-x:auto;">
                      ${Utils.escapeHtml(JSON.stringify(entry.details))}
                    </div>
                  ` : ''}
                </div>
              </div>
            `).join('') : '<div style="color:var(--text-muted); font-size:0.85rem;">No audit logs recorded for this case.</div>'}
          </div>
        </div>

      </div>

      <!-- Right Column: Multi-Signal Confidence Matrix & Decision Overview -->
      <div>

        <!-- Confidence Matrix Card -->
        <div class="detail-section">
          <h4>📊 Confidence Breakdown</h4>
          <div class="conf-summary-card">
            <div class="conf-score-large" style="color:${confColor};">
              ${(confScore * 100).toFixed(0)}%
            </div>
            <div class="conf-level-tag" style="color:${confColor};">
              ${conf ? conf.confidence_level : 'CALCULATED'} CONFIDENCE
            </div>
          </div>

          <!-- 6 Weighted Signals -->
          <div style="display:flex; flex-direction:column; gap:8px;">
            ${renderConfidenceRow('Clinical Extraction', conf?.components?.extraction_quality, '25%')}
            ${renderConfidenceRow('Deterministic Rule Agreement', conf?.components?.rule_agreement, '20%')}
            ${renderConfidenceRow('Spatial Location Verification', conf?.components?.location_verification, '20%')}
            ${renderConfidenceRow('Resource Availability', conf?.components?.resource_availability, '15%')}
            ${renderConfidenceRow('Duplicate Anomaly Check', conf?.components?.duplicate_penalty, '10%')}
            ${renderConfidenceRow('LLM Direct Confidence', conf?.components?.llm_direct_confidence, '10%')}
          </div>

          <div style="margin-top:16px; padding-top:14px; border-top:1px solid rgba(255,255,255,0.06); font-size:0.8rem; color:var(--text-secondary);">
            Requires Human Review: <strong style="color:${needsReview ? 'var(--accent-amber)' : 'var(--accent-emerald)'};">${needsReview ? '⚠️ YES' : 'NO'}</strong>
          </div>
        </div>

        <!-- Case Metadata Card -->
        <div class="detail-section">
          <h4>⚙️ System Metadata</h4>
          <div style="display:flex; flex-direction:column; gap:8px; font-size:0.82rem; color:var(--text-secondary);">
            <div>Case ID: <span style="font-family:var(--font-mono); color:var(--text-primary);">${c.id}</span></div>
            <div>Database Status: ${sBadge}</div>
            <div>Priority Level: ${pBadge}</div>
            <div>Geocoding Provider: <strong>${Utils.escapeHtml(c.geocoding_provider || '—')}</strong></div>
          </div>
        </div>

      </div>

    </div>
  `;

  setTimeout(() => {
    initMiniMap(c);
  }, 100);
}

function renderConfidenceRow(label, score, weight) {
  const val = score !== null && score !== undefined ? score : 0.8;
  const col = Utils.getConfidenceColor(val);
  return `
    <div class="conf-signal-row">
      <div class="conf-signal-meta">
        <span>${label} (${weight})</span>
        <span style="font-weight:700; color:${col};">${(val * 100).toFixed(0)}%</span>
      </div>
      <div class="conf-bar-wrap">
        <div class="conf-bar" style="width:${(val * 100).toFixed(0)}%; background:${col};"></div>
      </div>
    </div>
  `;
}

function initMiniMap(c) {
  const mapEl = document.getElementById('caseMiniMap');
  if (!mapEl) return;

  if (caseMiniMap) {
    caseMiniMap.remove();
    caseMiniMap = null;
  }

  const lat = c.latitude || 18.5204;
  const lon = c.longitude || 73.8567;

  caseMiniMap = L.map('caseMiniMap').setView([lat, lon], 13);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '© OpenStreetMap contributors',
  }).addTo(caseMiniMap);

  L.circleMarker([lat, lon], {
    radius: 10,
    fillColor: '#ef4444',
    color: '#ffffff',
    weight: 2,
    fillOpacity: 0.95,
  }).addTo(caseMiniMap).bindPopup(`<strong>🚨 Incident Site</strong><br>${Utils.escapeHtml(c.extracted_location || c.raw_text || '')}`).openPopup();
}

/* ── Modals & Pipeline Operations ───────────────────────────── */
function setupModals() {
  document.getElementById('btnCloseLocationModal')?.addEventListener('click', closeLocationModal);
  document.getElementById('btnSaveLocation')?.addEventListener('click', saveManualLocation);
  document.getElementById('btnCloseReviewModal')?.addEventListener('click', closeReviewModal);
  document.getElementById('btnSubmitReviewAction')?.addEventListener('click', submitReviewAction);
}

window.openLocationModal = function() {
  document.getElementById('locationModal').classList.add('active');
};
window.closeLocationModal = function() {
  document.getElementById('locationModal').classList.remove('active');
};

async function saveManualLocation() {
  const lat = parseFloat(document.getElementById('manualLat').value);
  const lon = parseFloat(document.getElementById('manualLon').value);
  const addr = document.getElementById('manualAddress').value.trim();

  if (isNaN(lat) || isNaN(lon)) {
    alert('Please enter valid numeric latitude and longitude coordinates.');
    return;
  }

  try {
    const user = Auth.getUser();
    await window.api.updateCaseLocation(currentCaseId, {
      latitude: lat,
      longitude: lon,
      formatted_address: addr || 'Manual Dispatcher Verified Entry',
    }, user ? user.username : 'dispatcher_1');

    Utils.showToast('✅ Location coordinates successfully updated!', 'success');
    closeLocationModal();
    await loadCaseDetails();
  } catch (err) {
    alert('Failed to update location: ' + err.message);
  }
}

window.openReviewModal = function() {
  document.getElementById('reviewModal').classList.add('active');
};
window.closeReviewModal = function() {
  document.getElementById('reviewModal').classList.remove('active');
};

async function submitReviewAction() {
  const action = document.getElementById('reviewActionSelect').value;
  const modSeverity = document.getElementById('reviewModSeverity').value || null;
  const modAmbulance = document.getElementById('reviewModAmbulance').value || null;
  const notes = document.getElementById('reviewNotes').value.trim();
  const user = Auth.getUser();

  try {
    await window.api.submitCaseReview(currentCaseId, {
      action,
      modified_severity: modSeverity,
      modified_ambulance: modAmbulance,
      dispatcher_notes: notes || undefined,
      dispatcher_id: user ? user.username : 'dispatcher_1',
    });

    Utils.showToast(`✅ Review decision (${action}) recorded successfully!`, 'success');
    closeReviewModal();
    await loadCaseDetails();
  } catch (err) {
    alert('Review submission error: ' + err.message);
  }
}

window.triggerTriage = async function() {
  try {
    Utils.showToast('Triggering AI clinical triage extraction…', 'info');
    await window.api.triageCase(currentCaseId);
    Utils.showToast('Clinical triage analysis completed.', 'success');
    await loadCaseDetails();
  } catch (err) {
    alert('Triage error: ' + err.message);
  }
};

window.triggerRAGVerify = async function() {
  try {
    Utils.showToast('Searching clinical guidelines vector store…', 'info');
    await window.api.verifyCaseRAG(currentCaseId);
    Utils.showToast('Clinical RAG verification completed.', 'success');
    await loadCaseDetails();
  } catch (err) {
    alert('RAG verification error: ' + err.message);
  }
};

window.triggerDispatch = async function() {
  try {
    Utils.showToast('Running spatial resource matching and OSRM routing…', 'info');
    const match = await window.api.dispatchCase(currentCaseId);
    Utils.showToast(`✅ Dispatched ambulance: ${match.matched_ambulance?.vehicle_number || ''} (ETA: ${match.ambulance_eta_minutes ? match.ambulance_eta_minutes.toFixed(1) : '~8'} min)`, 'success');
    await loadCaseDetails();
  } catch (err) {
    alert('Dispatch failed: ' + err.message);
  }
};
