const BASE = '/api'

export async function fetchSummary() {
  const r = await fetch(`${BASE}/telemetry/summary`)
  if (!r.ok) throw new Error('Failed to fetch summary')
  return r.json()
}

export async function fetchTelemetry(limit = 200) {
  const r = await fetch(`${BASE}/telemetry?limit=${limit}`)
  if (!r.ok) throw new Error('Failed to fetch telemetry')
  return r.json()
}

export async function fetchSecurityAlerts() {
  const r = await fetch(`${BASE}/security/alerts`)
  if (!r.ok) throw new Error('Failed to fetch security alerts')
  return r.json()
}

export async function fetchAudit(params = {}) {
  const q = new URLSearchParams(params).toString()
  const r = await fetch(`${BASE}/audit?${q}`)
  if (!r.ok) throw new Error('Failed to fetch audit log')
  return r.json()
}
