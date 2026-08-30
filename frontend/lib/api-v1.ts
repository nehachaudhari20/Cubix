/**
 * RedBlue v1 API client — Overview, Campaign Lab,
 * Score Console, Closed-Loop Arena, and Governance.
 */

import { apiBase } from './api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    cache: 'no-store',
  })
  const text = await res.text()
  let body: any = null
  try {
    body = JSON.parse(text)
  } catch {
    body = null
  }
  if (!res.ok) {
    const detail = body?.detail || body?.message || `Request failed (${res.status})`
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return body as T
}

// ── Blue Team v1 ────────────────────────────────────────────────
export const blueTeamV1 = {
  models: () => request<{ models: any[]; active_version: string }>('/api/v1/blue-team/models'),
  modelDetail: (version: string) => request<any>(`/api/v1/blue-team/models/${version}`),
  score: (body: { event_id: string; campaign_id?: string; model_version?: string }) =>
    request<any>('/api/v1/blue-team/score', { method: 'POST', body: JSON.stringify(body) }),
  scoreBatch: (body: { events: any[]; campaign_id?: string }) =>
    request<any>('/api/v1/blue-team/score/batch', { method: 'POST', body: JSON.stringify(body) }),
  ensemble: (scoreId: string) => request<any>(`/api/v1/blue-team/score/${scoreId}/ensemble`),
  explain: (scoreId: string) => request<any>(`/api/v1/blue-team/score/${scoreId}/explain`),
  policy: (scoreId: string) => request<any>(`/api/v1/blue-team/score/${scoreId}/policy`),
  audit: (scoreId: string) => request<any>(`/api/v1/blue-team/score/${scoreId}/audit`),
  retrain: (body: { trigger?: string; families?: string[] }) =>
    request<any>('/api/v1/blue-team/retrain', { method: 'POST', body: JSON.stringify(body) }),
}

// ── Red Team Campaign v1 ────────────────────────────────────────
export const redTeamCampaignV1 = {
  families: () => request<{ families: any[]; total: number }>('/api/v1/red-team/families'),
  hypotheses: (body?: {
    tested_families?: string[]
    max_hypotheses?: number
    prefer_composites?: boolean
  }) =>
    request<any>('/api/v1/red-team/hypotheses', {
      method: 'POST',
      body: JSON.stringify(body || {}),
    }),
  createCampaign: (body: {
    attack_family: string
    composite_families?: string[]
    strategy?: string
    campaign_size?: number
    execute?: boolean
  }) =>
    request<any>('/api/v1/red-team/campaigns', { method: 'POST', body: JSON.stringify(body) }),
  campaign: (id: string) => request<any>(`/api/v1/red-team/campaigns/${id}`),
  timeline: (id: string) => request<any>(`/api/v1/red-team/campaigns/${id}/timeline`),
  safety: (id: string) => request<any>(`/api/v1/red-team/campaigns/${id}/safety`),
  memory: (id: string) => request<any>(`/api/v1/red-team/campaigns/${id}/memory`),
  strategy: (id: string) => request<any>(`/api/v1/red-team/campaigns/${id}/strategy`),
  stopCampaign: (id: string) =>
    request<any>(`/api/v1/red-team/campaigns/${id}/stop`, { method: 'POST' }),
}

// ── Closed Loop ─────────────────────────────────────────────────
export const closedLoop = {
  run: (body?: {
    families?: number
    run_full_loop?: boolean
    skip_train_v1?: boolean
    swap_model?: boolean
    fresh_buffer?: boolean
  }) =>
    request<any>('/api/v1/loops/run', { method: 'POST', body: JSON.stringify(body || {}) }),
  loop: (id: string) => request<any>(`/api/v1/loops/${id}`),
  comparison: (id: string) => request<any>(`/api/v1/loops/${id}/comparison`),
  failureAnalysis: (id: string) => request<any>(`/api/v1/loops/${id}/failure-analysis`),
  missedEvents: (id: string) => request<any>(`/api/v1/loops/${id}/missed-events`),
  report: (id: string) => request<any>(`/api/v1/loops/${id}/report`),
}

// ── Governance ──────────────────────────────────────────────────
export const governance = {
  safety: () => request<any>('/api/v1/governance/safety'),
  modelRegistry: () => request<any>('/api/v1/governance/model-registry'),
  experiment: (id: string) => request<any>(`/api/v1/governance/experiment/${id}`),
  dataMetadata: () => request<any>('/api/v1/governance/data/metadata'),
}

// ── Novel Attack ────────────────────────────────────────────────
export const novelAttack = {
  generate: (body: {
    focus_area: string
    model?: string
    num_attacks?: number
    include_kb_context?: boolean
  }) =>
    request<any>('/api/v1/novel-attack/generate', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  history: () => request<any>('/api/v1/novel-attack/history'),
  get: (id: string) => request<any>(`/api/v1/novel-attack/${encodeURIComponent(id)}`),
}
