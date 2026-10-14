/**
 * ============================================================
 * SahayAI Staff SLA & Escalations Controller
 * ============================================================
 */

document.addEventListener('DOMContentLoaded', async () => {
  const user = await Auth.requireAuth();
  if (!user) return;

  Auth.renderStaffNav('sla');

  document.getElementById('btnTriggerSLACycle')?.addEventListener('click', triggerSLACheckCycle);
  document.getElementById('toggleResolvedEscalations')?.addEventListener('change', loadEscalations);
  document.getElementById('btnRefreshSLA')?.addEventListener('click', () => {
    loadSLATimers();
    loadEscalations();
  });

  await Promise.all([
    loadSLATimers(),
    loadEscalations(),
  ]);
});

async function loadSLATimers() {
  const grid = document.getElementById('slaTimersGrid');
  grid.innerHTML = '<div style="grid-column:1/-1; text-align:center; padding:24px;"><span class="spinner"></span><div style="margin-top:6px; color:var(--text-muted);">Inspecting active case timers…</div></div>';

  try {
    const timers = await window.api.getSLAStatus();

    if (!timers || timers.length === 0) {
      grid.innerHTML = `<div style="grid-column:1/-1;">${Utils.renderEmptyState('No active emergency timers. All active cases resolved or dispatched within target window.', '⏱️')}</div>`;
      return;
    }

    grid.innerHTML = timers.map(s => {
      const pct = Math.min(100, (s.elapsed_seconds / s.target_seconds) * 100);
      let borderClass = '';
      let statusTag = '🟢 OK';
      let barColor = 'var(--accent-emerald)';

      if (s.is_breached) {
        borderClass = 'breach';
        statusTag = '🔴 BREACH';
        barColor = 'var(--accent-red)';
      } else if (s.is_warning) {
        borderClass = 'warning';
        statusTag = '🟡 WARNING';
        barColor = 'var(--accent-amber)';
      }

      return `
        <div class="sla-card ${borderClass}">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <a href="/staff/cases/${encodeURIComponent(s.case_id)}" style="font-family:var(--font-mono); font-weight:700;">
              Case ${s.case_id.substring(0, 8)}…
            </a>
            ${Utils.getPriorityBadge(s.priority)}
          </div>

          <div style="display:flex; justify-content:space-between; font-size:0.8rem; color:var(--text-secondary); margin-bottom:6px;">
            <span>${Utils.formatDuration(s.elapsed_seconds)} elapsed / ${Utils.formatDuration(s.target_seconds)} target</span>
            <span style="font-weight:700;">${statusTag}</span>
          </div>

          <div class="conf-bar-wrap">
            <div class="conf-bar" style="width:${pct}%; background:${barColor};"></div>
          </div>

          ${s.is_breached ? `
            <div style="font-size:0.75rem; color:var(--accent-red); margin-top:8px; font-weight:600;">
              Breached by ${Utils.formatDuration(s.breach_duration_seconds)}
            </div>
          ` : ''}
        </div>
      `;
    }).join('');

  } catch (err) {
    grid.innerHTML = `<div style="grid-column:1/-1;">${Utils.renderErrorState('Failed to load SLA timers: ' + err.message, 'loadSLATimers()')}</div>`;
  }
}

async function loadEscalations() {
  const tbody = document.getElementById('escalationsTableBody');
  const showResolved = document.getElementById('toggleResolvedEscalations')?.checked || false;
  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:24px;"><span class="spinner"></span></td></tr>';

  try {
    const escalations = await window.api.listEscalations(!showResolved);

    if (!escalations || escalations.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:32px; color:var(--accent-emerald); font-weight:600;">✅ Zero active supervisor escalations. All cases tracking normally.</td></tr>';
      return;
    }

    tbody.innerHTML = escalations.map(e => `
      <tr>
        <td style="font-family:var(--font-mono); font-size:0.78rem;">${Utils.escapeHtml(e.id.substring(0, 8))}…</td>
        <td>
          <a href="/staff/cases/${encodeURIComponent(e.case_id)}" style="font-family:var(--font-mono); font-weight:700;">
            ${Utils.escapeHtml(e.case_id.substring(0, 8))}…
          </a>
        </td>
        <td><span class="badge" style="background:#7f1d1d; color:#fca5a5;">${Utils.escapeHtml(e.escalation_level)}</span></td>
        <td style="font-size:0.8rem; color:var(--text-muted);">${Utils.escapeHtml(e.triggered_by)}</td>
        <td style="color:var(--accent-amber); font-weight:600; font-size:0.82rem; max-width:240px;">
          ${Utils.escapeHtml(e.reason)}
        </td>
        <td style="color:var(--text-muted); font-size:0.78rem; white-space:nowrap;">
          ${Utils.formatDateTime(e.created_at)}
        </td>
        <td>
          ${e.resolved_at ? `
            <div style="color:var(--accent-emerald); font-size:0.78rem; font-weight:600;">
              ✅ Resolved (${Utils.formatTime(e.resolved_at)})
              <div style="font-size:0.72rem; color:var(--text-muted);">${Utils.escapeHtml(e.resolution_notes || '')}</div>
            </div>
          ` : `
            <button class="btn btn-outline btn-sm" onclick="promptResolveEscalation('${e.id}')">Resolve Alert</button>
          `}
        </td>
      </tr>
    `).join('');

  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7">${Utils.renderErrorState('Failed to load escalations: ' + err.message, 'loadEscalations()')}</td></tr>`;
  }
}

async function triggerSLACheckCycle() {
  const btn = document.getElementById('btnTriggerSLACycle');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Running…';

  try {
    const res = await window.api.triggerSLACheck();
    Utils.showToast(`SLA Check Complete: ${res.active_cases_checked} checked, ${res.new_warnings} warnings, ${res.new_breaches} breaches, ${res.new_escalations} escalations`, 'info');
    await Promise.all([loadSLATimers(), loadEscalations()]);
  } catch (err) {
    alert('SLA check error: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '⏱️ Trigger SLA Check Cycle';
  }
}

window.promptResolveEscalation = async function(escalationId) {
  const notes = prompt('Enter supervisor resolution notes for this escalation:');
  if (!notes) return;

  try {
    const user = Auth.getUser();
    await window.api.resolveEscalation(escalationId, notes, user ? user.username : 'supervisor_1');
    Utils.showToast('✅ Escalation marked as RESOLVED.', 'success');
    await loadEscalations();
  } catch (err) {
    alert('Resolution error: ' + err.message);
  }
};
