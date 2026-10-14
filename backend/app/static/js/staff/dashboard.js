/**
 * ============================================================
 * SahayAI Staff Operations Command Dashboard Controller
 * ============================================================
 */

document.addEventListener('DOMContentLoaded', async () => {
  // Enforce staff authentication
  const user = await Auth.requireAuth();
  if (!user) return;

  Auth.renderStaffNav('dashboard');
  setupDashboardToolbar();
  await loadDashboardData();

  // Auto-refresh every 20 seconds
  setInterval(loadDashboardData, 20000);
});

function setupDashboardToolbar() {
  document.getElementById('btnRefreshDashboard')?.addEventListener('click', loadDashboardData);

  document.getElementById('btnRunSLACheck')?.addEventListener('click', async () => {
    const btn = document.getElementById('btnRunSLACheck');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Checking…';
    try {
      const res = await window.api.triggerSLACheck();
      Utils.showToast(`SLA Inspection Complete: ${res.active_cases_checked} checked, ${res.new_breaches} breaches, ${res.new_escalations} escalations`, 'info');
      await loadDashboardData();
    } catch (err) {
      Utils.showToast('SLA Check Error: ' + err.message, 'danger');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '⏱️ Run SLA Check';
    }
  });

  document.getElementById('btnResetDemoData')?.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to reset demo data?\n\nThis will clear all submitted demo emergency cases and restore Pune ambulances and hospitals to baseline states.')) {
      return;
    }
    const btn = document.getElementById('btnResetDemoData');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Resetting…';
    try {
      const res = await window.api.resetDemo();
      Utils.showToast('✅ ' + (res.message || 'Demo data successfully reset to baseline.'), 'success');
      await loadDashboardData();
    } catch (err) {
      Utils.showToast('Reset error: ' + err.message, 'danger');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '🔄 Reset Demo Data';
    }
  });
}

async function loadDashboardData() {
  const tableBody = document.getElementById('dashboardTableBody');

  try {
    const [cases, reviews, ambulances, slaTimers, escalations] = await Promise.all([
      window.api.listCases({ limit: 50 }).catch(() => []),
      window.api.getReviewQueue(0, 100).catch(() => []),
      window.api.listAmbulances().catch(() => []),
      window.api.getSLAStatus().catch(() => []),
      window.api.listEscalations(true).catch(() => []),
    ]);

    // Update KPI Metric Cards
    const activeEmergencies = cases.filter(c => c.status !== 'RESOLVED' && c.status !== 'CANCELLED');
    const availableAmb = ambulances.filter(a => a.status === 'AVAILABLE');
    const activeDispatches = cases.filter(c => c.status === 'DISPATCHED');
    const slaWarnings = slaTimers.filter(s => s.is_warning && !s.is_breached);
    const slaBreaches = slaTimers.filter(s => s.is_breached);

    document.getElementById('kpiActiveCases').textContent = activeEmergencies.length;
    document.getElementById('kpiPendingReview').textContent = reviews.length;
    document.getElementById('kpiAvailableAmb').textContent = `${availableAmb.length}/${ambulances.length}`;
    document.getElementById('kpiActiveDispatches').textContent = activeDispatches.length;
    document.getElementById('kpiSLAWarnings').textContent = slaWarnings.length;
    document.getElementById('kpiSLABreaches').textContent = slaBreaches.length;

    // Refresh Navigation Badge counts
    Auth.refreshNavBadges();

    // Render Table
    if (!cases || cases.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:32px; color:var(--text-muted);">${Utils.renderEmptyState('No emergency cases reported yet. Visit the Citizen Portal to submit a report.')}</td></tr>`;
      return;
    }

    tableBody.innerHTML = cases.map(c => {
      const sla = slaTimers.find(s => s.case_id === c.id);
      let slaHtml = '<span style="color:var(--text-muted);">—</span>';
      if (sla) {
        if (sla.is_breached) {
          slaHtml = `<span class="badge" style="background:#7f1d1d; color:#fca5a5;">🔴 BREACH ${Math.round(sla.elapsed_seconds/60)}m</span>`;
        } else if (sla.is_warning) {
          slaHtml = `<span class="badge badge-moderate">⚠️ ${Math.round(sla.elapsed_seconds/60)}m / ${Math.round(sla.target_seconds/60)}m</span>`;
        } else {
          slaHtml = `<span style="color:var(--accent-emerald); font-weight:600; font-size:0.8rem;">🟢 ${Math.round(sla.elapsed_seconds/60)}m</span>`;
        }
      }

      const rawText = c.raw_text || c.raw_input || c.emergency_type || '—';
      const confScore = c.confidence_score !== null && c.confidence_score !== undefined ? c.confidence_score : 0.0;
      const confColor = Utils.getConfidenceColor(confScore);

      return `
        <tr>
          <td>
            <a href="/staff/cases/${encodeURIComponent(c.id)}" style="font-family:var(--font-mono); font-weight:700;">
              ${Utils.escapeHtml(c.id.substring(0, 8))}…
            </a>
          </td>
          <td style="color:var(--text-muted); font-size:0.78rem; white-space:nowrap;">
            ${Utils.formatTime(c.created_at || c.updated_at)}
          </td>
          <td style="max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${Utils.escapeHtml(c.extracted_location || rawText)}">
            📍 ${Utils.escapeHtml(c.extracted_location || 'Pune')}
          </td>
          <td style="font-weight:600; color:var(--text-primary); max-width:150px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
            ${Utils.escapeHtml(c.emergency_type || 'General Emergency')}
          </td>
          <td>${Utils.getPriorityBadge(c.priority)}</td>
          <td><span style="font-size:0.8rem; font-weight:600; color:var(--accent-cyan);">${Utils.escapeHtml(c.recommended_ambulance || 'ALS')}</span></td>
          <td style="min-width:100px;">
            <div style="display:flex; justify-content:space-between; font-size:0.75rem; font-weight:600; margin-bottom:2px;">
              <span>${(confScore * 100).toFixed(0)}%</span>
            </div>
            <div class="conf-bar-wrap">
              <div class="conf-bar" style="width:${(confScore * 100).toFixed(0)}%; background:${confColor};"></div>
            </div>
          </td>
          <td>${Utils.getStatusBadge(c.status)}</td>
          <td>${slaHtml}</td>
          <td>
            <div style="display:flex; gap:6px;">
              <a href="/staff/cases/${encodeURIComponent(c.id)}" class="btn btn-outline btn-sm">Inspect</a>
              ${c.status === 'UNDER_REVIEW' ? `<a href="/staff/review?case_id=${encodeURIComponent(c.id)}" class="btn btn-amber btn-sm">Review</a>` : ''}
              ${c.status !== 'DISPATCHED' && c.status !== 'RESOLVED' ? `<button class="btn btn-success btn-sm" onclick="quickDispatch('${c.id}')">Dispatch</button>` : ''}
            </div>
          </td>
        </tr>
      `;
    }).join('');

    const lastRefreshEl = document.getElementById('lastRefreshTime');
    if (lastRefreshEl) {
      lastRefreshEl.textContent = `Updated: ${new Date().toLocaleTimeString('en-IN')}`;
    }

  } catch (err) {
    console.error('Failed to load dashboard data:', err);
    tableBody.innerHTML = `<tr><td colspan="9">${Utils.renderErrorState('Unable to load dashboard emergency cases: ' + err.message, 'loadDashboardData()')}</td></tr>`;
  }
}

window.quickDispatch = async function(caseId) {
  try {
    const res = await window.api.dispatchCase(caseId);
    Utils.showToast(`Ambulance ${res.matched_ambulance?.vehicle_number || ''} dispatched successfully! ETA: ${res.ambulance_eta_minutes ? res.ambulance_eta_minutes.toFixed(1) : '~8'} min`, 'success');
    await loadDashboardData();
  } catch (err) {
    Utils.showToast('Dispatch failed: ' + err.message, 'danger');
  }
};
