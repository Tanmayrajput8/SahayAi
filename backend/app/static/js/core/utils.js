/**
 * ============================================================
 * SahayAI Core Utilities — Formatters, UI Helpers & Toasts
 * ============================================================
 */

const Utils = {
  /**
   * Safe HTML string escaping
   */
  escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  },

  /**
   * Format ISO timestamp to readable locale date/time
   */
  formatDateTime(iso) {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return iso;
      return d.toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric'
      }) + ' ' + d.toLocaleTimeString('en-IN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true
      });
    } catch {
      return iso;
    }
  },

  /**
   * Format time only (e.g. 02:45 PM)
   */
  formatTime(iso) {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });
    } catch {
      return iso;
    }
  },

  /**
   * Format duration in seconds to "Xm Ys"
   */
  formatDuration(seconds) {
    if (seconds === null || seconds === undefined) return '0s';
    const s = Math.round(seconds);
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    if (mins === 0) return `${secs}s`;
    return `${mins}m ${secs}s`;
  },

  /**
   * Percentage formatter
   */
  formatPercent(val) {
    if (val === null || val === undefined || isNaN(val)) return '—';
    return (val * 100).toFixed(0) + '%';
  },

  /**
   * Priority badge HTML
   */
  getPriorityBadge(priority) {
    const p = (priority || 'LOW').toUpperCase();
    let cls = 'badge-low';
    if (p === 'CRITICAL') cls = 'badge-critical';
    else if (p === 'HIGH') cls = 'badge-high';
    else if (p === 'MODERATE') cls = 'badge-moderate';
    return `<span class="badge ${cls}">${Utils.escapeHtml(p)}</span>`;
  },

  /**
   * Case status badge HTML
   */
  getStatusBadge(status) {
    const s = (status || 'PENDING').toLowerCase();
    const label = s.replace(/_/g, ' ').toUpperCase();
    return `<span class="badge badge-${s}">${Utils.escapeHtml(label)}</span>`;
  },

  /**
   * Returns tailored color token for confidence scores
   */
  getConfidenceColor(score) {
    if (score >= 0.75) return 'var(--accent-emerald)';
    if (score >= 0.5)  return 'var(--accent-amber)';
    return 'var(--accent-red)';
  },

  /**
   * Renders empty state card
   */
  renderEmptyState(message = 'No data available', icon = '📂') {
    return `
      <div class="empty-state">
        <div class="empty-state-icon">${icon}</div>
        <div class="empty-state-text">${Utils.escapeHtml(message)}</div>
      </div>
    `;
  },

  /**
   * Renders error state card
   */
  renderErrorState(message = 'Failed to load content', retryFn = null) {
    return `
      <div class="alert alert-danger" style="display:flex; justify-content:space-between; align-items:center;">
        <div>
          <strong>Error:</strong> ${Utils.escapeHtml(message)}
        </div>
        ${retryFn ? `<button class="btn btn-outline btn-sm" onclick="${retryFn}">Retry</button>` : ''}
      </div>
    `;
  },

  /**
   * Global Toast Notification
   */
  showToast(message, type = 'info', duration = 3500) {
    let container = document.getElementById('toastContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toastContainer';
      container.style.cssText = 'position:fixed; bottom:24px; right:24px; z-index:9999; display:flex; flex-direction:column; gap:8px; pointer-events:none;';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `alert alert-${type}`;
    toast.style.cssText = 'pointer-events:auto; box-shadow:var(--shadow-lg); animation:fadeIn 0.2s ease; margin:0;';
    toast.innerHTML = Utils.escapeHtml(message);

    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }
};

window.Utils = Utils;
