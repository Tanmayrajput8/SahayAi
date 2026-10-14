/**
 * ============================================================
 * SahayAI Staff Audit Logging & Provenance Controller
 * ============================================================
 */

let auditLogsCache = [];

document.addEventListener('DOMContentLoaded', async () => {
  const user = await Auth.requireAuth();
  if (!user) return;

  Auth.renderStaffNav('audit');

  document.getElementById('filterAuditStage')?.addEventListener('change', filterAndRenderAuditLogs);
  document.getElementById('searchAuditQuery')?.addEventListener('input', filterAndRenderAuditLogs);
  document.getElementById('btnRefreshAudit')?.addEventListener('click', loadAuditLogs);

  await loadAuditLogs();
});

async function loadAuditLogs() {
  const tbody = document.getElementById('auditTableBody');
  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:32px;"><span class="spinner"></span><div style="margin-top:8px; color:var(--text-muted);">Fetching immutable audit trail…</div></td></tr>';

  try {
    auditLogsCache = await window.api.listAuditLogs({ limit: 200 });
    filterAndRenderAuditLogs();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7">${Utils.renderErrorState('Failed to load audit logs: ' + err.message, 'loadAuditLogs()')}</td></tr>`;
  }
}

function filterAndRenderAuditLogs() {
  const tbody = document.getElementById('auditTableBody');
  const stageFilter = document.getElementById('filterAuditStage')?.value || '';
  const searchQuery = (document.getElementById('searchAuditQuery')?.value || '').toLowerCase().trim();

  let filtered = auditLogsCache;

  if (stageFilter) {
    filtered = filtered.filter(l => l.stage === stageFilter);
  }

  if (searchQuery) {
    filtered = filtered.filter(l =>
      (l.case_id && l.case_id.toLowerCase().includes(searchQuery)) ||
      (l.action && l.action.toLowerCase().includes(searchQuery)) ||
      (l.actor && l.actor.toLowerCase().includes(searchQuery)) ||
      (l.stage && l.stage.toLowerCase().includes(searchQuery))
    );
  }

  document.getElementById('auditCountLabel').textContent = `Showing ${filtered.length} of ${auditLogsCache.length} audit events`;

  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:32px;">${Utils.renderEmptyState('No audit log entries matching filters.', '📜')}</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(log => `
    <tr>
      <td style="color:var(--text-muted); font-size:0.75rem; white-space:nowrap;">
        ${Utils.formatDateTime(log.created_at)}
      </td>
      <td>
        <a href="/staff/cases/${encodeURIComponent(log.case_id)}" style="font-family:var(--font-mono); font-weight:700;">
          ${Utils.escapeHtml(log.case_id.substring(0, 8))}…
        </a>
      </td>
      <td><span class="badge" style="background:#1e293b; color:#93c5fd;">${Utils.escapeHtml(log.stage)}</span></td>
      <td style="font-weight:700; color:var(--text-primary); font-size:0.83rem;">${Utils.escapeHtml(log.action)}</td>
      <td style="color:var(--text-secondary); font-size:0.8rem;">${Utils.escapeHtml(log.actor)}</td>
      <td style="color:var(--text-muted); font-size:0.75rem;">${log.latency_ms ? `${log.latency_ms}ms` : '—'}</td>
      <td style="max-width:260px;">
        ${log.details && Object.keys(log.details).length ? `
          <details style="font-size:0.72rem; font-family:var(--font-mono); color:var(--text-secondary); cursor:pointer;">
            <summary style="color:var(--accent-cyan); font-weight:600;">Inspect JSON Details</summary>
            <pre style="background:#060a14; padding:6px; border-radius:4px; margin-top:4px; overflow-x:auto;">${Utils.escapeHtml(JSON.stringify(log.details, null, 2))}</pre>
          </details>
        ` : '<span style="color:var(--text-muted);">—</span>'}
      </td>
    </tr>
  `).join('');
}
