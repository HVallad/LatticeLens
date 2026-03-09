const BASE = '/api';

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status} ${resp.statusText}`);
  }
  return resp.json();
}

// Facts
export const api = {
  facts: {
    list: (params?: Record<string, string>) => {
      const qs = params ? '?' + new URLSearchParams(params).toString() : '';
      return fetchJSON<any[]>(`/facts${qs}`);
    },
    get: (code: string) => fetchJSON<any>(`/facts/${code}`),
    create: (data: any) =>
      fetchJSON<any>('/facts', { method: 'POST', body: JSON.stringify(data) }),
    update: (code: string, changes: any, reason: string) =>
      fetchJSON<any>(`/facts/${code}`, {
        method: 'PATCH',
        body: JSON.stringify({ changes, reason }),
      }),
    deprecate: (code: string, reason: string) =>
      fetchJSON<any>(`/facts/${code}/deprecate`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      }),
    promote: (code: string, reason: string) =>
      fetchJSON<any>(`/facts/${code}/promote`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      }),
    nextCode: (prefix: string) =>
      fetchJSON<{ code: string }>(`/facts/next-code/${prefix}`),
  },
  graph: {
    data: (includeInactive = false) =>
      fetchJSON<any>(`/graph/data?include_inactive=${includeInactive}`),
    impact: (code: string, depth = 3) =>
      fetchJSON<any>(`/graph/impact/${code}?depth=${depth}`),
    orphans: () => fetchJSON<string[]>('/graph/orphans'),
    contradictions: (minSharedTags = 2) =>
      fetchJSON<any[]>(`/graph/contradictions?min_shared_tags=${minSharedTags}`),
  },
  meta: {
    stats: () => fetchJSON<any>('/meta/stats'),
    tags: () => fetchJSON<any[]>('/meta/tags'),
    types: () => fetchJSON<any>('/meta/types'),
    roles: () => fetchJSON<Record<string, { name: string; description: string }>>('/meta/roles'),
    roleContext: (roleName: string) =>
      fetchJSON<{ role: string; codes: string[]; graph_codes: string[]; facts_loaded: number; total_tokens: number }>(`/meta/roles/${roleName}/context`),
    enums: () => fetchJSON<any>('/meta/enums'),
    validate: () => fetchJSON<any>('/meta/validate'),
  },
};
