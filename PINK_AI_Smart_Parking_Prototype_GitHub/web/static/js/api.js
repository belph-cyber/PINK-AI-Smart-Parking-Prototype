// -*- coding: utf-8 -*-
/* ==============================================================================
   PINK AI: Smart Parking Management System
   Unified API Client & JWT Token Manager
============================================================================== */

/* Shared transport adapter used by the dashboard, login and kiosk pages.
   Set window.PINK_API_BASE_URL before this script to connect to a separate API. */
window.PINK_API_BASE_URL = window.PINK_API_BASE_URL || '';
window.PINKApiClient = {
  lastSuccessAt: null,

  async request(endpoint, options = {}) {
    const { auth = true, timeoutMs = 10000, ...fetchOptions } = options;
    const headers = new Headers(fetchOptions.headers || {});
    if (fetchOptions.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    const token = auth ? localStorage.getItem('pink_token') : null;
    if (token) headers.set('Authorization', `Bearer ${token}`);

    const baseUrl = String(window.PINK_API_BASE_URL || '').replace(/\/$/, '');
    const url = baseUrl ? `${baseUrl}${endpoint}` : endpoint;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, { ...fetchOptions, headers, signal: controller.signal });
      if (response.ok) {
        this.lastSuccessAt = Date.now();
        window.dispatchEvent(new CustomEvent('pink-api-state', { detail: { state: 'LIVE', at: this.lastSuccessAt } }));
      } else {
        window.dispatchEvent(new CustomEvent('pink-api-state', { detail: { state: 'ERROR', status: response.status } }));
      }
      return response;
    } catch (error) {
      window.dispatchEvent(new CustomEvent('pink-api-state', { detail: { state: 'OFFLINE', message: error.name === 'AbortError' ? 'timeout' : 'network' } }));
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
  }
};

const API = {
  TOKEN_KEY: 'pink_ai_access_token',
  USER_KEY: 'pink_ai_user_data',

  getToken() {
    return localStorage.getItem(this.TOKEN_KEY);
  },

  setToken(token) {
    localStorage.setItem(this.TOKEN_KEY, token);
  },

  getUser() {
    try {
      const u = localStorage.getItem(this.USER_KEY);
      return u ? JSON.parse(u) : null;
    } catch (e) {
      return null;
    }
  },

  setUser(user) {
    localStorage.setItem(this.USER_KEY, JSON.stringify(user));
  },

  clearAuth() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
  },

  async request(endpoint, options = {}) {
    const headers = options.headers || {};
    headers['Content-Type'] = 'application/json';

    const token = this.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    try {
      const res = await fetch(endpoint, { ...options, headers });
      if (res.status === 401) {
        this.clearAuth();
        window.dispatchEvent(new CustomEvent('auth:required'));
        throw new Error('Authentication required');
      }
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.message || `Request failed (${res.status})`);
      }
      return data;
    } catch (err) {
      console.error(`[API Error] ${endpoint}:`, err);
      throw err;
    }
  },

  // Auth Endpoints
  async login(username, password) {
    const res = await this.request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    });
    if (res.access_token) {
      this.setToken(res.access_token);
      this.setUser(res.user);
    }
    return res;
  },

  async getMe() {
    return await this.request('/api/auth/me');
  },

  // Parking Endpoints
  async getParkingOverview() {
    return await this.request('/api/parking/overview');
  },

  async getFloorSlotMap(floorNumber) {
    return await this.request(`/api/parking/floor/${floorNumber}`);
  },

  async updateSlot(slotId, status, vehiclePlate = null, notes = null) {
    return await this.request(`/api/parking/slot/${slotId}`, {
      method: 'PUT',
      body: JSON.stringify({ status, vehicle_plate: vehiclePlate, notes })
    });
  },

  async getMyParking() {
    return await this.request('/api/parking/my');
  },

  async searchVehicles(query) {
    return await this.request(`/api/parking/search?q=${encodeURIComponent(query)}`);
  },

  // AI & Hybrid Verification
  async getAiEvents(limit = 30) {
    return await this.request(`/api/ai/events?limit=${limit}`);
  },

  async verifyAiEvent(eventId, action, correctedPlate = null, correctedSlotId = null, reviewNotes = null) {
    return await this.request(`/api/ai/verify/${eventId}`, {
      method: 'POST',
      body: JSON.stringify({
        action,
        corrected_plate: correctedPlate,
        corrected_slot_id: correctedSlotId,
        review_notes: reviewNotes
      })
    });
  },

  // Gate Control
  async getGates() {
    return await this.request('/api/gate/list');
  },

  async controlGate(gateId, action = 'OPEN', reason = null) {
    return await this.request('/api/gate/control', {
      method: 'POST',
      body: JSON.stringify({ gate_id: gateId, action, reason })
    });
  },

  async getGateLogs() {
    return await this.request('/api/gate/logs');
  },

  // CCTV Cameras
  async getCamStatus() {
    return await this.request('/api/cam/status');
  },

  // Messaging & Notifications
  async getConversations() {
    return await this.request('/api/messages/conversations');
  },

  async getConversationMessages(convId) {
    return await this.request(`/api/messages/conversation/${convId}`);
  },

  async sendMessage(convId, content) {
    return await this.request('/api/messages/send', {
      method: 'POST',
      body: JSON.stringify({ conversation_id: convId, content })
    });
  },

  async getNotifications() {
    return await this.request('/api/messages/notifications');
  },

  async markNotificationRead(notifId) {
    return await this.request(`/api/messages/notifications/${notifId}/read`, { method: 'PUT' });
  },

  // Admin Endpoints
  async getAdminUsers() {
    return await this.request('/api/admin/users');
  },

  async createAdminUser(userData) {
    return await this.request('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify(userData)
    });
  },

  async updateAdminUser(userId, userData) {
    return await this.request(`/api/admin/users/${userId}`, {
      method: 'PUT',
      body: JSON.stringify(userData)
    });
  },

  async getAdminVehicles() {
    return await this.request('/api/admin/vehicles');
  },

  async getAuditLogs() {
    return await this.request('/api/admin/audit-logs');
  },

  async getSystemHealth() {
    return await this.request('/api/admin/system-health');
  }
};

