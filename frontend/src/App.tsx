import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from './api'
import { AnswerPanel } from './components/AnswerPanel'
import { DetailModal } from './components/DetailModal'
import { QueryPlanPanel } from './components/QueryPlanPanel'
import {
  REVIEW_STATUS_LABELS, type AnswerResponse, type MeResponse, type Role,
  type SearchResponse,
} from './types'

type Mode = 'traditional' | 'ai'

interface Filters {
  education: string
  city: string
  major: string
}

const EMPTY_FILTERS: Filters = { education: '', city: '', major: '' }

const EXAMPLES = [
  '2026届计算机本科，想看西部基层案例',
  '四川 软件工程',
]

export default function App() {
  const [me, setMe] = useState<MeResponse | null>(null)
  const [mode, setMode] = useState<Mode>('traditional')
  const [text, setText] = useState('')
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null)
  const [answer, setAnswer] = useState<AnswerResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'home' | 'results'>('home')
  const [detailKey, setDetailKey] = useState<string | null>(null)

  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null))
  }, [])

  const runSearch = useCallback(async (
    nextMode: Mode,
    nextText: string,
    nextFilters: Filters,
  ) => {
    setLoading(true)
    setError(null)
    try {
      if (nextMode === 'traditional') {
        const result = await api.search({
          education: nextFilters.education,
          city: nextFilters.city,
          major: nextFilters.major,
          keywords: nextText || undefined,
        })
        setSearchResult(result)
        setAnswer(null)
      } else {
        const result = await api.answer(nextText)
        setAnswer(result)
        setSearchResult(null)
      }
      setView('results')
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.detail : '网络错误，请确认服务已启动')
    } finally {
      setLoading(false)
    }
  }, [])

  const applyRelaxation = useCallback((field: string) => {
    const nextFilters: Filters = {
      ...filters,
      [field]: field in filters ? '' : filters[field as keyof Filters],
    }
    setFilters(nextFilters)
    if (field === 'keywords') setText('')
    void runSearch(mode, field === 'keywords' ? '' : text, nextFilters)
  }, [filters, mode, text, runSearch])

  const switchRole = useCallback(async (role: Role) => {
    try {
      await api.switchDevRole(role)
      const nextMe = await api.me()
      setMe(nextMe)
      // 角色变化影响可见性，重跑当前查询
      await runSearch(mode, text, filters)
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.detail : '角色切换失败')
    }
  }, [mode, text, filters, runSearch])

  const records = searchResult?.results ?? answer?.records ?? []
  const plan = searchResult?.query_plan ?? answer?.query_plan ?? null

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">选调研</span>
          <span className="brand-sub">校园选调信息检索</span>
        </div>
        <div className="topbar-right">
          {me && (
            <span className={`role-badge role-${me.role}`}>
              {me.role_label}
            </span>
          )}
          {me?.dev_switch_enabled && me.role && (
            <select
              className="role-switch"
              value={me.role}
              onChange={(e) => void switchRole(e.target.value as Role)}
              aria-label="开发角色开关"
            >
              <option value="guest">游客</option>
              <option value="student">校内学生</option>
              <option value="teacher">校内教师</option>
              <option value="admin">管理员</option>
            </select>
          )}
        </div>
      </header>

      {view === 'home' && (
        <main className="home">
          <h1 className="hero-title">把分散的选调经验，搜成一条可信的路径</h1>
          <div className="search-box">
            <div className="segmented" role="tablist" aria-label="搜索模式">
              <button
                role="tab"
                aria-selected={mode === 'traditional'}
                className={mode === 'traditional' ? 'active' : ''}
                onClick={() => setMode('traditional')}
              >
                传统搜索
              </button>
              <button
                role="tab"
                aria-selected={mode === 'ai'}
                className={mode === 'ai' ? 'active' : ''}
                onClick={() => setMode('ai')}
              >
                AI 搜索
              </button>
            </div>
            <form
              className="search-form"
              onSubmit={(e) => {
                e.preventDefault()
                void runSearch(mode, text, filters)
              }}
            >
              <input
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={mode === 'ai'
                  ? '用一句话描述你的需求，例如：2026届计算机本科，想看西部基层案例'
                  : '输入关键词，例如：四川 软件工程'}
                aria-label="搜索"
              />
              <button type="submit" disabled={loading}>
                {loading ? '检索中…' : '搜索'}
              </button>
            </form>
            <div className="examples">
              {EXAMPLES.map((example) => (
                <button key={example} className="btn-ghost" onClick={() => setText(example)}>
                  {example}
                </button>
              ))}
            </div>
          </div>
          <p className="muted center">
            游客看到脱敏公开视图；登录后可见授权字段。所有结论都带可检查的字段证据。
          </p>
        </main>
      )}

      {view === 'results' && (
        <main className="results-page">
          <div className="results-toolbar">
            <button className="btn-ghost" onClick={() => setView('home')}>← 返回首页</button>
            <div className="filter-bar">
              <select
                value={filters.education}
                onChange={(e) => setFilters({ ...filters, education: e.target.value })}
                aria-label="学历筛选"
              >
                <option value="">全部学历</option>
                <option value="本科">本科</option>
                <option value="硕士">硕士</option>
                <option value="博士">博士</option>
              </select>
              <input
                value={filters.city}
                onChange={(e) => setFilters({ ...filters, city: e.target.value })}
                placeholder="城市/地区"
                aria-label="城市筛选"
              />
              <input
                value={filters.major}
                onChange={(e) => setFilters({ ...filters, major: e.target.value })}
                placeholder="专业"
                aria-label="专业筛选"
              />
              <button
                onClick={() => void runSearch(mode, text, filters)}
                disabled={loading}
              >
                应用筛选
              </button>
            </div>
          </div>

          {error && <p className="error-text">{error}</p>}

          {answer && <AnswerPanel answer={answer} />}

          {plan && (
            <QueryPlanPanel
              plan={plan}
              reasons={searchResult?.results[0]?.match_reasons}
            />
          )}

          <div className="results-meta">
            共 {searchResult?.total ?? answer?.records.length ?? 0} 条结果
            {me && me.role === 'guest' && ' · 游客视图：仅展示人工确认且已发布的记录'}
          </div>

          <ul className="result-list">
            {records.map((item) => (
              <li key={item.record_key} className="result-card">
                <div className="result-main">
                  <div className="result-title-row">
                    <button
                      className="result-title"
                      onClick={() => setDetailKey(item.record_key)}
                    >
                      {item.display_name}
                    </button>
                    <span className={`badge status-${item.review_status}`}>
                      {REVIEW_STATUS_LABELS[item.review_status] ?? item.review_status}
                    </span>
                  </div>
                  <p className="result-fields">
                    {[item.fields.education, item.fields.major, item.fields.city,
                      item.fields.position_or_unit]
                      .filter(Boolean).join(' · ') || '字段待补充'}
                  </p>
                  <p className="muted small">
                    {item.source?.title}
                    {item.source?.published_at
                      ? ` · ${item.source.published_at.slice(0, 10)}` : ''}
                    {typeof item.evidence_count === 'number'
                      ? ` · 证据 ${item.evidence_count} 条` : ''}
                  </p>
                  {item.match_reasons && item.match_reasons.length > 0 && (
                    <div className="chip-row">
                      {item.match_reasons.map((r) => (
                        <span key={r.label} className="chip chip-reason">{r.label}</span>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  className="btn-detail"
                  onClick={() => setDetailKey(item.record_key)}
                >
                  详情
                </button>
              </li>
            ))}
          </ul>

          {records.length === 0 && !loading && (
            <div className="empty-state">
              <p>没有满足全部条件的记录。</p>
              {searchResult && searchResult.relaxations.length > 0 && (
                <>
                  <p className="muted">可以试试逐项放宽：</p>
                  <div className="chip-row">
                    {searchResult.relaxations.map((offer) => (
                      <button
                        key={offer.field}
                        className="chip chip-action"
                        onClick={() => applyRelaxation(offer.field)}
                      >
                        放宽「{offer.label}」条件（约 {offer.match_count} 条）
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </main>
      )}

      {detailKey && (
        <DetailModal recordKey={detailKey} onClose={() => setDetailKey(null)} />
      )}

      <footer className="footer">
        <span>选调研 v0.1.0-dev · 数据为脱敏演示样本</span>
        <span>
          {me?.campus_original_asset_enabled
            ? '完整海报：已授权开启'
            : '完整海报：默认关闭（需学校授权）'}
        </span>
      </footer>
    </div>
  )
}
