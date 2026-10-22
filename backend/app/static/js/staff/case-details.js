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

  // Matched units — from verified dispatch data on the Case object
  const assignedAmb = c.assigned_ambulance || null;
  const matchedHosp = c.assigned_hospital || null;

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
              <div style="font-size:1rem; font-weight:800; color:var(--accent-cyan);">${Utils.escapeHtml(c.recommended_ambulance === 'UNKNOWN' ? 'UNKNOWN / REVIEW REQUIRED' : (c.recommended_ambulance || 'PENDING'))}</div>
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
              <span>AI Suggested: <strong>${Utils.escapeHtml(c.ai_suggested_severity || c.priority)}</strong> (${Utils.escapeHtml(c.ai_suggested_ambulance === 'UNKNOWN' ? 'UNKNOWN' : (c.ai_suggested_ambulance || 'PENDING'))})</span>
              <span>Deterministic Clinical Rule: <strong>${Utils.escapeHtml(c.deterministic_severity || c.priority)}</strong> (${Utils.escapeHtml(c.deterministic_ambulance === 'UNKNOWN' ? 'UNKNOWN' : (c.deterministic_ambulance || 'PENDING'))})</span>
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
                <div style="font-size:0.82rem; color:var(--text-secondary);">Driver: <strong>${assignedAmb.driver_name || 'Assigned'}</strong> (${assignedAmb.contact_number || 'N/A'})</div>
                ${c.eta_minutes ? `<div style="font-size:0.82rem; color:var(--accent-cyan); margin-top:4px;">⏱️ ETA: <strong>~${Math.round(c.eta_minutes)} min</strong> (${(c.ambulance_distance_km || 0).toFixed(1)} km)</div>` : ''}
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
                ${c.hospital_distance_km ? `<div style="font-size:0.82rem; color:var(--accent-cyan); margin-top:2px;">📍 Distance: <strong>${c.hospital_distance_km.toFixed(1)} km</strong></div>` : ''}
              ` : `
              <div style="color:var(--text-muted); font-size:0.85rem;">No hospital matched yet. Run Dispatch to assign nearest capable hospital.</div>
              `}
            </div>
          </div>

          <div style="display:flex; justify-content:flex-end; gap:10px; flex-wrap:wrap; align-items:center;">
            ${c.status === 'DISPATCHED' ? `
              <span class="badge badge-dispatched" style="padding:8px 12px; font-weight:800;">🚑 DISPATCHED / EN ROUTE (ETA: ~${Math.round(c.eta_minutes || 8)} min)</span>
              <button class="btn btn-primary" onclick="markArrived()">📍 ARRIVED (At Scene)</button>
              <button class="btn" style="background:#7c3aed; color:#fff;" onclick="markCompleted()">✅ COMPLETED (Transfer Patient)</button>
              <button class="btn btn-outline btn-sm" onclick="simulateProgression()" title="Auto-advance En Route → Arrived → Completed">⚡ Auto-Simulate</button>
              <button class="btn btn-outline btn-sm" onclick="triggerDispatch()">🔄 Re-Dispatch</button>
            ` : (c.status === 'ARRIVED' ? `
              <span class="badge badge-arrived" style="padding:8px 12px; font-weight:800;">🚨 ARRIVED AT SCENE</span>
              <button class="btn btn-success" onclick="markCompleted()">✅ COMPLETED (Transfer & Close)</button>
              <button class="btn btn-outline btn-sm" onclick="triggerDispatch()">🔄 Re-Dispatch</button>
            ` : (c.status === 'RESOLVED' ? `
              <span class="badge badge-resolved" style="padding:8px 12px; font-weight:800;">✅ COMPLETED (Case Successfully Closed)</span>
            ` : `
              <button class="btn btn-success" style="font-weight:800; font-size:0.95rem; padding:10px 18px;" onclick="triggerDispatch()">
                🚀 CLICK "DISPATCH" (Assign Ambulance &amp; Hospital)
              </button>
            `))}
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
            ${renderConfidenceRow('Clinical Extraction', conf?.components?.extraction_completeness ?? conf?.components?.extraction_quality, '25%')}
            ${renderConfidenceRow('Deterministic Rule Agreement', conf?.components?.rule_llm_agreement ?? conf?.components?.rule_agreement, '20%')}
            ${renderConfidenceRow('Spatial Location Verification', conf?.components?.location_verification, '20%')}
            ${renderConfidenceRow('Resource Availability', conf?.components?.resource_availability, '15%')}
            ${renderConfidenceRow('Duplicate Certainty', conf?.components?.duplicate_certainty ?? conf?.components?.duplicate_penalty, '10%')}
            ${renderConfidenceRow('LLM Direct Confidence', conf?.components?.llm_confidence ?? conf?.components?.llm_direct_confidence, '10%')}
          </div>

          <div style="margin-top:16px; padding-top:14px; border-top:1px solid rgba(255,255,255,0.06); font-size:0.8rem; color:var(--text-secondary);">
            Requires Human Review: <strong style="color:${needsReview ? 'var(--accent-amber)' : 'var(--accent-emerald)'};">${needsReview ? '⚠️ YES' : 'NO'}</strong>
          </div>
        </div>

        <!-- Real Multi-Signal Duplicate Detection Card -->
        <div class="detail-section">
          <h4>🔍 Duplicate Detection</h4>
          ${(() => {
            const dup = c.duplicate_detection;
            if (!dup || (dup.status === 'NOT_DUPLICATE' && (!dup.score || dup.score < 0.20))) {
              return `
                <div style="background:#090e1b; border:1px solid var(--border-color); border-radius:var(--radius-md); padding:14px;">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:0.75rem; color:var(--text-muted); font-weight:700;">STATUS</span>
                    <span class="badge" style="background:#052e16; color:#4ade80; border:1px solid #166534; font-weight:700;">INDEPENDENT INCIDENT</span>
                  </div>
                  <div style="margin-top:8px; font-size:0.82rem; color:var(--text-secondary);">
                    Duplicate Score: <strong style="color:var(--accent-emerald);">${dup ? (dup.score).toFixed(2) : '0.00'}</strong> · No duplicate incident detected in candidate window.
                  </div>
                </div>
              `;
            }
            const statusColor = dup.status === 'DUPLICATE' ? 'var(--accent-red)' : dup.status === 'POSSIBLE_DUPLICATE' ? 'var(--accent-amber)' : 'var(--accent-blue)';
            const statusBg = dup.status === 'DUPLICATE' ? '#450a0a' : dup.status === 'POSSIBLE_DUPLICATE' ? '#451a03' : '#082f49';
            return `
              <div style="background:#090e1b; border:1px solid var(--border-color); border-radius:var(--radius-md); padding:14px; margin-bottom:12px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                  <span style="font-size:0.75rem; color:var(--text-muted); font-weight:700; text-transform:uppercase;">Status</span>
                  <span class="badge" style="background:${statusBg}; color:${statusColor}; border:1px solid ${statusColor}; font-weight:800; font-size:0.82rem;">
                    ${dup.status.replace('_', ' ')}
                  </span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:10px;">
                  <span style="font-size:0.8rem; color:var(--text-secondary);">Overall Duplicate Score:</span>
                  <span style="font-size:1.3rem; font-weight:900; color:${statusColor}; font-family:var(--font-mono);">
                    ${dup.score.toFixed(2)}
                  </span>
                </div>
                ${dup.matched_case_id ? `
                  <div style="font-size:0.82rem; color:var(--text-secondary); margin-bottom:12px; padding:8px 10px; background:#060a14; border-radius:6px;">
                    Matched Candidate Case: <a href="/staff/cases/${encodeURIComponent(dup.matched_case_id)}" style="font-family:var(--font-mono); font-weight:700; color:var(--accent-cyan);">CASE-${dup.matched_case_id.substring(0, 8)}</a>
                  </div>
                ` : ''}

                <!-- Signals Breakdown -->
                <div style="font-size:0.75rem; font-weight:700; color:var(--text-muted); text-transform:uppercase; margin-bottom:6px;">Signals</div>
                <div style="display:flex; flex-direction:column; gap:6px; font-size:0.8rem;">
                  <div style="display:flex; justify-content:space-between;">
                    <span style="color:var(--text-secondary);">Semantic similarity:</span>
                    <strong style="color:var(--text-primary); font-family:var(--font-mono);">${dup.semantic_similarity.toFixed(2)}</strong>
                  </div>
                  <div style="display:flex; justify-content:space-between;">
                    <span style="color:var(--text-secondary);">Location distance:</span>
                    <strong style="color:var(--text-primary); font-family:var(--font-mono);">${dup.geographic_distance_km !== null ? `${dup.geographic_distance_km.toFixed(1)} km` : 'Unverified location'}</strong>
                  </div>
                  <div style="display:flex; justify-content:space-between;">
                    <span style="color:var(--text-secondary);">Temporal difference:</span>
                    <strong style="color:var(--text-primary); font-family:var(--font-mono);">${Math.round(dup.temporal_diff_minutes)} min</strong>
                  </div>
                  <div style="display:flex; justify-content:space-between;">
                    <span style="color:var(--text-secondary);">Emergency type similarity:</span>
                    <strong style="color:var(--text-primary); font-family:var(--font-mono);">${dup.emergency_type_similarity.toFixed(2)}</strong>
                  </div>
                </div>

                <!-- Weighted Formula -->
                <div style="margin-top:12px; padding-top:10px; border-top:1px solid rgba(255,255,255,0.06); font-size:0.74rem; font-family:var(--font-mono); color:var(--text-muted);">
                  Weighted score:<br>
                  0.40×${dup.semantic_similarity.toFixed(2)} + 0.30×${dup.location_similarity.toFixed(2)} + 0.15×${dup.temporal_similarity.toFixed(2)} + 0.15×${dup.emergency_type_similarity.toFixed(2)}<br>
                  Final: <strong style="color:${statusColor}; font-size:0.85rem;">${dup.score.toFixed(2)}</strong>
                </div>

                <div style="margin-top:10px; font-size:0.8rem; color:var(--text-secondary); display:flex; justify-content:space-between;">
                  <span>Human Review:</span>
                  <strong style="color:${dup.requires_review ? 'var(--accent-amber)' : 'var(--accent-emerald)'};">
                    ${dup.requires_review ? '⚠️ Required' : 'Not Required'}
                  </strong>
                </div>
                ${dup.requires_review ? `
                  <button class="btn btn-outline btn-sm" style="width:100%; margin-top:10px; font-weight:700;" onclick="openReviewModal()">
                    Intervene: Confirm / Reject Duplicate
                  </button>
                ` : ''}
              </div>
            `;
          })()}
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
  // Use actual backend score; do NOT substitute a fake default (0.8 would be misleading)
  if (score === null || score === undefined) {
    return `
    <div class="conf-signal-row">
      <div class="conf-signal-meta">
        <span>${label} (${weight})</span>
        <span style="font-weight:700; color:var(--text-muted);">N/A</span>
      </div>
      <div class="conf-bar-wrap">
        <div class="conf-bar" style="width:0%; background:var(--text-muted);"></div>
      </div>
    </div>
    `;
  }
  const val = score;
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

  // Only show marker if we have REAL verified or geocoded coordinates
  const hasCoords = c.latitude && c.longitude && c.geocoding_status !== 'failed';
  if (!hasCoords) {
    mapEl.innerHTML = `
      <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; background:#090e1b; border-radius:var(--radius-md); color:var(--text-muted); gap:8px;">
        <span style="font-size:2rem;">📍</span>
        <span style="font-weight:700; color:var(--accent-amber);">Location Not Verified</span>
        <span style="font-size:0.82rem; text-align:center; max-width:260px;">
          ${c.location_error || 'No geocoded coordinates available. Dispatcher must set location manually using the Override Location button.'}
        </span>
        <button class="btn btn-outline btn-sm" style="margin-top:8px;" onclick="openLocationModal()">✏️ Set Coordinates</button>
      </div>
    `;
    return;
  }

  caseMiniMap = L.map('caseMiniMap').setView([c.latitude, c.longitude], 14);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '© OpenStreetMap contributors',
  }).addTo(caseMiniMap);

  const verifiedColor = c.is_location_verified ? '#22c55e' : '#f59e0b';
  L.circleMarker([c.latitude, c.longitude], {
    radius: 10,
    fillColor: verifiedColor,
    color: '#ffffff',
    weight: 2,
    fillOpacity: 0.95,
  }).addTo(caseMiniMap).bindPopup(
    `<strong>🚨 Incident Site</strong><br>${Utils.escapeHtml(c.extracted_location || '')}<br>` +
    `<small>${c.is_location_verified ? '✅ Verified' : '⚠️ Unverified — Dispatcher confirmation needed'}</small>`
  ).openPopup();
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
    const user = Auth.getUser();
    const dispatcher = user ? user.username : 'dispatcher_1';
    const match = await window.api.dispatchCase(currentCaseId, false, dispatcher, true);
    Utils.showToast(`✅ Dispatched ambulance: ${match.matched_ambulance?.vehicle_number || ''} (ETA: ${match.ambulance_eta_minutes ? match.ambulance_eta_minutes.toFixed(1) : '~8'} min)`, 'success');
    await loadCaseDetails();
  } catch (err) {
    alert('Dispatch failed: ' + err.message);
  }
};

window.markArrived = async function() {
  try {
    const user = Auth.getUser();
    const dispatcher = user ? user.username : 'dispatcher_1';
    Utils.showToast('Updating status: Ambulance Arrived at Scene…', 'info');
    await window.api.updateCaseStatus(currentCaseId, 'ARRIVED', 'Ambulance arrived at incident coordinates', dispatcher);
    Utils.showToast('🚨 Case updated: AMBULANCE ARRIVED AT SCENE', 'success');
    await loadCaseDetails();
  } catch (err) {
    alert('Failed to mark arrived: ' + err.message);
  }
};

window.markCompleted = async function() {
  try {
    const user = Auth.getUser();
    const dispatcher = user ? user.username : 'dispatcher_1';
    Utils.showToast('Completing emergency case and releasing ambulance to AVAILABLE…', 'info');
    await window.api.updateCaseStatus(currentCaseId, 'RESOLVED', 'Patient care transferred to hospital emergency department', dispatcher);
    Utils.showToast('✅ Emergency COMPLETED & patient transferred!', 'success');
    await loadCaseDetails();
  } catch (err) {
    alert('Failed to complete case: ' + err.message);
  }
};

window.simulateProgression = async function() {
  const user = Auth.getUser();
  const dispatcher = user ? user.username : 'dispatcher_1';
  Utils.showToast('⚡ Simulating response progression (En Route → Arrived → Completed)…', 'info', 4000);

  setTimeout(async () => {
    try {
      await window.api.updateCaseStatus(currentCaseId, 'ARRIVED', 'Live telemetry: unit arrived at incident scene', dispatcher);
      Utils.showToast('🚨 Telemetry: Unit ARRIVED at incident scene!', 'info', 3000);
      await loadCaseDetails();
    } catch (e) {
      console.error(e);
    }
  }, 3500);

  setTimeout(async () => {
    try {
      await window.api.updateCaseStatus(currentCaseId, 'RESOLVED', 'Live telemetry: patient safely transferred to hospital emergency department', dispatcher);
      Utils.showToast('✅ Telemetry: Incident COMPLETED! Patient in hospital care.', 'success', 4000);
      await loadCaseDetails();
    } catch (e) {
      console.error(e);
    }
  }, 8000);
};
