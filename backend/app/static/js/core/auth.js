/**
 * ============================================================
 * SahayAI Core Auth Module — State, Role Guards & Navigation
 * ============================================================
 */

const Auth = {
  TOKEN_KEY: 'sahayai_token',
  USER_KEY: 'sahayai_user',

  getToken() {
    return localStorage.getItem(this.TOKEN_KEY) || sessionStorage.getItem(this.TOKEN_KEY);
  },

  setToken(token, remember = true) {
    if (remember) {
      localStorage.setItem(this.TOKEN_KEY, token);
    } else {
      sessionStorage.setItem(this.TOKEN_KEY, token);
    }
  },

  getUser() {
    try {
      const u = localStorage.getItem(this.USER_KEY) || sessionStorage.getItem(this.USER_KEY);
      return u ? JSON.parse(u) : null;
    } catch {
      return null;
    }
  },

  setUser(user, remember = true) {
    const serialized = JSON.stringify(user);
    if (remember) {
      localStorage.setItem(this.USER_KEY, serialized);
    } else {
      sessionStorage.setItem(this.USER_KEY, serialized);
    }
  },

  clearAuth() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
    sessionStorage.removeItem(this.TOKEN_KEY);
    sessionStorage.removeItem(this.USER_KEY);
  },

  isAuthenticated() {
    return !!this.getToken();
  },

  /**
   * Enforces staff authentication on protected staff pages.
   * If token is missing, redirects immediately to /staff/login.
   */
  async requireAuth(allowedRoles = []) {
    const token = this.getToken();
    if (!token) {
      const current = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.href = `/staff/login?redirect=${current}`;
      return null;
    }

    // Verify token validity against backend /auth/me
    try {
      const user = await window.api.getCurrentUser();
      this.setUser(user);

      if (allowedRoles.length > 0 && !allowedRoles.includes(user.role)) {
        alert(`Access Denied: Your role (${user.role}) is not authorized for this view.`);
        window.location.href = '/staff/dashboard';
        return null;
      }
      return user;
    } catch (err) {
      console.warn('Authentication token invalid or expired:', err);
      this.clearAuth();
      const current = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.href = `/staff/login?redirect=${current}`;
      return null;
    }
  },

  logout() {
    this.clearAuth();
    window.location.href = '/staff/login';
  },

  /**
   * Renders standardized Staff Sidebar Navigation with active tab highlight
   */
  renderStaffNav(activeKey = 'dashboard') {
    const sidebarEl = document.getElementById('staffSidebar');
    if (!sidebarEl) return;

    const user = this.getUser() || { username: 'Staff User', role: 'dispatcher' };
    const roleBadge = user.role ? user.role.toUpperCase() : 'DISPATCHER';

    sidebarEl.innerHTML = `
      <div class="sidebar-header">
        <div class="logo-badge">🚨</div>
        <div class="logo-text">
          <h1>SahayAI</h1>
          <span>Operations Command</span>
        </div>
      </div>

      <ul class="nav-links">
        <li class="nav-item ${activeKey === 'dashboard' ? 'active' : ''}">
          <a href="/staff/dashboard">
            <span>📊</span> <span>Dashboard</span>
          </a>
        </li>
        <li class="nav-item ${activeKey === 'cases' ? 'active' : ''}">
          <a href="/staff/cases">
            <span>📋</span> <span>Emergency Cases</span>
          </a>
        </li>
        <li class="nav-item ${activeKey === 'review' ? 'active' : ''}">
          <a href="/staff/review">
            <span>🧑‍⚕️</span> <span>Review Queue</span>
            <span class="nav-badge badge-moderate" id="navBadgeReview" style="display:none;">0</span>
          </a>
        </li>
        <li class="nav-item ${activeKey === 'ambulances' ? 'active' : ''}">
          <a href="/staff/ambulances">
            <span>🚑</span> <span>Ambulances</span>
            <span class="nav-badge badge-low" id="navBadgeAmbulance" style="display:none;">0</span>
          </a>
        </li>
        <li class="nav-item ${activeKey === 'hospitals' ? 'active' : ''}">
          <a href="/staff/hospitals">
            <span>🏥</span> <span>Hospitals</span>
          </a>
        </li>
        <li class="nav-item ${activeKey === 'map' ? 'active' : ''}">
          <a href="/staff/map">
            <span>🗺️</span> <span>Live Map</span>
          </a>
        </li>
        <li class="nav-item ${activeKey === 'sla' ? 'active' : ''}">
          <a href="/staff/sla">
            <span>⏱️</span> <span>SLA &amp; Escalations</span>
            <span class="nav-badge badge-critical" id="navBadgeEscalations" style="display:none;">0</span>
          </a>
        </li>
        <li class="nav-item ${activeKey === 'audit' ? 'active' : ''}">
          <a href="/staff/audit">
            <span>📜</span> <span>Audit Trail</span>
          </a>
        </li>
        <li class="nav-item ${activeKey === 'fairness' ? 'active' : ''}">
          <a href="/staff/fairness">
            <span>⚖️</span> <span>Fairness &amp; Bias</span>
          </a>
        </li>
      </ul>

      <div class="sidebar-footer">
        <div class="sidebar-user">
          <div class="sidebar-user-avatar">${(user.username || 'U')[0].toUpperCase()}</div>
          <div style="min-width:0; flex:1;">
            <div style="font-weight:700; font-size:0.86rem; color:var(--text-primary); text-overflow:ellipsis; overflow:hidden; white-space:nowrap;">
              ${Utils.escapeHtml(user.full_name || user.username)}
            </div>
            <div style="font-size:0.7rem; color:var(--accent-blue); font-weight:600;">
              ${roleBadge}
            </div>
          </div>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
          <a href="/" style="font-size:0.75rem; color:var(--text-muted);">← Citizen Portal</a>
          <button class="btn btn-outline btn-sm" id="btnSidebarLogout" style="padding:2px 8px; font-size:0.72rem;">Logout</button>
        </div>
      </div>
    `;

    document.getElementById('btnSidebarLogout')?.addEventListener('click', () => {
      Auth.logout();
    });

    // Asynchronously fetch live badge counts
    this.refreshNavBadges();
  },

  async refreshNavBadges() {
    try {
      const [reviewData, escData, ambData] = await Promise.all([
        window.api.getReviewQueue(0, 100).catch(() => []),
        window.api.listEscalations(true).catch(() => []),
        window.api.listAmbulances({ status: 'AVAILABLE' }).catch(() => []),
      ]);

      const reviewCount = Array.isArray(reviewData) ? reviewData.length : 0;
      const bReview = document.getElementById('navBadgeReview');
      if (bReview) {
        bReview.textContent = reviewCount;
        bReview.style.display = reviewCount > 0 ? 'inline-flex' : 'none';
      }

      const escCount = Array.isArray(escData) ? escData.length : 0;
      const bEsc = document.getElementById('navBadgeEscalations');
      if (bEsc) {
        bEsc.textContent = escCount;
        bEsc.style.display = escCount > 0 ? 'inline-flex' : 'none';
      }

      const ambCount = Array.isArray(ambData) ? ambData.length : 0;
      const bAmb = document.getElementById('navBadgeAmbulance');
      if (bAmb) {
        bAmb.textContent = ambCount;
        bAmb.style.display = ambCount > 0 ? 'inline-flex' : 'none';
      }
    } catch {
      // Non-critical badge update failure
    }
  }
};

window.Auth = Auth;
