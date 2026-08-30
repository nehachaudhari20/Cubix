/**
 * Attack Generation API client — 1500-transaction bulk generation + RAG queries.
 */

const BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export interface GenerateRequest {
  count?: number;
  focus_family?: string;
  focus_stage?: string;
  seed?: number;
}

export interface RAGQueryRequest {
  query: string;
  focus_family?: string;
  max_results?: number;
}

export const attackGen = {
  generate: (body: GenerateRequest) =>
    req<any>("/api/v1/attack-gen/generate", { method: "POST", body: JSON.stringify(body) }),

  getBatch: (id: string, offset = 0, limit = 100) =>
    req<any>(`/api/v1/attack-gen/batch/${id}?offset=${offset}&limit=${limit}`),

  getSummary: (id: string) =>
    req<any>(`/api/v1/attack-gen/summary/${id}`),

  getFamilies: (id: string) =>
    req<any>(`/api/v1/attack-gen/families/${id}`),

  listBatches: () =>
    req<any>("/api/v1/attack-gen/batches"),

  ragQuery: (body: RAGQueryRequest) =>
    req<any>("/api/v1/attack-gen/rag/query", { method: "POST", body: JSON.stringify(body) }),

  ragAttack: (body: RAGQueryRequest) =>
    req<any>("/api/v1/attack-gen/rag/attack", { method: "POST", body: JSON.stringify(body) }),
};
