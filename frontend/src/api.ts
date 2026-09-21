import type {
  AnswerResponse, MeResponse, ParseResponse, RecordDetail, Role, SearchResponse,
  StatsResponse,
  PrivacySettings, SavedSearch, NotificationItem, QueryPlan,
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
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
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
  search: (params: SearchParams, incognito = false) => {
    const query = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value) query.set(key, value)
    }
    const qs = query.toString()
    return request<SearchResponse>(`/api/search${qs ? `?${qs}` : ''}`, incognito ? { headers: { 'X-Incognito-Mode': '1' } } : undefined)
  },

  parseQuery: (text: string) =>
    request<ParseResponse>('/api/query/parse', {
      method: 'POST',
      body: JSON.stringify({ query: text }),
    }),

  answer: (text: string, incognito = false) =>
    request<AnswerResponse>('/api/query/answer', {
      method: 'POST',
      headers: incognito ? { 'X-Incognito-Mode': '1' } : undefined,
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

  listSavedSearches: () => request<{ items: SavedSearch[] }>('/api/saved-searches'),
  saveSearch: (queryPlan: QueryPlan, alert_frequency: SavedSearch['alert_frequency'] = 'weekly') =>
    request<SavedSearch>('/api/saved-searches', { method: 'POST', body: JSON.stringify({ query_plan: queryPlan, alert_frequency }) }),
  updateSavedAlert: (id: number, alert_frequency: SavedSearch['alert_frequency']) =>
    request<SavedSearch>(`/api/saved-searches/${id}/alert`, { method: 'PATCH', body: JSON.stringify({ alert_frequency }) }),
  deleteSavedSearch: (id: number) => request<{ deleted: boolean }>(`/api/saved-searches/${id}`, { method: 'DELETE' }),
  privacy: () => request<PrivacySettings>('/api/me/privacy'),
  updatePrivacy: (body: Partial<Pick<PrivacySettings, 'history_enabled' | 'recommendation_enabled'>>) =>
    request<PrivacySettings>('/api/me/privacy', { method: 'PATCH', body: JSON.stringify(body) }),
  clearHistory: () => request<{ deleted_count: number }>('/api/me/history', { method: 'DELETE' }),
  notifications: () => request<{ items: NotificationItem[] }>('/api/notifications'),
}
