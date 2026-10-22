/**
 * ============================================================
 * SahayAI Core API Client — Centralized Backend Communication
 * ============================================================
 * All HTTP requests to FastAPI endpoints are routed here.
 * Handles token attachment, status codes, timeouts, and error details.
 */

class ApiClient {
  constructor(basePrefix = '/api/v1') {
    this.basePrefix = basePrefix;
  }

  /**
   * Helper to retrieve JWT token from storage
   */
  getToken() {
    return localStorage.getItem('sahayai_token') || sessionStorage.getItem('sahayai_token');
  }

  /**
   * Core request wrapper
   */
  async request(endpoint, options = {}) {
    const url = endpoint.startsWith('http') || endpoint.startsWith('/api') || endpoint.startsWith('/health')
      ? endpoint
      : `${this.basePrefix}${endpoint}`;

    const headers = { ...(options.headers || {}) };
    const token = this.getToken();

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    }

    const config = {
      ...options,
      headers,
    };

    try {
      const response = await fetch(url, config);

      // Handle unauthenticated staff redirect
      if (response.status === 401 && window.location.pathname.startsWith('/staff') && !window.location.pathname.includes('/staff/login')) {
        localStorage.removeItem('sahayai_token');
        sessionStorage.removeItem('sahayai_token');
        window.location.href = `/staff/login?redirect=${encodeURIComponent(window.location.pathname)}`;
        return { ok: false, status: 401, error: 'Unauthorized' };
      }

      // Check if response contains JSON
      const contentType = response.headers.get('content-type') || '';
      let data = null;
      if (contentType.includes('application/json')) {
        data = await response.json();
      } else {
        data = await response.text();
      }

      if (!response.ok) {
        const errorDetail = (data && data.detail) ? data.detail : (data && data.message ? data.message : 'API Request Failed');
        const errorMessage = typeof errorDetail === 'object' ? (errorDetail.message || JSON.stringify(errorDetail)) : errorDetail;
        const error = new Error(errorMessage || `HTTP error ${response.status}`);
        error.status = response.status;
        error.data = data;
        throw error;
      }

      return data;
    } catch (err) {
      console.error(`[API Error] ${options.method || 'GET'} ${url}:`, err);
      throw err;
    }
  }

  /* ── 1. AUTHENTICATION ──────────────────────────────────────── */
  async login(username, password) {
    return this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  }

  async getCurrentUser() {
    return this.request('/auth/me');
  }

  /* ── 2. EMERGENCY CASES ─────────────────────────────────────── */
  async createCase(payload) {
    return this.request('/cases', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async submitAudioCase(formData) {
    return this.request('/cases/audio', {
      method: 'POST',
      body: formData,
    });
  }

  async getCase(caseId) {
    return this.request(`/cases/${caseId}`);
  }

  async listCases(params = {}) {
    const qs = new URLSearchParams();
    if (params.status) qs.append('status', params.status);
    if (params.limit) qs.append('limit', params.limit);
    if (params.skip) qs.append('skip', params.skip);
    const queryStr = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/cases${queryStr}`);
  }

  async triageCase(caseId) {
    return this.request(`/cases/${caseId}/triage`, {
      method: 'POST',
    });
  }

  async updateCaseLocation(caseId, payload, dispatcherId = 'dispatcher_1') {
    return this.request(`/cases/${caseId}/location?dispatcher_id=${encodeURIComponent(dispatcherId)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  }

  async dispatchCase(caseId, strictAmbulanceType = false, dispatcherId = 'dispatcher_1', manual = true) {
    return this.request(
      `/cases/${caseId}/dispatch?strict_ambulance_type=${strictAmbulanceType}&manual=${manual}&dispatcher_id=${encodeURIComponent(dispatcherId)}`,
      {
        method: 'POST',
      }
    );
  }

  async updateCaseStatus(caseId, status, notes = '', dispatcherId = 'dispatcher_1') {
    return this.request(`/cases/${caseId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({
        status,
        notes: notes || undefined,
        dispatcher_id: dispatcherId,
      }),
    });
  }

  /* ── 3. RESOURCES & FLEET ───────────────────────────────────── */
  async listAmbulances(params = {}) {
    const qs = new URLSearchParams();
    if (params.status) qs.append('status', params.status);
    if (params.type) qs.append('type', params.type);
    const queryStr = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/resources/ambulances${queryStr}`);
  }

  async listHospitals(params = {}) {
    const qs = new URLSearchParams();
    if (params.active_only !== undefined) qs.append('active_only', params.active_only);
    if (params.has_cardiac !== undefined) qs.append('has_cardiac', params.has_cardiac);
    if (params.has_trauma !== undefined) qs.append('has_trauma', params.has_trauma);
    if (params.has_burns !== undefined) qs.append('has_burns', params.has_burns);
    const queryStr = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/resources/hospitals${queryStr}`);
  }

  async calculateRoute(payload) {
    return this.request('/resources/route', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  /* ── 4. RAG CLINICAL VERIFICATION ──────────────────────────── */
  async verifyCaseRAG(caseId) {
    return this.request(`/rag/cases/${caseId}/verify`, {
      method: 'POST',
    });
  }

  async getRAGStatus() {
    return this.request('/rag/status');
  }

  /* ── 5. HUMAN-IN-THE-LOOP & CONFIDENCE ──────────────────────── */
  async getReviewQueue(skip = 0, limit = 50) {
    return this.request(`/review/queue?skip=${skip}&limit=${limit}`);
  }

  async getCaseConfidence(caseId) {
    return this.request(`/review/${caseId}/confidence`);
  }

  async submitCaseReview(caseId, payload) {
    return this.request(`/review/${caseId}/submit`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  /* ── 6. SLA & ESCALATIONS ──────────────────────────────────── */
  async getSLAStatus() {
    return this.request('/sla/status');
  }

  async triggerSLACheck() {
    return this.request('/sla/check', {
      method: 'POST',
    });
  }

  async listEscalations(unresolvedOnly = true) {
    return this.request(`/sla/escalations?unresolved_only=${unresolvedOnly}`);
  }

  async resolveEscalation(escalationId, resolutionNotes, supervisorId = 'supervisor_1') {
    return this.request(`/sla/escalations/${escalationId}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ resolution_notes: resolutionNotes, supervisor_id: supervisorId }),
    });
  }

  /* ── 7. AUDIT LOGGING & TIMELINE ───────────────────────────── */
  async listAuditLogs(params = {}) {
    const qs = new URLSearchParams();
    if (params.case_id) qs.append('case_id', params.case_id);
    if (params.stage) qs.append('stage', params.stage);
    if (params.action) qs.append('action', params.action);
    if (params.actor) qs.append('actor', params.actor);
    if (params.limit) qs.append('limit', params.limit);
    if (params.skip) qs.append('skip', params.skip);
    const queryStr = qs.toString() ? `?${qs.toString()}` : '';
    return this.request(`/audit/logs${queryStr}`);
  }

  async getCaseTimeline(caseId) {
    return this.request(`/audit/cases/${caseId}/timeline`);
  }

  /* ── 8. FAIRNESS & DEMOGRAPHICS ────────────────────────────── */
  async getFairnessBenchmark() {
    return this.request('/fairness/benchmark');
  }

  async runFairnessEvaluation() {
    return this.request('/fairness/run-eval', {
      method: 'POST',
    });
  }

  /* ── 9. SYSTEM ADMINISTRATION ──────────────────────────────── */
  async resetDemo() {
    return this.request('/system/reset', {
      method: 'POST',
    });
  }

  async checkHealth() {
    return this.request('/health');
  }
}

// Global API instance
const api = new ApiClient();
window.api = api;
