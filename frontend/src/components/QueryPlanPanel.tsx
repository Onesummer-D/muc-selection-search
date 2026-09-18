import { FIELD_LABELS, type MatchReason, type QueryPlan } from '../types'

export function QueryPlanPanel({ plan, reasons }: {
  plan: QueryPlan
  reasons?: MatchReason[]
}) {
  const chips: string[] = []
  for (const [key, label] of Object.entries(FIELD_LABELS)) {
    if (key === 'keywords') continue
    const value = (plan as unknown as Record<string, string | null>)[key]
    if (value) chips.push(`${label}：${value}`)
  }
  plan.keywords.forEach((k) => chips.push(`关键词：${k}`))

  return (
    <section className="plan-panel" aria-label="查询计划">
      <h3>查询计划（白名单条件）</h3>
      {chips.length === 0 ? (
        <p className="muted">无条件查询，展示最新已发布记录</p>
      ) : (
        <div className="chip-row">
          {chips.map((chip) => (
            <span key={chip} className="chip">{chip}</span>
          ))}
        </div>
      )}
      {reasons && reasons.length > 0 && (
        <ul className="reason-list">
          {reasons.map((r) => (
            <li key={r.label}>
              {r.label}
              <span className="reason-weight"> +{r.weight}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
