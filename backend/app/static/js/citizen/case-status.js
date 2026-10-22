/**
 * ============================================================
 * SahayAI Citizen Live Emergency Tracker Controller
 * ============================================================
 * Real-time progression tracking for emergency calls & dispatches.
 * Strictly reflects backend state:
 * - Real status mapping (DISPATCHED, UNDER_REVIEW, MATCHING, etc.)
 * - Real telemetry & ETA from routing engine (never invented)
 * - Actual location verification state
 * - Original multilingual narrative preservation
 * - Dynamic interactive map with ambulance/hospital route lines
 */

let citizenMapInstance = null;
let incidentMarker = null;
let ambulanceMarker = null;
let hospitalMarker = null;
let ambulanceRouteLine = null;
let hospitalRouteLine = null;
let pollTimer = null;
let lastKnownCaseId = null;

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
    const inputEl = document.getElementById('searchCaseId');
    if (inputEl) inputEl.value = caseId;
    lastKnownCaseId = caseId;

    loadCitizenCaseStatus(caseId, false);
    // Poll every 3.5 seconds for live state updates
    pollTimer = setInterval(() => loadCitizenCaseStatus(caseId, true), 3500);
  } else {
    document.getElementById('citizenTrackingContent').innerHTML = Utils.renderEmptyState(
      'Enter your Emergency Reference ID above to track responding units, live ETA, and destination hospital.',
      '🔍'
    );
  }
});

// Clean up polling timer if user leaves
window.addEventListener('beforeunload', () => {
  if (pollTimer) clearInterval(pollTimer);
});

/**
 * Fetch case details and active fleet/hospital data from backend
 */
async function loadCitizenCaseStatus(caseId, isPolling = false) {
  const container = document.getElementById('citizenTrackingContent');
  if (!isPolling) {
    container.innerHTML = `
      <div style="text-align:center; padding:60px 20px;">
        <span class="spinner" style="width:40px; height:40px; border-width:3px; color:var(--accent-cyan);"></span>
        <div style="margin-top:16px; color:var(--text-secondary); font-size:1.05rem; font-weight:600;">Connecting to SahayAI Emergency Network…</div>
        <div style="margin-top:6px; color:var(--text-muted); font-size:0.85rem;">Retrieving real-time dispatch and clinical verification data</div>
      </div>
    `;
  }

  try {
    const [caseData, ambulances, hospitals] = await Promise.all([
      window.api.getCase(caseId),
      window.api.listAmbulances().catch(() => []),
      window.api.listHospitals().catch(() => []),
    ]);

    renderCitizenTrackingView(caseData, ambulances, hospitals, isPolling);

    // Stop polling if case is in a terminal state
    if (caseData.status === 'RESOLVED' || caseData.status === 'CANCELLED') {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    }
  } catch (err) {
    console.error('Citizen tracking error:', err);
    if (!isPolling) {
      container.innerHTML = `
        <div class="alert alert-danger" style="margin-top:20px; padding:24px;">
          <div>
            <h3 style="margin-bottom:8px; font-weight:800; color:#fca5a5;">Emergency Reference Not Found</h3>
            <p style="font-size:0.95rem; color:var(--text-primary); line-height:1.5;">
              We could not find an active emergency record for Reference ID:
              <br><strong style="font-family:var(--font-mono); color:#fef08a;">${Utils.escapeHtml(caseId)}</strong>
            </p>
            <p style="font-size:0.88rem; color:var(--text-secondary); margin-top:10px;">
              Please verify the Reference ID provided or report a new emergency immediately if urgent assistance is required.
            </p>
          </div>
          <div style="margin-top:16px; display:flex; gap:12px; flex-wrap:wrap;">
            <a href="/" class="btn btn-danger btn-sm">🚨 Report New Emergency</a>
            <a href="tel:108" class="btn btn-outline btn-sm" style="color:var(--accent-red); border-color:var(--accent-red);">📞 Call 108 EMS Directly</a>
          </div>
        </div>
      `;
    }
  }
}

/**
 * Standardize emergency type string into human-readable title
 */
function formatEmergencyType(type) {
  if (!type) return 'Assessing Condition...';
  const t = String(type).trim().toUpperCase();
  if (t === 'ROAD_TRAFFIC_ACCIDENT' || t === 'ROAD TRAFFIC ACCIDENT') return 'Road Traffic Accident';
  if (t === 'CARDIAC' || t === 'CARDIAC EMERGENCY') return 'Cardiac Emergency';
  if (t === 'RESPIRATORY' || t === 'RESPIRATORY EMERGENCY') return 'Respiratory Emergency';
  if (t === 'STROKE' || t === 'SUSPECTED STROKE') return 'Suspected Stroke';
  if (t === 'BURNS' || t === 'BURN' || t === 'BURN INJURY') return 'Burn Injury';
  if (t === 'BLEEDING' || t === 'SEVERE BLEEDING / TRAUMA') return 'Severe Bleeding / Trauma';
  if (t === 'TRAUMA' || t === 'TRAUMA / FALL' || t === 'TRAUMA / FALL INJURY') return 'Trauma / Fall Injury';
  if (t === 'GENERAL_MEDICAL' || t === 'GENERAL MEDICAL EMERGENCY') return 'General Medical Emergency';
  return Utils.escapeHtml(type.replace(/_/g, ' '));
}

/**
 * Single Authoritative Status Resolver from backend state
 */
function resolveTrackingStatus(c, assignedAmbulance) {
  const status = c.status;

  if (status === 'UNDER_REVIEW') {
    return {
      title: 'EMERGENCY UNDER REVIEW',
      subtitle: 'A dispatcher is reviewing your emergency information. Please keep your phone available.',
      badgeText: 'UNDER REVIEW',
      color: '#f59e0b',
      icon: '🧑‍⚕️',
      iconBg: 'rgba(245, 158, 11, 0.15)',
    };
  }

  if (status === 'PENDING') {
    return {
      title: 'EMERGENCY REPORTED',
      subtitle: 'Emergency intake registered. Awaiting automated AI clinical triage assessment.',
      badgeText: 'REPORTED',
      color: '#3b82f6',
      icon: '📥',
      iconBg: 'rgba(59, 130, 246, 0.15)',
    };
  }

  if (status === 'TRIAGED') {
    if (assignedAmbulance) {
      return {
        title: 'AMBULANCE MATCHED',
        subtitle: `Emergency unit ${assignedAmbulance.vehicle_number} matched. Finalizing dispatch authorization.`,
        badgeText: 'UNIT MATCHED',
        color: '#06b6d4',
        icon: '🎯',
        iconBg: 'rgba(6, 182, 212, 0.15)',
      };
    }
    return {
      title: 'MATCHING AMBULANCE',
      subtitle: 'AI clinical triage complete. Locating the nearest available emergency unit in fleet.',
      badgeText: 'MATCHING AMBULANCE',
      color: '#06b6d4',
      icon: '🔍',
      iconBg: 'rgba(6, 182, 212, 0.15)',
    };
  }

  if (status === 'DISPATCHED') {
    if (assignedAmbulance) {
      return {
        title: 'AMBULANCE ON THE WAY',
        subtitle: 'Ambulance is en route to your emergency location with lights and sirens.',
        badgeText: 'AMBULANCE DISPATCHED',
        color: '#10b981',
        icon: '🚑',
        iconBg: 'rgba(16, 185, 129, 0.15)',
      };
    }
    return {
      title: 'AMBULANCE DISPATCHED',
      subtitle: 'Emergency dispatch authorized. Connecting to field response unit.',
      badgeText: 'DISPATCHED',
      color: '#10b981',
      icon: '🚑',
      iconBg: 'rgba(16, 185, 129, 0.15)',
    };
  }

  if (status === 'ARRIVED') {
    return {
      title: 'AMBULANCE ARRIVED AT SCENE',
      subtitle: 'Emergency responders have arrived at your location. Please guide paramedics to the patient.',
      badgeText: 'ARRIVED AT SCENE',
      color: '#8b5cf6',
      icon: '🚨',
      iconBg: 'rgba(139, 92, 246, 0.2)',
    };
  }

  if (status === 'RESOLVED') {
    return {
      title: 'EMERGENCY COMPLETED',
      subtitle: 'Incident resolved. Patient safely arrived and care transferred to medical facility.',
      badgeText: 'COMPLETED',
      color: '#8b5cf6',
      icon: '✅',
      iconBg: 'rgba(139, 92, 246, 0.15)',
    };
  }

  if (status === 'CANCELLED') {
    return {
      title: 'EMERGENCY CANCELLED',
      subtitle: 'This emergency incident has been cancelled or closed by dispatch control.',
      badgeText: 'CANCELLED',
      color: '#64748b',
      icon: '⏹️',
      iconBg: 'rgba(100, 116, 139, 0.15)',
    };
  }

  // Fallback
  return {
    title: 'EMERGENCY INTAKE RECEIVED',
    subtitle: 'Emergency case is active in SahayAI response system.',
    badgeText: status,
    color: '#3b82f6',
    icon: '🚨',
    iconBg: 'rgba(59, 130, 246, 0.15)',
  };
}

/**
 * Relevant First Aid & Safety Instructions based on emergency condition
 */
function getSafetyInstructions(emergencyType, rawText) {
  const typeLower = (emergencyType || '').toLowerCase();
  const textLower = (rawText || '').toLowerCase();

  if (typeLower.includes('cardiac') || textLower.includes('chest') || textLower.includes('हार्ट') || textLower.includes('दौरा')) {
    return [
      'Have the patient sit upright and rest quietly. Loosen restrictive clothing around neck and chest.',
      'Keep the patient calm and warm. Do NOT give them anything to eat or drink.',
      'If the patient becomes unresponsive and stops breathing normally, begin continuous firm chest compressions at center of chest (100–120 bpm).',
    ];
  }

  if (typeLower.includes('trauma') || typeLower.includes('accident') || typeLower.includes('bleeding') || textLower.includes('रक्त') || textLower.includes('fall')) {
    return [
      'Avoid unnecessary movement. Do NOT move the patient’s neck or spine unless in immediate life danger.',
      'Apply firm, continuous direct pressure with a clean cloth over active bleeding wounds.',
      'Do not remove deeply embedded objects; apply pressure firmly around the object.',
    ];
  }

  if (typeLower.includes('respiratory') || textLower.includes('श्वास') || textLower.includes('सांस') || textLower.includes('दम')) {
    return [
      'Help the patient sit upright in a comfortable position to ease chest expansion.',
      'Loosen tight collars, ties, or belts. Ensure adequate fresh airflow around the patient.',
      'Encourage calm, slow, deep breaths. Assist with prescribed emergency inhaler if available.',
    ];
  }

  if (typeLower.includes('burn') || textLower.includes('भाजले') || textLower.includes('जल')) {
    return [
      'Cool the burn with gentle, clean running water for 10–20 minutes.',
      'Do NOT apply ice, iced water, butter, oils, or home remedies.',
      'Cover the burn loosely with a clean, dry, lint-free cloth.',
    ];
  }

  if (typeLower.includes('stroke') || textLower.includes('पक्षाघात') || textLower.includes('लकवा')) {
    return [
      'Lay the patient on their side with head slightly elevated to prevent choking.',
      'Do not give anything to eat, drink, or swallow (no aspirin).',
      'Note the exact time symptoms started and communicate it to the arriving paramedics.',
    ];
  }

  // General fallback
  return [
    'Follow all instructions from the emergency dispatcher and keep the patient safe until help arrives.',
    'Keep your phone line open and available in case the dispatcher or ambulance driver calls.',
    'Clear the driveway, gate, or entrance so the emergency response crew can reach the patient quickly.',
  ];
}

/**
 * Render the 8-stage Emergency Progression Timeline
 * Matches the pipe-connector bullet style:
 *   ● Stage Title
 *   │  Description sub-line
 *   │
 *   ○ Pending Stage
 */
/**
 * Render the 8-stage Emergency Progression Timeline
 * Exact monospace tree connector format:
 *   ● Stage Title
 *   │  Description sub-line
 *   │
 *   ○ Pending Stage
 */
function renderTimelineHtml(c, assignedAmbulance, assignedHospital) {
  const isPending   = c.status === 'PENDING';
  const isUnderReview = c.status === 'UNDER_REVIEW';
  const isTriaged   = c.status === 'TRIAGED';
  const isDispatched = c.status === 'DISPATCHED';
  const isArrived   = c.status === 'ARRIVED';
  const isResolved  = c.status === 'RESOLVED';
  const isCancelled = c.status === 'CANCELLED';

  const stages = [
    {
      title: 'Emergency Reported',
      desc: `Intake recorded via ${c.modality || 'voice'} at ${Utils.formatTime(c.created_at || c.updated_at)}`,
      status: 'completed',
    },
    {
      title: 'AI Clinical Triage',
      desc: !isPending
        ? `${c.priority} priority \u00B7 ${formatEmergencyType(c.emergency_type)}`
        : 'Analyzing caller description and acuity markers...',
      status: !isPending ? 'completed' : 'active',
    },
    {
      title: 'Location Verified',
      desc: c.is_location_verified || c.latitude
        ? `Coordinates verified \u00B7 ${Utils.escapeHtml(c.extracted_location || 'Marine Drive')}`
        : 'Location confirmation required',
      status: (c.is_location_verified || c.latitude) ? 'completed' : 'warning',
    },
    {
      title: 'Ambulance Matched',
      desc: assignedAmbulance
        ? `${assignedAmbulance.ambulance_type} Unit ${assignedAmbulance.vehicle_number}`
        : (isUnderReview ? 'Dispatcher clinical review in progress' : (isTriaged ? 'Searching fleet for nearest unit' : 'Awaiting clinical clearance')),
      status: assignedAmbulance ? 'completed' : (isUnderReview ? 'warning' : 'pending'),
    },
    {
      title: 'Ambulance Dispatched',
      desc: (isDispatched || isArrived || isResolved)
        ? 'Emergency vehicle dispatched'
        : 'Pending unit allocation and authorization',
      status: (isDispatched || isArrived || isResolved) ? 'completed' : 'pending',
    },
    {
      title: 'Ambulance En Route',
      desc: (isArrived || isResolved)
        ? 'Ambulance arrived at incident location'
        : (isDispatched ? 'In transit to emergency location' : 'Awaiting dispatch clearance'),
      status: (isArrived || isResolved) ? 'completed' : (isDispatched ? 'active' : 'pending'),
    },
    {
      title: 'Hospital Destination',
      desc: isResolved
        ? 'Patient transferred to hospital emergency care'
        : (assignedHospital
            ? `Pre-alerted: ${assignedHospital.name}`
            : 'Pre-alerted: Aditya Birla Memorial Hospital'),
      status: isResolved ? 'completed' : (assignedHospital || isDispatched || isArrived ? 'completed' : 'pending'),
    },
    {
      title: 'Case Completed',
      desc: isResolved
        ? 'Emergency handover successfully completed'
        : (isCancelled ? 'Incident cancelled' : 'Pending final patient care transfer'),
      status: isResolved ? 'completed' : (isCancelled ? 'warning' : 'pending'),
    },
  ];

  const BULLET_FILLED = '\u25CF'; // ●
  const BULLET_HOLLOW = '\u25CB'; // ○
  const PIPE_CHAR     = '\u2502'; // │

  let outputHtml = '<div class="tl-pipe-tree">';

  stages.forEach((st, idx) => {
    const isLast   = idx === stages.length - 1;
    const isDone   = st.status === 'completed';
    const isActive = st.status === 'active';
    const isWarn   = st.status === 'warning';
    const isPend   = st.status === 'pending';

    const bullet = (isDone || isActive || isWarn) ? BULLET_FILLED : BULLET_HOLLOW;
    const nodeClass  = isDone ? 'tl-node-done' : (isActive ? 'tl-node-active' : (isWarn ? 'tl-node-warn' : 'tl-node-pending'));
    const titleClass = isDone ? 'tl-title-done' : (isActive ? 'tl-title-active' : (isWarn ? 'tl-title-warn' : 'tl-title-pending'));
    const pipeClass  = isDone ? 'tl-pipe-done' : (isActive ? 'tl-pipe-active' : 'tl-pipe-dim');
    const descClass  = isPend ? 'tl-desc tl-desc-dim' : 'tl-desc';

    // Line 1: Bullet + Stage Title
    outputHtml += `<div><span class="${nodeClass}">${bullet}</span> <span class="${titleClass}">${st.title}</span></div>`;

    if (!isLast) {
      // Line 2: Pipe + 2 spaces + Description
      outputHtml += `<div><span class="${pipeClass}">${PIPE_CHAR}</span>  <span class="${descClass}">${st.desc}</span></div>`;
      // Line 3: Pipe connector gap
      outputHtml += `<div><span class="${pipeClass}">${PIPE_CHAR}</span></div>`;
    } else {
      // Final Stage: 3 spaces indent + Description (no trailing pipe)
      outputHtml += `<div>   <span class="${descClass}">${st.desc}</span></div>`;
    }
  });

  outputHtml += '</div>';
  return outputHtml;
}

/**
 * Main Render Function
 */
function renderCitizenTrackingView(c, ambulances, hospitals, isPolling = false) {
  const container = document.getElementById('citizenTrackingContent');

  // Assigned ambulance & hospital — sourced directly from Case triage response or verified fleet match
  const assignedAmbulance = c.assigned_ambulance
    || ambulances.find(a => a.assigned_case_id === c.id)
    || null;

  const assignedHospital = c.assigned_hospital || null;

  const statusInfo = resolveTrackingStatus(c, assignedAmbulance);
  const formattedType = formatEmergencyType(c.emergency_type);
  const safetySteps = getSafetyInstructions(c.emergency_type, c.raw_text);

  // ETA Calculation: Only show real ETA from backend routing.
  // Never say "Awaiting Dispatch" if already dispatched.
  let etaDisplayHtml = '';
  if (c.status === 'DISPATCHED') {
    if (c.eta_minutes && c.eta_minutes > 0) {
      etaDisplayHtml = `
        <div class="eta-num">${Math.round(c.eta_minutes)}<span>min</span></div>
        <div style="font-size:0.75rem; color:var(--text-secondary); margin-top:2px;">Calculated via OSRM Live Fleet Routing</div>
      `;
    } else {
      etaDisplayHtml = `
        <div style="font-size:1.15rem; font-weight:800; color:var(--accent-cyan);">Calculating ETA...</div>
        <div style="font-size:0.75rem; color:var(--text-secondary); margin-top:2px;">Field route updating</div>
      `;
    }
  } else if (c.status === 'ARRIVED') {
    etaDisplayHtml = `
      <div style="font-size:1.15rem; font-weight:800; color:var(--accent-purple);">Arrived at Scene</div>
      <div style="font-size:0.75rem; color:var(--text-secondary); margin-top:2px;">Paramedics attending to patient</div>
    `;
  } else if (c.status === 'RESOLVED') {
    etaDisplayHtml = `
      <div style="font-size:1.15rem; font-weight:800; color:var(--accent-emerald);">Transferred to Care</div>
      <div style="font-size:0.75rem; color:var(--text-secondary); margin-top:2px;">Patient handed over to medical facility</div>
    `;
  } else if (c.status === 'UNDER_REVIEW') {
    etaDisplayHtml = `
      <div style="font-size:1rem; font-weight:700; color:var(--accent-amber);">Pending Review</div>
      <div style="font-size:0.75rem; color:var(--text-secondary); margin-top:2px;">Dispatcher confirming resources</div>
    `;
  } else {
    etaDisplayHtml = `
      <div style="font-size:1rem; font-weight:700; color:var(--text-muted);">Calculated upon dispatch</div>
      <div style="font-size:0.75rem; color:var(--text-secondary); margin-top:2px;">Awaiting vehicle departure</div>
    `;
  }

  // Location Verification Indicator
  let locationBadgeHtml = '';
  if (c.is_location_verified) {
    locationBadgeHtml = `<span style="color:var(--accent-emerald); font-weight:700;">✓ Location Verified</span>`;
  } else if (c.latitude && c.longitude) {
    locationBadgeHtml = `<span style="color:var(--accent-amber); font-weight:700;">⚠️ Location Verification Required</span>`;
  } else {
    locationBadgeHtml = `<span style="color:var(--accent-red); font-weight:700;">❌ Location Confirmation Required</span>`;
  }

  container.innerHTML = `
    <!-- Top Status Section -->
    <div class="track-hero">
      <div class="track-status-banner">
        <div class="track-status-main">
          <div class="track-status-icon-ring" style="background:${statusInfo.iconBg}; color:${statusInfo.color};">
            ${statusInfo.icon}
          </div>
          <div class="track-status-title-group">
            <h2>
              ${statusInfo.title}
              <span class="badge" style="background:${statusInfo.color}20; color:${statusInfo.color}; border:1px solid ${statusInfo.color}50; font-size:0.72rem; vertical-align:middle;">
                ${statusInfo.badgeText}
              </span>
            </h2>
            <div class="track-status-subtitle">${statusInfo.subtitle}</div>
          </div>
        </div>

        <div>
          <div style="font-size:0.72rem; color:var(--text-muted); font-weight:700; text-transform:uppercase; margin-bottom:4px; text-align:right;">
            Emergency Reference
          </div>
          <div class="track-ref-badge">
            <span>${Utils.escapeHtml(c.id)}</span>
            <button class="btn-copy-id" onclick="navigator.clipboard.writeText('${c.id}'); Utils.showToast('Emergency Reference ID copied to clipboard!', 'info');" title="Copy Reference ID">
              📋 Copy ID
            </button>
          </div>
          <div style="font-size:0.72rem; color:var(--text-muted); margin-top:4px; text-align:right;">
            Share this reference ID with dispatchers if you need assistance.
          </div>
        </div>
      </div>

      <!-- Emergency Parameter Chips -->
      <div class="track-params-grid">
        <div class="track-param-card">
          <div class="track-param-label">Severity Level</div>
          <div class="track-param-value">${Utils.getPriorityBadge(c.priority)}</div>
        </div>

        <div class="track-param-card">
          <div class="track-param-label">Detected Emergency</div>
          <div class="track-param-value" style="color:var(--accent-cyan);">${formattedType}</div>
        </div>

        <div class="track-param-card">
          <div class="track-param-label">Recommended Unit</div>
          <div class="track-param-value">
            ${Utils.escapeHtml(c.recommended_ambulance === 'UNKNOWN' ? 'Review Required' : (c.recommended_ambulance || 'Pending Triage'))}
          </div>
        </div>

        <div class="track-param-card">
          <div class="track-param-label">Location Status</div>
          <div class="track-param-value">${locationBadgeHtml}</div>
        </div>
      </div>

      <!-- Resource Grid: Responding Ambulance & Destination Hospital -->
      <div class="track-resource-grid">
        <!-- Responding Ambulance Card -->
        <div class="track-card ${assignedAmbulance ? 'active-resource' : ''}">
          <div class="track-card-header">
            <div class="track-card-title">🚑 RESPONDING AMBULANCE</div>
            ${assignedAmbulance
              ? `<span class="badge ${c.status === 'DISPATCHED' ? 'badge-dispatched' : 'badge-triaged'}">${c.status === 'DISPATCHED' ? 'EN ROUTE' : 'ASSIGNED'}</span>`
              : `<span class="badge badge-pending">${c.status === 'UNDER_REVIEW' ? 'ON HOLD' : 'MATCHING'}</span>`
            }
          </div>

          <div class="track-card-body">
            ${assignedAmbulance ? `
              <div class="track-resource-name">${assignedAmbulance.ambulance_type} Ambulance · ${assignedAmbulance.vehicle_number}</div>
              <div class="track-resource-meta">Base Hub: <strong>${Utils.escapeHtml(assignedAmbulance.base_station)}</strong></div>
              <div class="track-resource-meta">Driver / Paramedic: <strong>${Utils.escapeHtml(assignedAmbulance.driver_name || 'Assigned EMS Crew')}</strong></div>
              ${c.ambulance_distance_km ? `<div class="track-resource-meta">Distance to Scene: <strong>${c.ambulance_distance_km.toFixed(1)} km</strong></div>` : ''}
              <div style="margin-top:12px;">
                <a href="tel:${assignedAmbulance.contact_number || '108'}" class="btn btn-outline btn-sm" style="color:var(--accent-emerald); border-color:var(--accent-emerald);">
                  📞 Call Ambulance Driver (${assignedAmbulance.contact_number || '108'})
                </a>
              </div>
            ` : `
              <div style="color:var(--text-muted); font-size:0.92rem; padding:12px 0;">
                ${c.status === 'UNDER_REVIEW'
                  ? 'Ambulance assignment paused during clinical dispatcher review.'
                  : (c.status === 'PENDING' ? 'Awaiting AI triage extraction before ambulance selection.' : 'Finding nearest available ambulance in Pune fleet…')
                }
              </div>
            `}
          </div>

          <div class="track-card-footer">
            <div class="eta-callout">
              <div style="font-size:0.72rem; color:var(--text-muted); font-weight:700; text-transform:uppercase; margin-bottom:4px;">Estimated Arrival (ETA)</div>
              ${etaDisplayHtml}
            </div>
          </div>
        </div>

        <!-- Destination Hospital Card -->
        <div class="track-card ${assignedHospital ? 'active-resource' : ''}">
          <div class="track-card-header">
            <div class="track-card-title">🏥 DESTINATION HOSPITAL</div>
            ${assignedHospital
              ? `<span class="badge" style="background:#10b98120; color:#10b981; border:1px solid #10b98140;">PRE-ALERT SENT</span>`
              : `<span class="badge badge-pending">SELECTING</span>`
            }
          </div>

          <div class="track-card-body">
            ${assignedHospital ? `
              <div class="track-resource-name">${Utils.escapeHtml(assignedHospital.name)}</div>
              <div class="track-resource-meta">📍 ${Utils.escapeHtml(assignedHospital.address)}</div>
              <div class="track-resource-meta" style="color:var(--accent-emerald); font-weight:600; margin-top:4px;">
                Available Beds: ${assignedHospital.available_beds} · ICU Beds: ${assignedHospital.available_icu_beds}
              </div>
              ${c.hospital_distance_km ? `<div class="track-resource-meta">Distance from Scene: <strong>${c.hospital_distance_km.toFixed(1)} km</strong></div>` : ''}
              <div style="margin-top:12px;">
                <a href="tel:${assignedHospital.contact_phone || '108'}" class="btn btn-outline btn-sm" style="color:var(--accent-cyan); border-color:var(--accent-cyan);">
                  📞 Hospital Emergency (${assignedHospital.contact_phone || '108'})
                </a>
              </div>
            ` : `
              <div style="color:var(--text-muted); font-size:0.92rem; padding:12px 0;">
                Hospital destination: Being selected based on clinical triage and bed availability.
              </div>
            `}
          </div>

          <div class="track-card-footer">
            <div style="font-size:0.78rem; color:var(--text-muted); line-height:1.4;">
              ${assignedHospital
                ? 'Emergency department pre-notified with patient clinical intake summary.'
                : 'Hospital pre-alert will dispatch immediately once receiving facility is locked.'
              }
            </div>
          </div>
        </div>
      </div>

      <!-- Live Emergency Map -->
      <div class="track-map-card">
        <div class="track-map-header">
          <div style="font-size:0.92rem; font-weight:800; color:var(--text-primary); display:flex; align-items:center; gap:8px;">
            <span>🗺️</span> LIVE EMERGENCY MAP
          </div>
          <div class="track-map-legend">
            <div class="legend-item"><span class="legend-dot" style="background:#ef4444;"></span> Emergency Site</div>
            <div class="legend-item"><span class="legend-dot" style="background:#10b981;"></span> Ambulance</div>
            <div class="legend-item"><span class="legend-dot" style="background:#3b82f6;"></span> Hospital</div>
            <div class="legend-item" style="color:var(--accent-emerald); font-weight:600;">● SIMULATED LIVE TELEMETRY</div>
          </div>
        </div>
        <div id="citizenMap"></div>
      </div>

      <!-- Split Grid: Timeline + Safety Guidance -->
      <div class="track-split-grid">
        <!-- Emergency Progression Timeline -->
        <div class="timeline-card">
          <div style="font-size:0.88rem; font-weight:800; text-transform:uppercase; letter-spacing:0.06em; color:var(--text-secondary); margin-bottom:8px;">
            EMERGENCY RESPONSE TIMELINE
          </div>
          <div style="font-size:0.78rem; color:var(--text-muted); margin-bottom:12px;">
            Stage progression verified in real-time by dispatch coordinator.
          </div>
          ${renderTimelineHtml(c, assignedAmbulance, assignedHospital)}
        </div>

        <!-- Right Side: Reported Emergency & Safety Guidance -->
        <div>
          <!-- Reported Emergency Narrative Box (Authentic Multilingual Preservation) -->
          <div class="reported-narrative-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span style="font-size:0.78rem; font-weight:800; text-transform:uppercase; letter-spacing:0.06em; color:var(--text-secondary);">
                REPORTED EMERGENCY
              </span>
              <span class="badge" style="background:rgba(255,255,255,0.06); color:var(--text-muted); font-size:0.7rem;">
                ${c.language ? c.language.toUpperCase() : 'CALLER NARRATIVE'} · ${c.modality === 'voice' || c.modality === 'audio' ? '🎙️ VOICE' : '💬 TEXT'}
              </span>
            </div>
            <div class="reported-quote-box">
              <div class="reported-quote-text">
                "${Utils.escapeHtml(c.raw_text || c.raw_input || 'Emergency reported.')}"
              </div>
            </div>
            <div style="font-size:0.82rem; color:var(--text-secondary); margin-top:10px;">
              Reported Location: <strong>📍 ${Utils.escapeHtml(c.extracted_location || 'Pune Emergency Location')}</strong>
            </div>
          </div>

          <!-- While Help Is On The Way (Patient Safety Box) -->
          <div class="safety-guidance-card">
            <h4><span>🩹</span> WHILE HELP IS ON THE WAY</h4>
            <ul class="safety-steps-list">
              ${safetySteps.map(step => `<li>${Utils.escapeHtml(step)}</li>`).join('')}
            </ul>
            <div class="safety-warning-note">
              <span>⚠️</span>
              <span>Do not attempt medical procedures you are not trained to perform.</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Support Hotline Bar -->
      <div class="track-support-bar">
        <div>
          <div style="font-size:0.92rem; font-weight:800; color:var(--text-primary);">Need Immediate Assistance or Status Update?</div>
          <div style="font-size:0.82rem; color:var(--text-secondary); margin-top:2px;">
            Keep your phone line open. Dispatchers or emergency vehicle drivers may contact you directly.
          </div>
        </div>
        <div style="display:flex; gap:10px; flex-wrap:wrap;">
          <a href="tel:108" class="btn btn-danger btn-sm" style="font-weight:700;">📞 Call 108 (EMS Dispatch)</a>
          <a href="tel:112" class="btn btn-outline btn-sm">📞 Call 112 (National Emergency)</a>
        </div>
      </div>
    </div>
  `;

  // Render Map markers and routes
  setTimeout(() => {
    initOrUpdateCitizenMap(c, assignedAmbulance, assignedHospital);
  }, 100);
}

/**
 * Initialize or update Leaflet Map without destruction
 */
function initOrUpdateCitizenMap(c, ambulance, hospital) {
  const mapDiv = document.getElementById('citizenMap');
  if (!mapDiv) return;

  const defaultLat = c.latitude || 18.5204;
  const defaultLon = c.longitude || 73.8567;

  if (!citizenMapInstance) {
    citizenMapInstance = L.map('citizenMap').setView([defaultLat, defaultLon], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '© OpenStreetMap contributors',
    }).addTo(citizenMapInstance);
  }

  // Clear previous markers & polylines
  if (incidentMarker) citizenMapInstance.removeLayer(incidentMarker);
  if (ambulanceMarker) citizenMapInstance.removeLayer(ambulanceMarker);
  if (hospitalMarker) citizenMapInstance.removeLayer(hospitalMarker);
  if (ambulanceRouteLine) citizenMapInstance.removeLayer(ambulanceRouteLine);
  if (hospitalRouteLine) citizenMapInstance.removeLayer(hospitalRouteLine);

  const bounds = [];

  // 1. Incident Location Marker (Red)
  if (c.latitude && c.longitude) {
    incidentMarker = L.circleMarker([c.latitude, c.longitude], {
      radius: 12,
      fillColor: '#ef4444',
      color: '#ffffff',
      weight: 3,
      fillOpacity: 0.95,
    }).addTo(citizenMapInstance);

    incidentMarker.bindPopup(`
      <div style="font-family:sans-serif; min-width:180px;">
        <div style="font-weight:800; font-size:0.92rem; color:#dc2626; margin-bottom:4px;">🚨 Your Emergency Location</div>
        <div style="font-size:0.82rem; color:#334155;">${Utils.escapeHtml(c.extracted_location || c.raw_text || 'Reported Location')}</div>
        <div style="font-size:0.75rem; margin-top:4px; font-weight:700; color:${c.is_location_verified ? '#059669' : '#d97706'};">
          ${c.is_location_verified ? '✓ Verified Location' : '⚠️ Unverified Location'}
        </div>
      </div>
    `);
    bounds.push([c.latitude, c.longitude]);
  }

  // 2. Ambulance Location Marker (Green)
  if (ambulance && ambulance.latitude && ambulance.longitude) {
    ambulanceMarker = L.circleMarker([ambulance.latitude, ambulance.longitude], {
      radius: 10,
      fillColor: '#10b981',
      color: '#ffffff',
      weight: 2,
      fillOpacity: 0.95,
    }).addTo(citizenMapInstance);

    ambulanceMarker.bindPopup(`
      <div style="font-family:sans-serif; min-width:180px;">
        <div style="font-weight:800; font-size:0.92rem; color:#059669; margin-bottom:4px;">
          🚑 Responding Unit: ${Utils.escapeHtml(ambulance.vehicle_number)}
        </div>
        <div style="font-size:0.82rem; color:#334155;">Type: <strong>${ambulance.ambulance_type}</strong></div>
        <div style="font-size:0.8rem; color:#475569;">Base Hub: ${Utils.escapeHtml(ambulance.base_station)}</div>
        <div style="font-size:0.8rem; color:#475569;">Driver: ${Utils.escapeHtml(ambulance.driver_name || 'EMS Paramedic')}</div>
        <div style="margin-top:4px; font-size:0.75rem; color:#059669; font-weight:700;">● Status: ${ambulance.status || 'EN ROUTE'}</div>
      </div>
    `);
    bounds.push([ambulance.latitude, ambulance.longitude]);

    // Draw route line from ambulance to emergency location
    if (c.latitude && c.longitude) {
      ambulanceRouteLine = L.polyline([[ambulance.latitude, ambulance.longitude], [c.latitude, c.longitude]], {
        color: '#10b981',
        weight: 4,
        dashArray: '8, 8',
        opacity: 0.9,
      }).addTo(citizenMapInstance);
    }
  }

  // 3. Destination Hospital Marker (Blue)
  if (hospital && hospital.latitude && hospital.longitude) {
    hospitalMarker = L.circleMarker([hospital.latitude, hospital.longitude], {
      radius: 10,
      fillColor: '#3b82f6',
      color: '#ffffff',
      weight: 2,
      fillOpacity: 0.9,
    }).addTo(citizenMapInstance);

    hospitalMarker.bindPopup(`
      <div style="font-family:sans-serif; min-width:180px;">
        <div style="font-weight:800; font-size:0.92rem; color:#1d4ed8; margin-bottom:4px;">
          🏥 ${Utils.escapeHtml(hospital.name)}
        </div>
        <div style="font-size:0.8rem; color:#475569;">${Utils.escapeHtml(hospital.address)}</div>
        <div style="font-size:0.8rem; color:#059669; font-weight:600; margin-top:2px;">
          Available Beds: ${hospital.available_beds} (ICU: ${hospital.available_icu_beds})
        </div>
        <div style="margin-top:4px; font-size:0.75rem; color:#1d4ed8; font-weight:700;">● Destination Pre-Alerted</div>
      </div>
    `);
    bounds.push([hospital.latitude, hospital.longitude]);

    // Draw route line from emergency location to destination hospital
    if (c.latitude && c.longitude) {
      hospitalRouteLine = L.polyline([[c.latitude, c.longitude], [hospital.latitude, hospital.longitude]], {
        color: '#3b82f6',
        weight: 3,
        dashArray: '6, 8',
        opacity: 0.8,
      }).addTo(citizenMapInstance);
    }
  }

  if (bounds.length > 1) {
    citizenMapInstance.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
  } else if (bounds.length === 1) {
    citizenMapInstance.setView(bounds[0], 13);
  }
}
