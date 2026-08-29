export interface CampaignEvent {
  id: string
  loop_run_id: string
  family_id: string
  family_name: string
  step: number | null
  sandbox_decision: string
  evasion_outcome: string
  ml_score: number | null
  amount: number | null
  created_at: string
}

export interface LoopRun {
  id: string
  status: string
  trigger: string
  started_at: string
  finished_at: string | null
  families_count: number
  skip_train_v1: boolean
  swap_model: boolean
  fresh_buffer: boolean
  buffer_payments: number
  buffer_bypassed: number
  buffer_blocked: number
  families_tested: string
  v1_buffer_mean: number | null
  v2_buffer_mean: number | null
  score_lift: number | null
  recommend_swap: boolean | null
  val_pr_auc: number | null
  val_roc_auc: number | null
  verify_decision: string | null
  verify_ml_score: number | null
  error_message: string | null
  events?: CampaignEvent[]
}

export interface SystemStatus {
  kb: any
  buffer: any
  model: any
  scheduler: any
  latest_run: LoopRun | null
  running_loop: string | null
}

export interface EvidenceRecord {
  evidence_id: string
  campaign_id: string
  attack_family: string
  action_type: string
  sandbox_decision: string
  evasion_outcome: string
  ml_score: number | null
  amount: number | null
  step: number | null
  timestamp: string
  label: number | null
  features: Record<string, unknown>
  control_triggers: string[]
  blocking_control: string | null
  is_hard_negative: boolean
}

export const apiBase = () =>
  (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

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
  if (body === null && text.trim() === '') {
    throw new Error(`Empty response from ${path}`)
  }
  return body as T
}

export const api = {
  status: () => request<SystemStatus>('/api/platform/status'),
  runs: (limit = 15) => request<LoopRun[]>(`/api/platform/runs?limit=${limit}`),
  run: (id: string) => request<LoopRun>(`/api/platform/runs/${encodeURIComponent(id)}`),
  start: (body: object) =>
    request<{ run_id: string; status: string }>('/api/platform/loop/run', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  running: () => request<{ running: boolean; run_id?: string }>('/api/platform/loop/running'),
  stop: () =>
    request<{ run_id: string; status: string }>('/api/platform/loop/stop', { method: 'POST' }),
  scheduler: () => request<SystemStatus['scheduler']>('/api/platform/scheduler'),
  saveScheduler: (body: object) =>
    request<SystemStatus['scheduler']>('/api/platform/scheduler', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  buffer: () => request<any>('/api/platform/buffer'),
  recent: (limit = 20) =>
    request<EvidenceRecord[]>(`/api/platform/buffer/recent?limit=${limit}`),
  stats: () => request<any>('/api/kb/stats'),
  families: (limit = 100) => request<any[]>(`/api/kb/families?limit=${limit}`),
  family: (id: string) => request<any>(`/api/kb/families/${encodeURIComponent(id)}`),
  signals: () => request<any[]>('/api/kb/signals'),
  stages: () => request<any[]>('/api/kb/stages'),
  stageControls: () => request<Record<string, string[]>>('/api/kb/stages/controls'),
  evaluation: (id: string) =>
    request<any>(`/api/platform/runs/${encodeURIComponent(id)}/evaluation`),
  failure: (id: string) =>
    request<any>(`/api/platform/runs/${encodeURIComponent(id)}/failure-analysis`),
  redteamView: (id: string) => request<any>(`/api/redteam/view/${encodeURIComponent(id)}`),
  redteamFamilies: () => request<any[]>('/api/redteam/families'),
  redteamPropose: (body: { prompt: string; focus_family?: string }) =>
    request<any>('/api/redteam/propose', { method: 'POST', body: JSON.stringify(body) }),
}

export const fmtDate = (v: string | null | undefined) =>
  v ? new Date(v).toLocaleString() : '—'
export const fmtNum = (v: number | null | undefined, d = 3) =>
  v == null ? '—' : v.toFixed(d)
export const fmtLift = (v: number | null | undefined) =>
  v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(4)}`
export const fmtId = (v: string) => (v.length > 8 ? `${v.slice(0, 8)}…` : v)
export const fmtMoney = (v: number | null | undefined) =>
  v == null ? '—' : `₹${v.toLocaleString()}`

export function errorText(e: unknown) {
  return e instanceof Error ? e.message : 'Network error'
}

export type { SystemStatus as Status }
