// ============================================================
// SahayAI Emergency — Complete Interactive Dispatcher Frontend
// ============================================================

// ── AUTH ─────────────────────────────────────────────────────
let authToken = localStorage.getItem('sahayai_token') || null;
let mapInstance = null;
let currentCaseId = null;

async function ensureAuth() {
  if (authToken) return authToken;
  try {
    const res = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'dispatcher1', password: 'dispatcher123' }),
    });
    if (res.ok) {
      const d = await res.json();
      authToken = d.access_token;
      localStorage.setItem('sahayai_token', authToken);
      document.getElementById('authStatusBadge').textContent = '🔓 dispatcher1';
      document.getElementById('authStatusBadge').style.background = 'rgba(16,185,129,0.25)';
      document.getElementById('authStatusBadge').style.color = '#6ee7b7';
    }
  } catch (e) {
    console.warn('Auto-auth failed', e);
    document.getElementById('authStatusBadge').textContent = '⚠️ Auth Failed';
    document.getElementById('authStatusBadge').style.background = 'rgba(239,68,68,0.2)';
  }
  return authToken;
}

async function apiFetch(url, opts = {}) {
  await ensureAuth();
  const headers = { ...(opts.headers || {}) };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
  // Don't set Content-Type for FormData (browser sets boundary)
  if (!(opts.body instanceof FormData)) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }
  const r = await fetch(url, { ...opts, headers });
  if (r.status === 401) {
    authToken = null; localStorage.removeItem('sahayai_token');
    await ensureAuth();
    return fetch(url, { ...opts, headers: { ...headers, Authorization: `Bearer ${authToken}` } });
  }
  return r;
}

// ── NAVIGATION ────────────────────────────────────────────────
const PAGE_TITLES = {
  'view-dashboard':   'Operations Command Overview',
  'view-intake':      '🆘 Create Emergency — Multi-lingual Intake',
  'view-review':      'Human-in-the-Loop Review Queue',
  'view-cases':       'All Emergency Cases',
  'view-case-detail': 'Case Provenance & Pipeline',
  'view-map':         'Pune Regional Fleet & Hospital Map',
  'view-escalations': 'SLA Threshold Escalations',
  'view-fairness':    'Multilingual Demographic Fairness',
  'view-audit':       'Immutable System Audit Trail',
};

function switchView(viewId) {
  document.querySelectorAll('.view-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const panel = document.getElementById(viewId);
  if (panel) panel.classList.add('active');
  const nav = document.querySelector(`[data-view="${viewId}"]`);
  if (nav) nav.classList.add('active');
  document.getElementById('pageTitle').textContent = PAGE_TITLES[viewId] || 'SahayAI Emergency';

  if (viewId === 'view-map') { loadMapData(); setTimeout(() => mapInstance?.invalidateSize(), 250); }
  if (viewId === 'view-fairness') loadFairnessData();
  if (viewId === 'view-audit') loadAuditLogs();
  if (viewId === 'view-escalations') { loadEscalationsData(); loadSLATimers(); }
  if (viewId === 'view-review') loadReviewQueue();
  if (viewId === 'view-cases') loadAllCases();
}

function setupNavigation() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => switchView(item.dataset.view));
  });
}

// ── INIT ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  setupNavigation();
  setupIntakeForm();
  setupReviewModal();
  initMap();

  if (window.location.pathname.includes('/dashboard') || window.location.hash === '#dashboard') {
    switchView('view-dashboard');
  } else {
    switchView('view-intake');
  }

  await ensureAuth();
  await loadDashboardData();
  setInterval(loadDashboardData, 30000);
  document.getElementById('lastRefresh').textContent = 'Auto-refresh: every 30s';
});

// ── DASHBOARD KPIs ────────────────────────────────────────────
async function loadDashboardData() {
  try {
    const [casesRes, reviewRes, escRes, slaRes] = await Promise.all([
      apiFetch('/api/v1/cases?limit=100'),
      fetch('/api/v1/review/queue'),
      fetch('/api/v1/sla/escalations?unresolved_only=true'),
      fetch('/api/v1/sla/status'),
    ]);
    const casesList  = await casesRes.json().then(d => Array.isArray(d) ? d : []).catch(() => []);
    const reviewList = await reviewRes.json().then(d => Array.isArray(d) ? d : []).catch(() => []);
    const escList    = await escRes.json().then(d => Array.isArray(d) ? d : []).catch(() => []);
    const slaList    = await slaRes.json().then(d => Array.isArray(d) ? d : []).catch(() => []);

    document.getElementById('kpiCritical').textContent   = casesList.filter(c => c.priority === 'CRITICAL').length;
    document.getElementById('kpiReview').textContent     = reviewList.length;
    document.getElementById('kpiDispatched').textContent = casesList.filter(c => c.status === 'DISPATCHED').length;
    document.getElementById('kpiTotal').textContent      = casesList.length;
    document.getElementById('kpiBreaches').textContent   = slaList.filter(s => s.is_breached).length;
    document.getElementById('badgeReviewCount').textContent     = reviewList.length;
    document.getElementById('badgeEscalationCount').textContent = escList.length;
    renderDashboardTable(casesList, slaList);
    document.getElementById('sysStatus').textContent = 'Online';
    document.getElementById('sysStatus').style.color = 'var(--accent-emerald)';
    document.getElementById('lastRefresh').textContent = 'Last refresh: ' + new Date().toLocaleTimeString('en-IN');
  } catch (err) {
    console.error('Dashboard load error:', err);
    document.getElementById('sysStatus').textContent = 'Offline';
    document.getElementById('sysStatus').style.color = 'var(--accent-red)';
  }
}

// Alias — same clean implementation
const loadDashboardDataSimple = loadDashboardData;

function slaFor(caseId, slaList) {
  return slaList.find(s => s.case_id === caseId);
}

function renderDashboardTable(cases, slaList = []) {
  const tbody = document.getElementById('tableDashboardBody');
  if (!cases.length) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:var(--text-muted); padding:28px;">
      No emergency cases yet. <a href="#" onclick="switchView('view-intake'); return false;" style="color:var(--accent-cyan);">Create one now →</a></td></tr>`;
    return;
  }
  tbody.innerHTML = cases.slice(0, 50).map(c => {
    // CaseTriageResponse uses 'id', 'priority', 'emergency_type', 'status', 'confidence_score'
    // raw narrative is accessible via extracted_location or we show emergency_type
    const narrative = c.extracted_location || c.emergency_type || '—';
    const rawText   = c.raw_text || c.raw_input || narrative;
    const sla = slaFor(c.id, slaList);
    const slaHtml = sla
      ? sla.is_breached
        ? `<span class="badge" style="background:#7f1d1d;color:#fca5a5;">BREACH ${Math.round(sla.elapsed_seconds/60)}m</span>`
        : sla.is_warning
          ? `<span class="badge badge-moderate">⚠️ ${Math.round(sla.elapsed_seconds/60)}m/${Math.round(sla.target_seconds/60)}m</span>`
          : `<span style="color:var(--accent-emerald); font-size:0.75rem;">${Math.round(sla.elapsed_seconds/60)}m</span>`
      : '<span style="color:var(--text-muted)">—</span>';
    return `<tr>
      <td><a href="#" onclick="inspectCase('${c.id}'); return false;" style="color:var(--accent-cyan); font-weight:700; font-family:monospace;">${c.id.substring(0,8)}…</a></td>
      <td><span class="badge badge-${(c.priority||'low').toLowerCase()}">${c.priority||'?'}</span></td>
      <td style="color:var(--text-secondary); max-width:120px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${c.emergency_type||'—'}</td>
      <td style="max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--text-secondary);" title="${esc(rawText)}">${esc(rawText)}</td>
      <td><span class="badge badge-${(c.status||'pending').toLowerCase()}">${c.status||'?'}</span></td>
      <td>${c.confidence_score != null ? `<div style="min-width:80px;">${(c.confidence_score*100).toFixed(0)}%<div class="conf-bar-wrap"><div class="conf-bar" style="width:${(c.confidence_score*100).toFixed(0)}%; background:${confColor(c.confidence_score)};"></div></div></div>` : '—'}</td>
      <td>${slaHtml}</td>
      <td>
        <div style="display:flex; gap:4px;">
          <button class="btn btn-outline btn-sm" onclick="inspectCase('${c.id}')">🔍 Inspect</button>
          ${c.status === 'UNDER_REVIEW' ? `<button class="btn btn-amber btn-sm" onclick="openReviewModal('${c.id}')">Review</button>` : ''}
        </div>
      </td>
    </tr>`;
  }).join('');
}

// ── INTAKE FORM ───────────────────────────────────────────────
const SAMPLES = {
  hindi: {
    text: 'मरीज को सांस लेने में बहुत दिक्कत हो रही है और छाती में दर्द है, पुणे में एम्बुलेंस चाहिए।',
    location: 'FC Road, Deccan Gymkhana, Pune',
    lat: '18.5204',
    lon: '73.8406',
    lang: 'hindi',
  },
  marathi: {
    text: 'अपघात झाला आहे, रुग्ण बेशुद्ध आहे, रक्ताचा स्त्राव होतोय, शिवाजीनगर पुणे लवकर या.',
    location: 'Shivajinagar Station, Pune',
    lat: '18.5314',
    lon: '73.8446',
    lang: 'marathi',
  },
  cardiac: {
    text: 'Patient collapsed at Swargate Bus Stand. Severe crushing chest pain radiating to left arm. Not breathing properly. Approx 55-year-old male. Please send ALS ambulance urgently!',
    location: 'Swargate Bus Stand, Pune',
    lat: '18.5018',
    lon: '73.8580',
    lang: 'english',
  },
  trauma: {
    text: 'Serious road accident near Pune-Mumbai Highway at Wakad junction. Two vehicles collided, heavy bleeding, one person unconscious. Need ALS ambulance immediately.',
    location: 'Wakad Junction, Pune-Mumbai Highway',
    lat: '18.5950',
    lon: '73.7620',
    lang: 'english',
  },
};

function fillSampleEmergency(type) {
  const s = SAMPLES[type];
  if (!s) return;
  document.getElementById('emergencyText').value = s.text;
  document.getElementById('locationText').value  = s.location;
  document.getElementById('latInput').value       = s.lat;
  document.getElementById('lonInput').value       = s.lon;
  if (s.lang && document.getElementById('languageSelect')) {
    document.getElementById('languageSelect').value = s.lang;
  }
}

function setupIntakeForm() {
  // Modality toggle
  document.querySelectorAll('input[name="modality"]').forEach(radio => {
    radio.addEventListener('change', () => {
      const isAudio = radio.value === 'audio';
      document.getElementById('textInputSection').style.display = isAudio ? 'none' : 'block';
      document.getElementById('audioInputSection').style.display = isAudio ? 'block' : 'none';
      document.querySelectorAll('.modality-btn').forEach(b => b.classList.remove('active'));
      radio.closest('.modality-btn').classList.add('active');
    });
  });

  // Browser Geolocation Detector
  document.getElementById('btnDetectGPS')?.addEventListener('click', () => {
    const btn = document.getElementById('btnDetectGPS');
    if (!navigator.geolocation) {
      document.getElementById('latInput').value = '18.5204';
      document.getElementById('lonInput').value = '73.8567';
      if (!document.getElementById('locationText').value) {
        document.getElementById('locationText').value = 'Pune City (Simulated GPS)';
      }
      return;
    }
    btn.textContent = '📍 Locating…';
    navigator.geolocation.getCurrentPosition(
      pos => {
        document.getElementById('latInput').value = pos.coords.latitude.toFixed(6);
        document.getElementById('lonInput').value = pos.coords.longitude.toFixed(6);
        if (!document.getElementById('locationText').value) {
          document.getElementById('locationText').value = `GPS Location (${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)})`;
        }
        btn.textContent = '✅ Located';
        setTimeout(() => { btn.textContent = '📍 Detect GPS'; }, 3000);
      },
      err => {
        // Safe fallback for local prototype testing if user denies permission or browser lacks GPS
        document.getElementById('latInput').value = '18.5204';
        document.getElementById('lonInput').value = '73.8567';
        if (!document.getElementById('locationText').value) {
          document.getElementById('locationText').value = 'Pune City Center (GPS Fallback)';
        }
        btn.textContent = '📍 Pune (Fallback)';
        setTimeout(() => { btn.textContent = '📍 Detect GPS'; }, 3000);
      },
      { timeout: 5000 }
    );
  });

  // Reset Demo Data Button
  document.getElementById('btnResetDemo')?.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to reset all demo emergency data?\n\nThis will clear all submitted cases and restore ambulances and hospitals to their baseline states.')) {
      return;
    }
    const btn = document.getElementById('btnResetDemo');
    btn.disabled = true;
    btn.textContent = '🔄 Resetting…';
    try {
      const res = await apiFetch('/api/v1/system/reset', { method: 'POST' });
      if (!res.ok) throw new Error('Reset request failed');
      const data = await res.json();
      alert('✅ ' + data.message);
      currentCaseId = null;
      await loadDashboardDataSimple();
      switchView('view-intake');
    } catch (e) {
      alert('Reset error: ' + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = '🔄 Reset Demo Data';
    }
  });

  document.getElementById('btnSubmitEmergency').addEventListener('click', submitEmergency);
  document.getElementById('btnNewEmergency').addEventListener('click', () => switchView('view-intake'));
  document.getElementById('btnRefresh').addEventListener('click', loadDashboardDataSimple);
  document.getElementById('btnCheckSLA').addEventListener('click', runSLACheck);
  document.getElementById('showResolvedEsc').addEventListener('change', loadEscalationsData);
  document.getElementById('caseStatusFilter').addEventListener('change', loadAllCases);
  document.getElementById('btnRunFairness').addEventListener('click', async () => {
    document.getElementById('tableFairnessBody').innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--accent-amber);">Running benchmark…</td></tr>';
    const res = await fetch('/api/v1/fairness/run-eval', { method: 'POST' });
    const data = await res.json();
    renderFairnessTable(data);
  });
}

async function submitEmergency() {
  const btn = document.getElementById('btnSubmitEmergency');
  const errBanner = document.getElementById('intakeErrorBanner');
  errBanner.style.display = 'none';

  const modality = document.querySelector('input[name="modality"]:checked')?.value || 'text';

  if (modality === 'text') {
    const text = document.getElementById('emergencyText').value.trim();
    if (!text) { showIntakeError('Emergency description is required.'); return; }

    btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Submitting…';
    try {
      await textEmergencyFlow(text);
    } finally { btn.disabled = false; btn.innerHTML = '🚨 Submit Emergency'; }
  } else {
    const file = document.getElementById('audioFile').files[0];
    if (!file) { showIntakeError('Please select an audio file.'); return; }
    btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Processing Audio…';
    try {
      await audioEmergencyFlow(file);
    } finally { btn.disabled = false; btn.innerHTML = '🚨 Submit Emergency'; }
  }
}

function showIntakeError(msg) {
  const b = document.getElementById('intakeErrorBanner');
  b.textContent = '⚠️ ' + msg;
  b.style.display = 'block';
}

// ── TEXT EMERGENCY FLOW ───────────────────────────────────────
async function textEmergencyFlow(text) {
  const location = document.getElementById('locationText').value.trim();
  const lat = parseFloat(document.getElementById('latInput').value) || null;
  const lon = parseFloat(document.getElementById('lonInput').value) || null;
  const phone = document.getElementById('callerPhone').value.trim() || null;

  const progressDiv = document.getElementById('intakeProgress');
  const stepsDiv    = document.getElementById('progressSteps');
  progressDiv.style.display = 'block';
  stepsDiv.innerHTML = '';

  const steps = [
    { id: 'step-create',    label: 'Creating Emergency Case', icon: '📥' },
    { id: 'step-triage',    label: 'Running AI Triage (LLM Extraction + Severity)', icon: '🧠' },
    { id: 'step-rag',       label: 'RAG Clinical Verification', icon: '📚' },
    { id: 'step-confidence',label: 'Multi-Signal Confidence Calculation', icon: '📊' },
    { id: 'step-location',  label: 'Location Verification / Geocoding', icon: '📍' },
    { id: 'step-resources', label: 'Ambulance & Hospital Matching', icon: '🚑' },
  ];

  steps.forEach(s => {
    stepsDiv.insertAdjacentHTML('beforeend', `
      <div class="prog-step" id="${s.id}">
        <span class="step-icon">⏳</span>
        <span>${s.label}</span>
        <span id="${s.id}-status" style="margin-left:auto; font-size:0.75rem; color:var(--text-muted);">Waiting…</span>
      </div>`);
  });

  let caseId = null;
  const setStep = (id, state, msg) => {
    const el = document.getElementById(id);
    const st = document.getElementById(id + '-status');
    if (!el) return;
    el.className = `prog-step ${state === 'done' ? 'step-done' : state === 'running' ? 'step-running' : 'step-fail'}`;
    el.querySelector('.step-icon').textContent = state === 'done' ? '✅' : state === 'running' ? '⚙️' : '❌';
    if (st) st.textContent = msg;
  };

  try {
    // Step 1 – Create Case
    setStep('step-create', 'running', 'Submitting…');
    const payload = {
      raw_text: text,
      raw_input: text,
      modality: 'text',
    };
    const lang = document.getElementById('languageSelect')?.value;
    if (lang) payload.language = lang;
    if (phone) payload.caller_phone = phone;
    if (location) payload.manual_location = location;
    if (lat != null && !isNaN(lat)) payload.latitude = lat;
    if (lon != null && !isNaN(lon)) payload.longitude = lon;

    const createRes = await fetch('/api/v1/cases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!createRes.ok) {
      const err = await createRes.json();
      throw new Error(err.detail?.message || JSON.stringify(err.detail) || 'Case creation failed');
    }
    const created = await createRes.json();
    caseId = created.id;
    currentCaseId = caseId;
    setStep('step-create', 'done', `Case ${caseId.substring(0,8)}…`);

    // Step 2 – AI Triage
    setStep('step-triage', 'running', 'Running LLM pipeline…');
    const triageRes = await fetch(`/api/v1/cases/${caseId}/triage`, { method: 'POST' });
    let triageData = null;
    if (triageRes.ok) {
      triageData = await triageRes.json();
      setStep('step-triage', 'done', `${triageData.priority||'?'} · ${triageData.emergency_type||'?'} · ${triageData.recommended_ambulance||'?'}`);
    } else {
      setStep('step-triage', 'fail', 'Triage failed (non-critical)');
    }

    // Step 3 – RAG Verification
    setStep('step-rag', 'running', 'Searching clinical knowledge base…');
    const ragRes = await fetch(`/api/v1/rag/cases/${caseId}/verify`, { method: 'POST' });
    if (ragRes.ok) {
      const ragData = await ragRes.json();
      setStep('step-rag', 'done', `${ragData.severity_confirmed ? '✓ Severity confirmed' : '⚠ Severity uncertain'} · ${ragData.evidence_count||0} evidence chunks`);
    } else {
      setStep('step-rag', 'fail', 'RAG unavailable (non-critical)');
    }

    // Step 4 – Confidence
    setStep('step-confidence', 'running', 'Calculating…');
    const confRes = await fetch(`/api/v1/review/${caseId}/confidence`);
    let confData = null;
    if (confRes.ok) {
      confData = await confRes.json();
      const pct = (confData.overall_confidence * 100).toFixed(0);
      setStep('step-confidence', 'done', `${pct}% (${confData.confidence_level}) · Review: ${confData.requires_human_review ? 'YES ⚠️' : 'No'}`);
    } else {
      setStep('step-confidence', 'fail', 'Confidence calc unavailable');
    }

    // Step 5 – Location
    setStep('step-location', 'running', 'Verifying location coordinates…');
    if (lat && lon && location) {
      const locPayload = { latitude: lat, longitude: lon, formatted_address: location };
      const locRes = await fetch(`/api/v1/cases/${caseId}/location?dispatcher_id=dispatcher_1`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(locPayload),
      });
      setStep('step-location', locRes.ok ? 'done' : 'fail', locRes.ok ? `Verified: ${location}` : 'Location patch failed');
    } else {
      setStep('step-location', 'done', triageData?.extracted_location ? `AI Extracted: ${triageData.extracted_location}` : 'Location verified');
    }

    // Step 6 – Resource Match & Dispatch
    if (confData && confData.requires_human_review) {
      setStep('step-resources', 'warn', '⚠️ Awaiting Human Dispatcher Review (Uncertainty flagged)');
    } else {
      setStep('step-resources', 'running', 'Finding nearest ambulance & hospital…');
      const matchRes = await fetch(`/api/v1/cases/${caseId}/dispatch`, { method: 'POST' });
      if (matchRes.ok) {
        const matchData = await matchRes.json();
        const amb = matchData.matched_ambulance;
        const hosp = matchData.matched_hospital;
        setStep('step-resources', 'done',
          `Dispatched: ${amb?.vehicle_number||'?'} → ${hosp?.name||'?'} · ETA ${matchData.ambulance_eta_minutes != null ? matchData.ambulance_eta_minutes.toFixed(1) : '?'} min`);
      } else {
        const err = await matchRes.json().catch(() => ({}));
        setStep('step-resources', 'fail', err.detail?.message || 'Ambulance match pending dispatcher review');
      }
    }

    // Navigate to Case Detail
    setTimeout(() => {
      inspectCase(caseId);
    }, 1500);

  } catch (err) {
    showIntakeError(err.message);
    if (caseId) setTimeout(() => inspectCase(caseId), 800);
  }
}

// ── AUDIO EMERGENCY FLOW ──────────────────────────────────────
async function audioEmergencyFlow(file) {
  const progressDiv = document.getElementById('intakeProgress');
  const stepsDiv    = document.getElementById('progressSteps');
  progressDiv.style.display = 'block';
  stepsDiv.innerHTML = `
    <div class="prog-step step-running" id="step-audio">
      <span class="step-icon">⚙️</span>
      <span>Transcribing audio & running full AI pipeline…</span>
    </div>`;

  try {
    const form = new FormData();
    form.append('audio_file', file);
    const phone = document.getElementById('callerPhone').value.trim();
    const loc   = document.getElementById('locationText').value.trim();
    const lang  = document.getElementById('languageHint')?.value || '';
    if (phone) form.append('caller_phone', phone);
    if (loc)   form.append('manual_location', loc);
    if (lang)  form.append('language_hint', lang);

    const res = await fetch('/api/v1/cases/audio', { method: 'POST', body: form });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail?.message || 'Audio upload failed');
    }
    const data = await res.json();
    document.getElementById('step-audio').className = 'prog-step step-done';
    document.getElementById('step-audio').querySelector('.step-icon').textContent = '✅';
    document.getElementById('step-audio').querySelector('span:nth-child(2)').textContent =
      `Done — ${data.priority} · ${data.emergency_type||'?'} · ${data.recommended_ambulance||'?'}`;

    setTimeout(() => inspectCase(data.id), 1200);
  } catch (err) {
    document.getElementById('step-audio').className = 'prog-step step-fail';
    document.getElementById('step-audio').querySelector('.step-icon').textContent = '❌';
    showIntakeError(err.message);
  }
}

// ── CASE INSPECTOR ────────────────────────────────────────────
async function inspectCase(caseId) {
  currentCaseId = caseId;
  switchView('view-case-detail');
  const container = document.getElementById('caseDetailContainer');
  container.innerHTML = `<div class="detail-section" style="text-align:center; padding:32px;"><span class="spinner" style="width:28px;height:28px;border-width:3px;"></span><div style="margin-top:12px; color:var(--text-secondary);">Loading case ${caseId.substring(0,8)}…</div></div>`;

  try {
    const [caseRes, confRes, timelineRes] = await Promise.all([
      apiFetch(`/api/v1/cases/${caseId}`),
      fetch(`/api/v1/review/${caseId}/confidence`),
      fetch(`/api/v1/audit/cases/${caseId}/timeline`),
    ]);

    if (!caseRes.ok) { container.innerHTML = errBox(`Case ${caseId} not found.`); return; }
    const c        = await caseRes.json();
    const conf     = confRes.ok ? await confRes.json() : null;
    const timeline = timelineRes.ok ? await timelineRes.json() : [];

    const pBadge = `<span class="badge badge-${(c.priority||'low').toLowerCase()}">${c.priority||'?'}</span>`;
    const sBadge = `<span class="badge badge-${(c.status||'pending').toLowerCase()}">${c.status||'?'}</span>`;
    const confPct = conf ? (conf.overall_confidence * 100).toFixed(0) : '—';
    const confColor_ = conf ? confColor(conf.overall_confidence) : 'var(--text-muted)';
    const needsReview = conf?.requires_human_review;

    container.innerHTML = `
      <!-- Review Banner -->
      ${needsReview ? `
        <div class="review-required-banner">
          <div class="icon">⚠️</div>
          <div>
            <div style="font-weight:700; color:var(--accent-amber); font-size:1rem;">Human Review Required</div>
            <div style="font-size:0.83rem; color:var(--text-secondary); margin-top:2px;">${esc(conf.review_trigger_reason||'Low confidence or contradictory signals detected')}</div>
          </div>
          <button class="btn btn-amber" style="margin-left:auto;" onclick="openReviewModal('${caseId}')">🧑‍⚕️ Review Now</button>
        </div>` : ''}

      <!-- Workflow Actions -->
      <div class="workflow-actions">
        <strong style="font-size:0.78rem; text-transform:uppercase; color:var(--text-muted); letter-spacing:0.05em; margin-right:4px;">Pipeline Actions:</strong>
        <button class="btn btn-primary btn-sm" onclick="runTriage('${caseId}')">🧠 Analyze / Triage</button>
        <button class="btn btn-outline btn-sm" onclick="runRAG('${caseId}')">📚 RAG Verify</button>
        <button class="btn btn-outline btn-sm" onclick="openLocationModal('${caseId}')">📍 Set Location</button>
        <button class="btn btn-outline btn-sm" onclick="viewCaseOnMap('${caseId}')">🗺️ View on Map</button>
        <button class="btn btn-success btn-sm" onclick="runDispatch('${caseId}')">🚑 Find &amp; Dispatch</button>
        ${c.status === 'UNDER_REVIEW' ? `<button class="btn btn-amber btn-sm" onclick="openReviewModal('${caseId}')">🧑‍⚕️ Human Review</button>` : ''}
        <button class="btn btn-outline btn-sm" onclick="loadAuditTimeline('${caseId}')">📜 Audit Timeline</button>
      </div>

      <div class="detail-grid">
        <div>
          <!-- Step 1: Intake -->
          <div class="detail-section">
            <h4>📥 Step 1: Emergency Intake &amp; Modality ${pBadge}</h4>
            <div class="pipeline-step">
              <div class="pipeline-step-title">📞 Raw Caller Narrative</div>
              <div class="pipeline-step-body" style="font-weight:600; font-size:0.95rem; line-height:1.6;">"${esc(c.raw_text||'')}"</div>
            </div>
            <div style="display:flex; gap:16px; font-size:0.8rem; color:var(--text-secondary); flex-wrap:wrap; margin-top:8px;">
              <span>Modality: <strong>${c.modality||'text'}</strong></span>
              <span>Language: <strong>${c.language||'—'}</strong></span>
              <span>Status: ${sBadge}</span>
              <span>Phone: <strong>${c.caller_phone||'—'}</strong></span>
              <span>Created: <strong>${fmtTime(c.created_at)}</strong></span>
            </div>
          </div>

          <!-- Step 2: AI Triage -->
          <div class="detail-section">
            <h4>🧠 Step 2: AI Hybrid Clinical Triage</h4>
            <div class="pipeline-step step-${c.priority==='CRITICAL'?'error':c.priority==='HIGH'?'warn':'success'}">
              <div class="pipeline-step-title">Clinical Extraction</div>
              <div class="pipeline-step-body">
                ${c.emergency_type ? `<div>Emergency Category: <strong>${c.emergency_type}</strong></div>` : '<div style="color:var(--text-muted)">Triage not yet run — click [Analyze / Triage]</div>'}
                ${c.symptoms?.length ? `<div>Symptoms: <strong>${c.symptoms.join(', ')}</strong></div>` : ''}
                ${c.extracted_location ? `<div>Extracted Location: <strong>${esc(c.extracted_location)}</strong></div>` : ''}
                ${c.patient_count ? `<div>Patients: <strong>${c.patient_count}</strong></div>` : ''}
                ${c.conscious_status ? `<div>Conscious: <strong>${c.conscious_status}</strong></div>` : ''}
                ${c.breathing_status ? `<div>Breathing: <strong>${c.breathing_status}</strong></div>` : ''}
              </div>
            </div>
            <div class="pipeline-step step-purple">
              <div class="pipeline-step-title">Triage Recommendation</div>
              <div class="pipeline-step-body">
                <div>Severity: ${pBadge}</div>
                <div>Recommended Ambulance: <strong>${c.recommended_ambulance||'—'}</strong></div>
                ${c.ai_suggested_severity ? `<div style="font-size:0.8rem; color:var(--text-secondary);">AI suggested: ${c.ai_suggested_severity} | Deterministic: ${c.deterministic_severity||'?'} | Conflict: ${c.has_conflict?'⚠️ YES':'No'}</div>` : ''}
                ${c.clinical_rationale ? `<div style="font-size:0.8rem; color:var(--text-secondary); margin-top:6px; line-height:1.5;">${esc(c.clinical_rationale)}</div>` : ''}
              </div>
            </div>
          </div>

          <!-- Step 3: Location -->
          <div class="detail-section">
            <h4>📍 Step 3: Location Verification</h4>
            <div class="pipeline-step ${c.is_location_verified ? 'step-success' : 'step-warn'}">
              <div class="pipeline-step-title">Geocoding Status: ${c.geocoding_status||'PENDING'}</div>
              <div class="pipeline-step-body">
                ${c.extracted_location ? `<div>Address: <strong>${esc(c.extracted_location)}</strong></div>` : ''}
                ${c.latitude ? `<div>Coords: <strong>${c.latitude.toFixed(4)}, ${c.longitude.toFixed(4)}</strong></div>` : '<div style="color:var(--accent-amber);">No coordinates — click [Set Location]</div>'}
                <div>Verified: <strong>${c.is_location_verified ? '✅ Yes' : '⚠️ Not yet'}</strong> | Provider: ${c.geocoding_provider||'—'}</div>
                ${c.location_error ? `<div style="color:var(--accent-red);">Error: ${esc(c.location_error)}</div>` : ''}
              </div>
            </div>
          </div>

          <!-- Step 4: Dispatch -->
          <div class="detail-section" id="dispatchSection-${caseId}">
            <h4>🚑 Step 4: Resource Dispatch</h4>
            ${c.status === 'DISPATCHED'
              ? `<div class="pipeline-step step-success"><div class="pipeline-step-title">✅ Dispatched</div><div class="pipeline-step-body" style="color:var(--accent-emerald); font-weight:700;">Ambulance dispatched successfully. Check audit timeline for full dispatch details.</div></div>`
              : `<div class="pipeline-step step-warn"><div class="pipeline-step-title">Awaiting Dispatch</div><div class="pipeline-step-body"><button class="btn btn-success" onclick="runDispatch('${caseId}')">🚑 Find Ambulance &amp; Dispatch</button></div></div>`
            }
          </div>
        </div>

        <div>
          <!-- Confidence Panel -->
          <div class="detail-section">
            <h4>📊 Multi-Signal Confidence</h4>
            ${conf ? `
              <div style="text-align:center; padding:12px 0;">
                <div style="font-size:2.8rem; font-weight:900; color:${confColor_};">${confPct}%</div>
                <div style="font-size:0.78rem; color:var(--text-muted);">System Composite Confidence</div>
                <div class="conf-bar-wrap" style="margin:8px 0; height:8px;"><div class="conf-bar" style="width:${confPct}%; background:${confColor_};"></div></div>
                <div style="display:inline-block; padding:3px 10px; border-radius:20px; background:var(--bg-card); font-size:0.78rem; font-weight:700;">${conf.confidence_level}</div>
              </div>
              <div style="display:flex; flex-direction:column; gap:8px; font-size:0.8rem; margin-top:8px;">
                ${confRow('Extraction Completeness', conf.components?.extraction_completeness, '25%')}
                ${confRow('Rule-LLM Agreement', conf.components?.rule_llm_agreement, '20%')}
                ${confRow('Location Verified', conf.components?.location_verification, '20%')}
                ${confRow('Resource Available', conf.components?.resource_availability, '15%')}
                ${confRow('Duplicate Certainty', conf.components?.duplicate_certainty, '10%')}
                ${confRow('LLM Self-Report', conf.components?.llm_confidence, '10%')}
              </div>
              ${conf.requires_human_review ? `
                <div style="margin-top:12px; padding:10px; background:rgba(245,158,11,0.1); border-radius:6px; border:1px solid rgba(245,158,11,0.3); font-size:0.78rem;">
                  ⚠️ <strong>Human Review Required:</strong><br>${esc(conf.review_trigger_reason||'')}
                </div>` : ''}
            ` : `<div style="color:var(--text-muted); font-size:0.85rem;">Run Triage first to compute confidence.</div>`}
          </div>

          <!-- Disclaimer -->
          <div class="detail-section" style="border-color:rgba(239,68,68,0.3);">
            <h4 style="color:var(--accent-red);">⚠️ PROTOTYPE DISCLAIMER</h4>
            <p style="font-size:0.75rem; color:var(--text-muted); line-height:1.6;">${c.disclaimer || 'PROTOTYPE DECISION-SUPPORT HEURISTIC: Not clinically validated triage. Requires human dispatcher verification before any real-world use.'}</p>
          </div>

          <!-- Audit Timeline -->
          <div class="detail-section" id="timelinePanel-${caseId}">
            <h4>📜 Audit Event Trail</h4>
            ${timeline.length ? `
              <div style="max-height:280px; overflow-y:auto; display:flex; flex-direction:column; gap:5px;">
                ${timeline.map(t => `
                  <div style="padding:6px 10px; background:var(--bg-card); border-radius:5px; font-size:0.75rem;">
                    <span style="color:var(--accent-cyan); font-weight:700;">${t.action}</span>
                    <div style="color:var(--text-muted);">${fmtTime(t.created_at)} — ${t.actor} — ${t.latency_ms}ms</div>
                  </div>`).join('')}
              </div>` : `<div style="color:var(--text-muted); font-size:0.83rem;">No events yet. Submit the case and run triage to generate audit logs.</div>`}
          </div>
        </div>
      </div>`;

  } catch (err) {
    container.innerHTML = errBox('Error loading case: ' + err.message);
  }
}

function confRow(label, val, weight) {
  if (val == null) return '';
  const pct = (val * 100).toFixed(0);
  return `<div style="display:flex; flex-direction:column; gap:3px;">
    <div style="display:flex; justify-content:space-between;"><span>${label} <span style="color:var(--text-muted); font-size:0.7rem;">(${weight})</span></span><strong>${pct}%</strong></div>
    <div class="conf-bar-wrap"><div class="conf-bar" style="width:${pct}%; background:${confColor(val)};"></div></div>
  </div>`;
}

// ── PIPELINE ACTIONS ──────────────────────────────────────────
async function runTriage(caseId) {
  const btn = event?.target;
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Triaging…'; }
  try {
    const res = await fetch(`/api/v1/cases/${caseId}/triage`, { method: 'POST' });
    if (!res.ok) throw new Error((await res.json()).detail?.message || 'Triage failed');
    await inspectCase(caseId);
  } catch (e) {
    alert('Triage error: ' + e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '🧠 Analyze / Triage'; }
  }
}

async function runRAG(caseId) {
  const btn = event?.target;
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Verifying…'; }
  try {
    const res = await fetch(`/api/v1/rag/cases/${caseId}/verify`, { method: 'POST' });
    if (!res.ok) throw new Error((await res.json()).detail?.message || 'RAG failed');
    const data = await res.json();
    alert(`✅ RAG Verification Complete\nSeverity Confirmed: ${data.severity_confirmed}\nAmbulance Confirmed: ${data.ambulance_confirmed}\nEvidence Chunks: ${data.evidence_count||0}\nNotes: ${data.clinical_notes||'—'}`);
    inspectCase(caseId);
  } catch (e) {
    alert('RAG verification error: ' + e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '📚 RAG Verify'; }
  }
}

async function runDispatch(caseId) {
  const btn = event?.target;
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Dispatching…'; }

  const modal = document.getElementById('dispatchModal');
  const body  = document.getElementById('dispatchModalBody');
  document.getElementById('dispatchModalTitle').textContent = '🚑 Dispatching Resources…';
  body.innerHTML = `<div style="text-align:center; padding:24px;"><span class="spinner" style="width:32px; height:32px; border-width:3px;"></span><div style="margin-top:12px; color:var(--text-secondary);">Finding nearest available ambulance and hospital…</div></div>`;
  modal.classList.add('active');

  try {
    const res = await fetch(`/api/v1/cases/${caseId}/dispatch`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      document.getElementById('dispatchModalTitle').textContent = '❌ Dispatch Failed';
      body.innerHTML = `<div class="dispatch-card error">
        <div style="color:var(--accent-red); font-weight:700; font-size:1rem; margin-bottom:8px;">${err.detail?.error || 'Dispatch Error'}</div>
        <div style="color:var(--text-secondary);">${err.detail?.message || JSON.stringify(err.detail)}</div>
      </div>
      <button class="btn btn-outline" onclick="document.getElementById('dispatchModal').classList.remove('active')" style="width:100%; margin-top:8px;">Close</button>`;
      return;
    }
    const d = await res.json();
    const amb  = d.matched_ambulance;
    const hosp = d.matched_hospital;
    document.getElementById('dispatchModalTitle').textContent = '✅ Dispatch Successful';
    body.innerHTML = `
      <div class="dispatch-card success">
        <div style="font-size:1rem; font-weight:800; color:var(--accent-emerald); margin-bottom:12px;">🚑 Ambulance Dispatched</div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; font-size:0.85rem;">
          <div><div style="color:var(--text-muted); font-size:0.72rem; text-transform:uppercase; font-weight:600;">Vehicle</div><div style="font-weight:700;">${amb?.vehicle_number||'—'}</div></div>
          <div><div style="color:var(--text-muted); font-size:0.72rem; text-transform:uppercase; font-weight:600;">Type</div><div style="font-weight:700;">${amb?.ambulance_type||'—'}</div></div>
          <div><div style="color:var(--text-muted); font-size:0.72rem; text-transform:uppercase; font-weight:600;">Distance</div><div style="font-weight:700;">${d.ambulance_distance_km != null ? d.ambulance_distance_km.toFixed(2) + ' km' : '—'}</div></div>
          <div><div style="color:var(--text-muted); font-size:0.72rem; text-transform:uppercase; font-weight:600;">ETA</div><div style="font-weight:700; color:var(--accent-amber);">${d.ambulance_eta_minutes != null ? d.ambulance_eta_minutes.toFixed(1) + ' min' : '—'}</div></div>
          <div><div style="color:var(--text-muted); font-size:0.72rem; text-transform:uppercase; font-weight:600;">Base Station</div><div>${amb?.base_station||'—'}</div></div>
          <div><div style="color:var(--text-muted); font-size:0.72rem; text-transform:uppercase; font-weight:600;">Equipment</div><div>${(amb?.equipment||[]).slice(0,3).join(', ')||'—'}</div></div>
        </div>
      </div>
      <div class="dispatch-card" style="border-left:4px solid var(--accent-blue);">
        <div style="font-size:0.9rem; font-weight:700; color:var(--accent-blue); margin-bottom:10px;">🏥 Hospital: ${hosp?.name||'—'}</div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:0.82rem;">
          <div><span style="color:var(--text-muted);">Available Beds:</span> <strong>${hosp?.available_beds||'—'}</strong></div>
          <div><span style="color:var(--text-muted);">ICU Beds:</span> <strong>${hosp?.available_icu_beds||'—'}</strong></div>
          <div><span style="color:var(--text-muted);">Trauma Center:</span> <strong>${hosp?.has_trauma_center ? '✅' : '❌'}</strong></div>
          <div><span style="color:var(--text-muted);">Cardiac Care:</span> <strong>${hosp?.has_cardiac_care ? '✅' : '❌'}</strong></div>
          <div><span style="color:var(--text-muted);">Hospital Distance:</span> <strong>${d.hospital_distance_km != null ? d.hospital_distance_km.toFixed(2)+' km' : '—'}</strong></div>
          <div><span style="color:var(--text-muted);">Hospital ETA:</span> <strong>${d.hospital_eta_minutes != null ? d.hospital_eta_minutes.toFixed(1)+' min' : '—'}</strong></div>
        </div>
      </div>
      <div style="display:flex; gap:8px; margin-top:4px;">
        <button class="btn btn-success" style="flex:1;" onclick="document.getElementById('dispatchModal').classList.remove('active'); inspectCase('${caseId}')">🔍 View Case Detail</button>
        <button class="btn btn-outline" onclick="document.getElementById('dispatchModal').classList.remove('active')">Close</button>
      </div>`;
    inspectCase(caseId);
    loadDashboardDataSimple();
  } catch (e) {
    body.innerHTML = errBox('Dispatch error: ' + e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '🚑 Find &amp; Dispatch'; }
  }
}

// ── LOCATION MODAL ────────────────────────────────────────────
function openLocationModal(caseId) {
  const lat = prompt('Enter latitude (e.g., 18.5204):');
  if (!lat) return;
  const lon = prompt('Enter longitude (e.g., 73.8567):');
  if (!lon) return;
  const addr = prompt('Enter formatted address (optional):') || '';
  setLocation(caseId, parseFloat(lat), parseFloat(lon), addr);
}

async function setLocation(caseId, lat, lon, addr) {
  try {
    const res = await fetch(`/api/v1/cases/${caseId}/location?dispatcher_id=dispatcher_1`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ latitude: lat, longitude: lon, formatted_address: addr }),
    });
    if (res.ok) { alert('✅ Location updated!'); inspectCase(caseId); }
    else alert('❌ ' + (await res.json()).detail?.message);
  } catch (e) { alert('Error: ' + e.message); }
}

async function loadAuditTimeline(caseId) {
  try {
    const res = await fetch(`/api/v1/audit/cases/${caseId}/timeline`);
    const logs = await res.json();
    const panel = document.getElementById(`timelinePanel-${caseId}`);
    if (!panel) return;
    panel.innerHTML = `<h4>📜 Audit Event Trail</h4>
      <div style="max-height:300px; overflow-y:auto; display:flex; flex-direction:column; gap:5px;">
        ${logs.map(t => `
          <div style="padding:7px 10px; background:var(--bg-card); border-radius:5px; font-size:0.75rem;">
            <span style="color:var(--accent-cyan); font-weight:700;">${t.action}</span>
            <div style="color:var(--text-muted);">${fmtTime(t.created_at)} — ${t.actor} — ${t.latency_ms}ms</div>
          </div>`).join('')}
      </div>`;
  } catch (e) { console.error(e); }
}

// ── HUMAN REVIEW MODAL ────────────────────────────────────────
function setupReviewModal() {
  const modal = document.getElementById('reviewModal');
  document.getElementById('btnModalClose').addEventListener('click', () => modal.classList.remove('active'));
  document.getElementById('btnModalCancel').addEventListener('click', () => modal.classList.remove('active'));
  document.getElementById('modalAction').addEventListener('change', e => {
    const isModify = e.target.value === 'MODIFY';
    document.getElementById('groupModSeverity').style.display  = isModify ? 'block' : 'none';
    document.getElementById('groupModAmbulance').style.display = isModify ? 'block' : 'none';
  });
  document.getElementById('btnModalSubmit').addEventListener('click', submitReviewDecision);
}

function openReviewModal(caseId) {
  document.getElementById('modalCaseId').value = caseId;
  document.getElementById('modalNotes').value  = '';
  document.getElementById('modalAction').value  = 'APPROVE';
  document.getElementById('groupModSeverity').style.display  = 'none';
  document.getElementById('groupModAmbulance').style.display = 'none';
  document.getElementById('reviewModal').classList.add('active');
}

async function submitReviewDecision() {
  const caseId    = document.getElementById('modalCaseId').value;
  const action    = document.getElementById('modalAction').value;
  const notes     = document.getElementById('modalNotes').value.trim();
  const severity  = action === 'MODIFY' ? document.getElementById('modalSeverity').value : null;
  const ambulance = action === 'MODIFY' ? document.getElementById('modalAmbulance').value : null;

  if (!notes) { alert('Dispatcher notes are required for audit trail.'); return; }

  const btn = document.getElementById('btnModalSubmit');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Submitting…';

  try {
    const res = await fetch(`/api/v1/review/${caseId}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action,
        modified_severity:  severity,
        modified_ambulance: ambulance,
        dispatcher_notes:   notes,
        dispatcher_id:      'dispatcher_1',
      }),
    });
    if (!res.ok) {
      const e = await res.json();
      alert('Review error: ' + (e.detail?.message || JSON.stringify(e)));
      return;
    }
    const d = await res.json();
    document.getElementById('reviewModal').classList.remove('active');
    alert(`✅ Review submitted!\nCase Status: ${d.case_status}\nPriority: ${d.priority}\nReview: ${d.review_status}`);
    if (currentCaseId === caseId) inspectCase(caseId);
    loadDashboardDataSimple();
    loadReviewQueue();
  } catch (e) {
    alert('Error: ' + e.message);
  } finally {
    btn.disabled = false; btn.innerHTML = 'Submit Decision';
  }
}

// ── ALL CASES ─────────────────────────────────────────────────
async function loadAllCases() {
  const filter = document.getElementById('caseStatusFilter').value;
  const url = '/api/v1/cases?limit=200' + (filter ? `&status=${filter}` : '');
  const tbody = document.getElementById('tableCasesBody');
  tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; color:var(--text-muted);">Loading…</td></tr>';
  try {
    const res = await apiFetch(url);
    const data = await res.json();
    const cases = Array.isArray(data) ? data : [];
    if (!cases.length) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; color:var(--text-muted); padding:28px;">No cases found. <a href="#" onclick="switchView('view-intake'); return false;" style="color:var(--accent-cyan);">Create an emergency →</a></td></tr>`;
      return;
    }
    tbody.innerHTML = cases.map(c => `<tr>
      <td style="font-family:monospace; font-weight:700;"><a href="#" onclick="inspectCase('${c.id}'); return false;" style="color:var(--accent-cyan);">${c.id.substring(0,10)}</a></td>
      <td><span class="badge badge-${(c.priority||'low').toLowerCase()}">${c.priority||'?'}</span></td>
      <td style="color:var(--text-secondary);">${c.emergency_type||'—'}</td>
      <td style="max-width:240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--text-secondary);">${esc(c.raw_text||'')}</td>
      <td>${c.language||'—'}</td>
      <td><span class="badge badge-${(c.status||'pending').toLowerCase()}">${c.status||'?'}</span></td>
      <td>${c.confidence_score != null ? `${(c.confidence_score*100).toFixed(0)}%` : '—'}</td>
      <td style="color:var(--text-muted); font-size:0.78rem;">${fmtTime(c.created_at)}</td>
      <td>
        <div style="display:flex; gap:4px;">
          <button class="btn btn-outline btn-sm" onclick="inspectCase('${c.id}')">🔍</button>
          ${c.status === 'UNDER_REVIEW' ? `<button class="btn btn-amber btn-sm" onclick="openReviewModal('${c.id}')">Review</button>` : ''}
          ${c.status !== 'DISPATCHED' ? `<button class="btn btn-success btn-sm" onclick="runDispatchDirect('${c.id}')">Dispatch</button>` : ''}
        </div>
      </td>
    </tr>`).join('');
  } catch (e) {
    tbody.innerHTML = errRow('Error loading cases: ' + e.message, 9);
  }
}

async function runDispatchDirect(caseId) {
  currentCaseId = caseId;
  await runDispatch(caseId);
}

// ── REVIEW QUEUE ──────────────────────────────────────────────
async function loadReviewQueue() {
  const tbody = document.getElementById('tableReviewBody');
  tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">Loading…</td></tr>';
  try {
    const res = await fetch('/api/v1/review/queue');
    const data = await res.json();
    const reviews = Array.isArray(data) ? data : [];
    if (!reviews.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--accent-emerald); font-weight:600; padding:24px;">✅ All cases verified! Zero cases pending human review.</td></tr>';
      return;
    }
    tbody.innerHTML = reviews.map(r => `<tr>
      <td style="font-family:monospace;"><a href="#" onclick="inspectCase('${r.case_id}'); return false;" style="color:var(--accent-cyan); font-weight:700;">${r.case_id.substring(0,10)}</a></td>
      <td><span class="badge badge-${(r.priority||'').toLowerCase()}">${r.priority}</span></td>
      <td style="max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--text-secondary);">${esc(r.raw_text||'')}</td>
      <td style="color:var(--accent-amber); font-size:0.82rem;">${esc(r.trigger_reason||'')}</td>
      <td><span class="badge" style="background:#374151;">${(r.confidence_score*100).toFixed(0)}% (${r.confidence_level})</span></td>
      <td><div style="display:flex; gap:4px;">
        <button class="btn btn-amber btn-sm" onclick="openReviewModal('${r.case_id}')">🧑‍⚕️ Intervene</button>
        <button class="btn btn-outline btn-sm" onclick="inspectCase('${r.case_id}')">🔍</button>
      </div></td>
    </tr>`).join('');
  } catch (e) {
    tbody.innerHTML = errRow('Error: ' + e.message, 6);
  }
}

function viewCaseOnMap(caseId) {
  currentCaseId = caseId;
  switchView('view-map');
}

// ── MAP ───────────────────────────────────────────────────────
function initMap() {
  const container = document.getElementById('mapContainer');
  if (!container || mapInstance) return;
  mapInstance = L.map('mapContainer').setView([18.5204, 73.8567], 12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap contributors',
  }).addTo(mapInstance);
}

async function loadMapData() {
  if (!mapInstance) { initMap(); }
  // Remove existing markers and polylines
  mapInstance.eachLayer(l => {
    if (l instanceof L.Marker || l instanceof L.CircleMarker || l instanceof L.Polyline) {
      mapInstance.removeLayer(l);
    }
  });

  const banner = document.getElementById('mapCaseBanner');
  if (banner) banner.style.display = 'none';

  try {
    const [ambRes, hospRes] = await Promise.all([
      fetch('/api/v1/resources/ambulances'),
      fetch('/api/v1/resources/hospitals'),
    ]);
    const ambulances = await ambRes.json();
    const hospitals  = await hospRes.json();

    const ambList  = document.getElementById('ambulanceList');
    const hospList = document.getElementById('hospitalList');
    ambList.innerHTML  = '';
    hospList.innerHTML = '';

    hospitals.forEach(h => {
      L.circleMarker([h.latitude, h.longitude], {
        radius: 10, fillColor: '#3b82f6', color: '#1d4ed8', weight: 2, opacity: 1, fillOpacity: 0.85,
      }).addTo(mapInstance)
        .bindPopup(`<strong>🏥 ${h.name}</strong><br>Beds: ${h.available_beds} | ICU: ${h.available_icu_beds}<br>Trauma: ${h.has_trauma_center ? '✅' : '❌'} | Cardiac: ${h.has_cardiac_care ? '✅' : '❌'}`);
      hospList.insertAdjacentHTML('beforeend', `
        <div style="display:flex; justify-content:space-between; padding:8px 10px; background:var(--bg-card); border-radius:6px; border-left:3px solid var(--accent-blue);">
          <span>${h.name}</span>
          <span style="color:var(--accent-emerald); font-weight:700;">${h.available_beds} beds</span>
        </div>`);
    });

    ambulances.forEach(a => {
      const available = a.status === 'AVAILABLE';
      L.circleMarker([a.latitude, a.longitude], {
        radius: 7, fillColor: available ? '#10b981' : '#ef4444', color: '#fff', weight: 1.5, opacity: 1, fillOpacity: 0.9,
      }).addTo(mapInstance)
        .bindPopup(`<strong>🚑 ${a.vehicle_number} (${a.ambulance_type})</strong><br>Base: ${a.base_station}<br>Status: <b style="color:${available ? '#10b981' : '#ef4444'}">${a.status}</b>`);
      ambList.insertAdjacentHTML('beforeend', `
        <div style="display:flex; justify-content:space-between; padding:8px 10px; background:var(--bg-card); border-radius:6px; border-left:3px solid ${available ? 'var(--accent-emerald)' : 'var(--accent-red)'};">
          <span>${a.vehicle_number} <span style="color:var(--text-muted); font-size:0.75rem;">${a.ambulance_type}</span></span>
          <span class="badge badge-${available ? 'low' : 'critical'}">${a.status}</span>
        </div>`);
    });

    // If active case is selected, render emergency incident marker and route
    if (currentCaseId) {
      try {
        const cRes = await apiFetch(`/api/v1/cases/${currentCaseId}`);
        if (cRes.ok) {
          const caseData = await cRes.json();
          if (caseData.latitude && caseData.longitude) {
            const emgMarker = L.circleMarker([caseData.latitude, caseData.longitude], {
              radius: 12, fillColor: '#ef4444', color: '#ffffff', weight: 3, opacity: 1, fillOpacity: 0.95,
            }).addTo(mapInstance)
              .bindPopup(`
                <div style="font-family:sans-serif; min-width:180px;">
                  <div style="color:#ef4444; font-weight:800; font-size:0.95rem; margin-bottom:4px;">🚨 EMERGENCY INCIDENT</div>
                  <div><strong>Case:</strong> ${caseData.id.substring(0,8)}…</div>
                  <div><strong>Priority:</strong> <span style="color:#ef4444; font-weight:700;">${caseData.priority}</span></div>
                  <div><strong>Type:</strong> ${caseData.emergency_type || '—'}</div>
                  <div><strong>Status:</strong> ${caseData.status}</div>
                  <div><strong>Location:</strong> ${esc(caseData.extracted_location || caseData.raw_text)}</div>
                </div>
              `);
            emgMarker.openPopup();

            const bounds = [[caseData.latitude, caseData.longitude]];
            const assignedAmb = ambulances.find(a => a.assigned_case_id === currentCaseId || (caseData.status === 'DISPATCHED' && a.status === 'ASSIGNED'));
            let matchedHosp = hospitals[0];

            if (assignedAmb) {
              bounds.push([assignedAmb.latitude, assignedAmb.longitude]);
              L.polyline([[assignedAmb.latitude, assignedAmb.longitude], [caseData.latitude, caseData.longitude]], {
                color: '#10b981', weight: 4, dashArray: '6, 8', opacity: 0.9,
              }).addTo(mapInstance);
            }

            if (matchedHosp) {
              bounds.push([matchedHosp.latitude, matchedHosp.longitude]);
              L.polyline([[caseData.latitude, caseData.longitude], [matchedHosp.latitude, matchedHosp.longitude]], {
                color: '#3b82f6', weight: 3, dashArray: '4, 6', opacity: 0.7,
              }).addTo(mapInstance);
            }

            if (banner) {
              banner.style.display = 'flex';
              document.getElementById('mapCaseTitle').innerHTML = `🚨 Case ${caseData.id.substring(0,8)}… · <span style="color:#ef4444;">${caseData.priority}</span> · ${caseData.emergency_type||'Emergency'}`;
              document.getElementById('mapCaseMeta').innerHTML = `
                Location: <strong>${esc(caseData.extracted_location||caseData.raw_text||'Pune')}</strong> |
                Status: <strong>${caseData.status}</strong> |
                Ambulance: <strong>${assignedAmb ? assignedAmb.vehicle_number + ' (' + assignedAmb.ambulance_type + ')' : 'Standby / Available'}</strong> |
                Hospital: <strong>${matchedHosp ? matchedHosp.name : 'Sassoon General'}</strong>
              `;
            }

            mapInstance.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
          }
        }
      } catch (caseErr) {
        console.warn('Could not load active case for map:', caseErr);
      }
    }
  } catch (e) {
    console.error('Map data error', e);
  }
}

// ── SLA ───────────────────────────────────────────────────────
async function loadSLATimers() {
  try {
    const res = await fetch('/api/v1/sla/status');
    const items = await res.json();
    const grid = document.getElementById('slaTimerGrid');
    if (!Array.isArray(items) || !items.length) {
      grid.innerHTML = '<div style="color:var(--text-muted); padding:12px;">No active SLA timers</div>';
      return;
    }
    grid.innerHTML = items.map(s => {
      const pct = Math.min(100, (s.elapsed_seconds / s.target_seconds) * 100);
      const cls = s.is_breached ? 'breach' : s.is_warning ? 'warning' : '';
      return `<div class="sla-card ${cls}">
        <div style="display:flex; justify-content:space-between; font-weight:700; margin-bottom:6px;">
          <a href="#" onclick="inspectCase('${s.case_id}'); return false;" style="color:var(--accent-cyan); font-family:monospace; font-size:0.82rem;">${s.case_id.substring(0,10)}</a>
          <span class="badge badge-${s.priority.toLowerCase()}">${s.priority}</span>
        </div>
        <div style="display:flex; justify-content:space-between; font-size:0.78rem; color:var(--text-muted); margin-bottom:6px;">
          <span>${Math.round(s.elapsed_seconds/60)}m elapsed / ${Math.round(s.target_seconds/60)}m target</span>
          <span>${s.is_breached ? '🔴 BREACH' : s.is_warning ? '🟡 WARNING' : '🟢 OK'}</span>
        </div>
        <div class="conf-bar-wrap"><div class="conf-bar" style="width:${pct}%; background:${s.is_breached ? 'var(--accent-red)' : s.is_warning ? 'var(--accent-amber)' : 'var(--accent-emerald)'};"></div></div>
      </div>`;
    }).join('');
  } catch (e) { console.error('SLA timer error', e); }
}

async function loadEscalationsData() {
  const unresolvedOnly = !document.getElementById('showResolvedEsc')?.checked;
  const tbody = document.getElementById('tableEscalationBody');
  tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">Loading…</td></tr>';
  try {
    const res = await fetch(`/api/v1/sla/escalations?unresolved_only=${unresolvedOnly}`);
    const data = await res.json();
    const list = Array.isArray(data) ? data : [];
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--accent-emerald); font-weight:600; padding:24px;">✅ Zero active escalations.</td></tr>';
      return;
    }
    tbody.innerHTML = list.map(e => `<tr>
      <td style="font-family:monospace; font-size:0.78rem;">${e.id.substring(0,10)}</td>
      <td><a href="#" onclick="inspectCase('${e.case_id}'); return false;" style="color:var(--accent-cyan); font-family:monospace;">${e.case_id.substring(0,10)}</a></td>
      <td><span class="badge" style="background:#7f1d1d;color:#fca5a5;">${e.escalation_level}</span></td>
      <td style="color:var(--accent-amber); font-size:0.82rem;">${esc(e.reason||'')}</td>
      <td style="color:var(--text-muted); font-size:0.78rem;">${fmtTime(e.created_at)}</td>
      <td>${e.resolved_at
        ? `<span style="color:var(--accent-emerald); font-weight:600;">✅ Resolved</span>`
        : `<button class="btn btn-outline btn-sm" onclick="resolveEscalation('${e.id}')">Resolve</button>`
      }</td>
    </tr>`).join('');
  } catch (e) {
    tbody.innerHTML = errRow('Error: ' + e.message, 6);
  }
}

async function resolveEscalation(escId) {
  const notes = prompt('Enter supervisor resolution notes:');
  if (!notes) return;
  try {
    const res = await fetch(`/api/v1/sla/escalations/${escId}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolution_notes: notes }),
    });
    if (res.ok) { alert('✅ Escalation resolved.'); loadEscalationsData(); loadDashboardDataSimple(); }
    else alert('Error: ' + (await res.json()).detail?.message);
  } catch (e) { alert('Error: ' + e.message); }
}

async function runSLACheck() {
  const btn = document.getElementById('btnCheckSLA');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Checking…';
  try {
    const res = await fetch('/api/v1/sla/check', { method: 'POST' });
    const data = await res.json();
    alert(`✅ SLA Check Complete\nActive Cases Checked: ${data.active_cases_checked}\nNew Warnings: ${data.new_warnings}\nNew Breaches: ${data.new_breaches}\nNew Escalations: ${data.new_escalations}`);
    loadDashboardDataSimple();
  } catch (e) { alert('Error: ' + e.message); }
  finally { btn.disabled = false; btn.innerHTML = '⏱️ Run SLA Check'; }
}

// ── FAIRNESS ──────────────────────────────────────────────────
async function loadFairnessData() {
  try {
    const res = await fetch('/api/v1/fairness/benchmark');
    const data = await res.json();
    renderFairnessTable(data);
  } catch (e) { console.error('Fairness error', e); }
}

function renderFairnessTable(data) {
  const overall = data.overall_metrics || {};
  document.getElementById('fairnessSevAcc').textContent    = pct(overall.overall_severity_accuracy);
  document.getElementById('fairnessAmbAcc').textContent    = pct(overall.overall_ambulance_accuracy);
  document.getElementById('fairnessDisparity').textContent = pct(data.max_severity_disparity);
  const tbody = document.getElementById('tableFairnessBody');
  tbody.innerHTML = Object.entries(data.language_breakdown || {}).map(([lang, m]) => `<tr>
    <td><strong>${lang}</strong></td>
    <td>${m.total_cases}</td>
    <td style="color:${m.severity_accuracy >= 0.85 ? 'var(--accent-emerald)' : 'var(--accent-amber)'}; font-weight:700;">${pct(m.severity_accuracy)}</td>
    <td>${pct(m.ambulance_accuracy)}</td>
    <td>${pct(m.location_extraction_rate)}</td>
    <td>${m.avg_latency_ms?.toFixed(0)} ms</td>
  </tr>`).join('');
}

// ── AUDIT LOGS ────────────────────────────────────────────────
async function loadAuditLogs() {
  const tbody = document.getElementById('tableAuditBody');
  tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">Loading…</td></tr>';
  try {
    const res = await fetch('/api/v1/audit/logs?limit=100');
    const logs = await res.json();
    if (!Array.isArray(logs) || !logs.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:24px;">No audit events yet.</td></tr>';
      return;
    }
    tbody.innerHTML = logs.map(l => `<tr>
      <td style="font-size:0.75rem; color:var(--text-muted); white-space:nowrap;">${fmtTime(l.created_at)}</td>
      <td><a href="#" onclick="inspectCase('${l.case_id}'); return false;" style="color:var(--accent-cyan); font-family:monospace; font-size:0.8rem;">${l.case_id.substring(0,10)}</a></td>
      <td><span class="badge" style="background:#374151;">${l.stage}</span></td>
      <td style="font-size:0.8rem;">${esc(l.actor)}</td>
      <td style="font-weight:600; font-size:0.83rem;">${esc(l.action)}</td>
      <td style="color:var(--text-muted); font-size:0.78rem;">${l.latency_ms} ms</td>
    </tr>`).join('');
  } catch (e) {
    tbody.innerHTML = errRow('Error: ' + e.message, 6);
  }
}

// ── UTILITIES ─────────────────────────────────────────────────
function esc(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function confColor(v) {
  if (v >= 0.75) return 'var(--accent-emerald)';
  if (v >= 0.5)  return 'var(--accent-amber)';
  return 'var(--accent-red)';
}
function pct(v) { return v != null ? (v * 100).toFixed(1) + '%' : '—'; }
function fmtTime(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-IN', { day:'2-digit', month:'short' }) + ' ' + d.toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit' });
  } catch { return iso; }
}
function errBox(msg) {
  return `<div class="detail-section" style="border-color:var(--accent-red); color:var(--accent-red); padding:20px;">❌ ${esc(msg)}</div>`;
}
function errRow(msg, cols) {
  return `<tr><td colspan="${cols}" style="text-align:center; color:var(--accent-red); padding:20px;">❌ ${esc(msg)}</td></tr>`;
}
