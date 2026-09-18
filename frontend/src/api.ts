import type {
  AnswerResponse, MeResponse, ParseResponse, RecordDetail, Role, SearchResponse,
  StatsResponse,
} from './types'

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail || `请求失败 (${status})`)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  const body = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    const detail = (body as { detail?: string }).detail
      ?? (body as { error?: string }).error
      ?? `请求失败 (${resp.status})`
    throw new ApiError(resp.status, detail)
  }
  return body as T
}

export interface SearchParams {
  [key: string]: string | undefined
}

export const api = {
  search: (params: SearchParams) => {
    const query = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value) query.set(key, value)
    }
    const qs = query.toString()
    return request<SearchResponse>(`/api/search${qs ? `?${qs}` : ''}`)
  },

  parseQuery: (text: string) =>
    request<ParseResponse>('/api/query/parse', {
      method: 'POST',
      body: JSON.stringify({ query: text }),
    }),

  answer: (text: string) =>
    request<AnswerResponse>('/api/query/answer', {
      method: 'POST',
      body: JSON.stringify({ query: text }),
    }),

  recordDetail: (recordKey: string) =>
    request<RecordDetail>(`/api/records/${encodeURIComponent(recordKey)}`),

  stats: (params: SearchParams) => {
    const query = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value) query.set(key, value)
    }
    const qs = query.toString()
    return request<StatsResponse>(`/api/search/stats${qs ? `?${qs}` : ''}`)
  },

  compare: (recordKeys: string[]) =>
    request<{ records: RecordDetail[] }>('/api/compare', {
      method: 'POST',
      body: JSON.stringify({ record_keys: recordKeys }),
    }),

  me: () => request<MeResponse>('/api/auth/me'),

  switchDevRole: (role: Role) =>
    request<{ role: Role }>('/api/dev/role', {
      method: 'POST',
      body: JSON.stringify({ role }),
    }),

  resetDevRole: () =>
    request<{ role: Role }>('/api/dev/role', { method: 'DELETE' }),
}
