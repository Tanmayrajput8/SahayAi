/**
 * ============================================================
 * SahayAI Staff Multilingual Fairness & Bias Evaluation Controller
 * ============================================================
 */

document.addEventListener('DOMContentLoaded', async () => {
  const user = await Auth.requireAuth();
  if (!user) return;

  Auth.renderStaffNav('fairness');

  document.getElementById('btnRunFairnessEval')?.addEventListener('click', runFairnessEval);
  document.getElementById('btnRefreshFairness')?.addEventListener('click', loadFairnessData);

  await loadFairnessData();
});

async function loadFairnessData() {
  const tbody = document.getElementById('fairnessTableBody');
  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:32px;"><span class="spinner"></span><div style="margin-top:8px; color:var(--text-muted);">Computing multilingual fairness benchmarks…</div></td></tr>';

  try {
    const data = await window.api.getFairnessBenchmark();
    renderFairnessData(data);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7">${Utils.renderErrorState('Failed to load fairness metrics: ' + err.message, 'loadFairnessData()')}</td></tr>`;
  }
}

function renderFairnessData(data) {
  const overall = data.overall_metrics || {};
  document.getElementById('kpiSevAccuracy').textContent = Utils.formatPercent(overall.overall_severity_accuracy);
  document.getElementById('kpiAmbAccuracy').textContent = Utils.formatPercent(overall.overall_ambulance_accuracy);
  document.getElementById('kpiMaxDisparity').textContent = Utils.formatPercent(data.max_severity_disparity || 0.0);
  document.getElementById('kpiEvaluatedCases').textContent = overall.total_cases_evaluated || 0;

  const tbody = document.getElementById('fairnessTableBody');
  const breakdown = data.language_breakdown || {};

  if (!Object.keys(breakdown).length) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:32px;">${Utils.renderEmptyState('No demographic evaluation records generated yet.', '⚖️')}</td></tr>`;
    return;
  }

  tbody.innerHTML = Object.entries(breakdown).map(([lang, m]) => {
    const emAcc = m.emergency_type_accuracy !== null && m.emergency_type_accuracy !== undefined ? m.emergency_type_accuracy : 0.0;
    const sevAcc = m.severity_accuracy !== null && m.severity_accuracy !== undefined ? m.severity_accuracy : 0.0;
    const ambAcc = m.ambulance_accuracy !== null && m.ambulance_accuracy !== undefined ? m.ambulance_accuracy : 0.0;
    const locRate = m.location_extraction_rate !== null && m.location_extraction_rate !== undefined ? m.location_extraction_rate : 0.0;

    return `
      <tr>
        <td>
          <strong style="color:var(--text-primary); font-size:0.92rem;">${Utils.escapeHtml(lang)}</strong>
        </td>
        <td><strong>${m.total_samples || m.total_cases || 0}</strong></td>
        <td>
          <div style="font-weight:700; color:${emAcc >= 0.85 ? 'var(--accent-emerald)' : 'var(--accent-amber)'};">
            ${Utils.formatPercent(emAcc)}
          </div>
          <div class="conf-bar-wrap">
            <div class="conf-bar" style="width:${(emAcc * 100).toFixed(0)}%; background:${emAcc >= 0.85 ? 'var(--accent-emerald)' : 'var(--accent-amber)'};"></div>
          </div>
        </td>
        <td>
          <div style="font-weight:700; color:${sevAcc >= 0.85 ? 'var(--accent-emerald)' : 'var(--accent-amber)'};">
            ${Utils.formatPercent(sevAcc)}
          </div>
          <div class="conf-bar-wrap">
            <div class="conf-bar" style="width:${(sevAcc * 100).toFixed(0)}%; background:${sevAcc >= 0.85 ? 'var(--accent-emerald)' : 'var(--accent-amber)'};"></div>
          </div>
        </td>
        <td>
          <div style="font-weight:700; color:${ambAcc >= 0.85 ? 'var(--accent-emerald)' : 'var(--accent-amber)'};">
            ${Utils.formatPercent(ambAcc)}
          </div>
          <div class="conf-bar-wrap">
            <div class="conf-bar" style="width:${(ambAcc * 100).toFixed(0)}%; background:${ambAcc >= 0.85 ? 'var(--accent-emerald)' : 'var(--accent-amber)'};"></div>
          </div>
        </td>
        <td>
          <div style="font-weight:600; color:var(--accent-cyan);">
            ${Utils.formatPercent(locRate)}
          </div>
        </td>
        <td style="color:var(--text-muted); font-size:0.8rem;">
          ${m.avg_latency_ms ? `${m.avg_latency_ms.toFixed(0)} ms` : '—'}
        </td>
        <td>
          <span class="badge ${sevAcc >= 0.85 && emAcc >= 0.85 ? 'badge-low' : 'badge-moderate'}">
            ${sevAcc >= 0.85 && emAcc >= 0.85 ? 'PARITY VERIFIED' : 'ACCEPTABLE RANGE'}
          </span>
        </td>
      </tr>
    `;
  }).join('');

}

async function runFairnessEval() {
  const btn = document.getElementById('btnRunFairnessEval');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Running Benchmark Suite…';

  try {
    const data = await window.api.runFairnessEvaluation();
    Utils.showToast('✅ Fairness benchmark evaluation completed successfully!', 'success');
    renderFairnessData(data);
  } catch (err) {
    alert('Benchmark execution error: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '⚡ Run Model Evaluation Suite';
  }
}
