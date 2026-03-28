/**
 * api.js — REST API client for one-off queries and commands.
 */

const BASE_URL = 'http://localhost:8001';

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`;
  try {
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error(`API error [${path}]:`, err);
    return null;
  }
}

export const api = {
  // Health
  health: () => request('/health'),

  // Stats
  getStats: () => request('/stats'),

  // Detection control
  startDetection: (source = '0', targetFps = 30) =>
    request('/detection/start', {
      method: 'POST',
      body: JSON.stringify({ source, target_fps: targetFps }),
    }),
  stopDetection: () => request('/detection/stop', { method: 'POST' }),
  detectionStatus: () => request('/detection/status'),

  // Signals
  getSignalStatus: () => request('/signal/status'),
  overrideSignal: (lane, reason = 'manual') =>
    request('/signal/override', {
      method: 'POST',
      body: JSON.stringify({ lane, reason, vehicle_type: 'manual' }),
    }),

  // Vehicle counts (from external)
  sendVehicleCounts: (armCounts, total, mode = 'ADAPTIVE') =>
    request('/vehicle-counts', {
      method: 'POST',
      body: JSON.stringify({
        arm_counts: armCounts,
        total_vehicles: total,
        mode,
        source: 'dashboard',
      }),
    }),

  // Density
  getDensity: () => request('/density'),

  // History
  getHistory: (eventType, lane, limit = 50) => {
    const params = new URLSearchParams();
    if (eventType) params.set('event_type', eventType);
    if (lane) params.set('lane', lane);
    params.set('limit', limit);
    return request(`/history?${params}`);
  },
  getPhaseHistory: (limit = 100) => request(`/history/phases?limit=${limit}`),
  getAlertHistory: (limit = 50) => request(`/history/alerts?limit=${limit}`),
};
