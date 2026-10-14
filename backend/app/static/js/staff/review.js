/**
 * ============================================================
 * SahayAI Staff Human Review Queue Controller
 * ============================================================
 */

let selectedCaseIdForReview = null;

document.addEventListener('DOMContentLoaded', async () => {
  const user = await Auth.requireAuth();
  if (!user) return;

  Auth.renderStaffNav('review');

  document.getElementById('btnRefreshReview')?.addEventListener('click', loadReviewQueue);
  document.getElementById('btnCloseReviewModal')?.addEventListener('click', closeReviewModal);
  document.getElementById('btnSubmitReviewAction')?.addEventListener('click', submitReviewModalAction);

  await loadReviewQueue();

  // If case_id was passed in query param, open review modal for it automatically
  const urlParams = new URLSearchParams(window.location.search);
  const targetCaseId = urlParams.get('case_id');
  if (targetCaseId) {
    openReviewModal(targetCaseId);
  }
});

async function loadReviewQueue() {
  const tbody = document.getElementById('reviewTableBody');
  tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:32px;"><span class="spinner"></span><div style="margin-top:8px; color:var(--text-muted);">Fetching pending human review cases…</div></td></tr>`;

  try {
    const queue = await window.api.getReviewQueue(0, 100);

    // Update counter
    document.getElementById('reviewQueueCount').textContent = `${queue.length} Cases Requiring Intervention`;
    Auth.refreshNavBadges();

    if (!queue || queue.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:36px; color:var(--accent-emerald); font-weight:600;">✅ All cases verified! Zero emergency reports currently pending dispatcher review.</td></tr>`;
      return;
    }

    tbody.innerHTML = queue.map(item => {
      const confScore = item.confidence_score !== null && item.confidence_score !== undefined ? item.confidence_score : 0.0;
      const confColor = Utils.getConfidenceColor(confScore);

      return `
        <tr>
          <td>
            <a href="/staff/cases/${encodeURIComponent(item.case_id)}" style="font-family:var(--font-mono); font-weight:700;">
              ${Utils.escapeHtml(item.case_id.substring(0, 8))}…
            </a>
          </td>
          <td style="color:var(--text-muted); font-size:0.78rem; white-space:nowrap;">
            ${Utils.formatTime(item.created_at)}
          </td>
          <td style="font-weight:600; color:var(--text-primary); max-width:140px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
            ${Utils.escapeHtml(item.emergency_type || 'General')}
          </td>
          <td>${Utils.getPriorityBadge(item.priority)}</td>
          <td style="max-width:240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${Utils.escapeHtml(item.raw_text)}">
            ${Utils.escapeHtml(item.raw_text)}
          </td>
          <td style="color:var(--accent-amber); font-weight:600; font-size:0.82rem; max-width:200px;">
            ⚠️ ${Utils.escapeHtml(item.trigger_reason || 'Uncertainty threshold flagged')}
          </td>
          <td style="min-width:90px;">
            <div style="font-size:0.75rem; font-weight:700; color:${confColor};">${(confScore * 100).toFixed(0)}% (${item.confidence_level})</div>
            <div class="conf-bar-wrap">
              <div class="conf-bar" style="width:${(confScore * 100).toFixed(0)}%; background:${confColor};"></div>
            </div>
          </td>
          <td>
            <div style="display:flex; gap:6px;">
              <button class="btn btn-success btn-sm" onclick="quickApproveCase('${item.case_id}')" title="Approve AI triage assessment">✓ Approve</button>
              <button class="btn btn-amber btn-sm" onclick="openReviewModal('${item.case_id}')" title="Modify severity or ambulance">Override</button>
              <button class="btn btn-danger btn-sm" onclick="quickRejectCase('${item.case_id}')" title="Reject invalid emergency">✕ Reject</button>
            </div>
          </td>
        </tr>
      `;
    }).join('');

  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8">${Utils.renderErrorState('Failed to load review queue: ' + err.message, 'loadReviewQueue()')}</td></tr>`;
  }
}

window.quickApproveCase = async function(caseId) {
  if (!confirm(`Confirm clinical approval of case ${caseId.substring(0,8)}… with current parameters?`)) return;

  try {
    const user = Auth.getUser();
    await window.api.submitCaseReview(caseId, {
      action: 'APPROVE',
      dispatcher_id: user ? user.username : 'dispatcher_1',
      dispatcher_notes: 'Approved via Quick Dispatcher Review Action',
    });

    Utils.showToast('✅ Case approved and routed to dispatch pipeline!', 'success');
    await loadReviewQueue();
  } catch (err) {
    alert('Approval failed: ' + err.message);
  }
};

window.quickRejectCase = async function(caseId) {
  const reason = prompt('Please specify operational reason for rejecting this case:');
  if (!reason) return;

  try {
    const user = Auth.getUser();
    await window.api.submitCaseReview(caseId, {
      action: 'REJECT',
      dispatcher_id: user ? user.username : 'dispatcher_1',
      dispatcher_notes: reason,
    });

    Utils.showToast('Case marked as REJECTED.', 'info');
    await loadReviewQueue();
  } catch (err) {
    alert('Rejection failed: ' + err.message);
  }
};

window.openReviewModal = function(caseId) {
  selectedCaseIdForReview = caseId;
  document.getElementById('modalCaseIdLabel').textContent = caseId;
  document.getElementById('reviewModal').classList.add('active');
};

window.closeReviewModal = function() {
  selectedCaseIdForReview = null;
  document.getElementById('reviewModal').classList.remove('active');
};

async function submitReviewModalAction() {
  if (!selectedCaseIdForReview) return;

  const action = document.getElementById('reviewActionSelect').value;
  const modSeverity = document.getElementById('reviewModSeverity').value || null;
  const modAmbulance = document.getElementById('reviewModAmbulance').value || null;
  const notes = document.getElementById('reviewNotes').value.trim();
  const user = Auth.getUser();

  try {
    await window.api.submitCaseReview(selectedCaseIdForReview, {
      action,
      modified_severity: modSeverity,
      modified_ambulance: modAmbulance,
      dispatcher_notes: notes || undefined,
      dispatcher_id: user ? user.username : 'dispatcher_1',
    });

    Utils.showToast(`✅ Review action (${action}) successfully submitted!`, 'success');
    closeReviewModal();
    await loadReviewQueue();
  } catch (err) {
    alert('Failed to submit review: ' + err.message);
  }
}
