/**
 * ============================================================
 * SahayAI Staff All Cases Controller
 * ============================================================
 */

let allCasesCache = [];

document.addEventListener('DOMContentLoaded', async () => {
  const user = await Auth.requireAuth();
  if (!user) return;

  Auth.renderStaffNav('cases');

  const filterStatus = document.getElementById('filterCaseStatus');
  const searchInput = document.getElementById('searchCaseQuery');

  filterStatus?.addEventListener('change', () => filterAndRenderCases());
  searchInput?.addEventListener('input', () => filterAndRenderCases());

  document.getElementById('btnRefreshCases')?.addEventListener('click', loadCases);

  await loadCases();
});

async function loadCases() {
  const tbody = document.getElementById('casesTableBody');
  tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:32px;"><span class="spinner"></span><div style="margin-top:8px; color:var(--text-muted);">Loading emergency cases…</div></td></tr>`;

  try {
    const [cases, slaTimers] = await Promise.all([
      window.api.listCases({ limit: 100 }),
      window.api.getSLAStatus().catch(() => []),
    ]);

    allCasesCache = cases.map(c => {
      const sla = slaTimers.find(s => s.case_id === c.id);
      return { ...c, sla };
    });

    filterAndRenderCases();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="9">${Utils.renderErrorState('Failed to load emergency cases: ' + err.message, 'loadCases()')}</td></tr>`;
  }
}

function filterAndRenderCases() {
  const tbody = document.getElementById('casesTableBody');
  const statusFilter = document.getElementById('filterCaseStatus')?.value || '';
  const searchQuery = (document.getElementById('searchCaseQuery')?.value || '').toLowerCase().trim();

  let filtered = allCasesCache;

  if (statusFilter) {
    filtered = filtered.filter(c => c.status === statusFilter);
  }

  if (searchQuery) {
    filtered = filtered.filter(c =>
      (c.id && c.id.toLowerCase().includes(searchQuery)) ||
      (c.raw_text && c.raw_text.toLowerCase().includes(searchQuery)) ||
      (c.emergency_type && c.emergency_type.toLowerCase().includes(searchQuery)) ||
      (c.extracted_location && c.extracted_location.toLowerCase().includes(searchQuery)) ||
      (c.caller_phone && c.caller_phone.toLowerCase().includes(searchQuery))
    );
  }

  document.getElementById('casesCountLabel').textContent = `Showing ${filtered.length} of ${allCasesCache.length} cases`;

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:32px;">${Utils.renderEmptyState('No cases match the selected filter.')}</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(c => {
    const sla = c.sla;
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
          ${Utils.formatDateTime(c.created_at || c.updated_at)}
        </td>
        <td style="max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${Utils.escapeHtml(c.extracted_location || c.raw_text)}">
          📍 ${Utils.escapeHtml(c.extracted_location || 'Pune')}
        </td>
        <td style="font-weight:600; color:var(--text-primary); max-width:160px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
          ${Utils.escapeHtml(c.emergency_type || 'General')}
        </td>
        <td>${Utils.getPriorityBadge(c.priority)}</td>
        <td><span style="font-size:0.8rem; font-weight:700; color:var(--accent-cyan);">${Utils.escapeHtml(c.recommended_ambulance || 'ALS')}</span></td>
        <td style="min-width:100px;">
          <div style="font-size:0.75rem; font-weight:600; margin-bottom:2px;">${(confScore * 100).toFixed(0)}%</div>
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
          </div>
        </td>
      </tr>
    `;
  }).join('');
}
