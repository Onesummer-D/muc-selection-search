import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { FIELD_LABELS, REVIEW_STATUS_LABELS, type RecordDetail } from '../types'

export function CompareModal({ recordKeys, onClose }: {
  recordKeys: string[]
  onClose: () => void
}) {
  const [records, setRecords] = useState<RecordDetail[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api.compare(recordKeys)
      .then((data) => { if (!cancelled) setRecords(data.records) })
      .catch((exc: ApiError) => { if (!cancelled) setError(exc.detail) })
    return () => { cancelled = true }
  }, [recordKeys])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const fieldKeys = ['cohort', 'grade', 'education', 'college', 'major', 'city',
    'position_or_unit']

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal modal-wide" role="dialog" aria-modal="true"
        onClick={(e) => e.stopPropagation()}>
        <header className="modal-header">
          <h2>对比台（{recordKeys.length} 条）</h2>
          <button className="btn-ghost" onClick={onClose}>关闭</button>
        </header>
        {error && <p className="error-text">{error}</p>}
        {!records && !error && <p className="muted">加载中…</p>}
        {records && records.length > 0 && (
          <table className="evidence-table compare-table">
            <thead>
              <tr>
                <th>字段</th>
                {records.map((r) => (
                  <th key={r.record_key}>
                    {r.display_name}
                    <div>
                      <span className={`badge status-${r.review_status}`}>
                        {REVIEW_STATUS_LABELS[r.review_status] ?? r.review_status}
                      </span>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {fieldKeys.map((field) => (
                <tr key={field}>
                  <th>{FIELD_LABELS[field]}</th>
                  {records.map((r) => {
                    const value = r.fields[field as keyof typeof r.fields]
                    const ev = r.evidence.filter((e) => e.field === field)
                    return (
                      <td key={r.record_key}>
                        {value ?? <span className="muted">未提供</span>}
                        {ev.map((e, i) => (
                          <div key={i} className="muted small">“{e.text}”</div>
                        ))}
                      </td>
                    )
                  })}
                </tr>
              ))}
              <tr>
                <th>来源</th>
                {records.map((r) => (
                  <td key={r.record_key} className="small">
                    {r.source?.title}
                    {r.source?.published_at
                      ? <> · {r.source.published_at.slice(0, 10)}</> : null}
                  </td>
                ))}
              </tr>
              <tr>
                <th>证据条数</th>
                {records.map((r) => (
                  <td key={r.record_key}>{r.evidence.length}</td>
                ))}
              </tr>
            </tbody>
          </table>
        )}
        <p className="muted small">
          对比台只展示当前角色可见的字段与证据；证据缺失显示"未提供"，不做推测补全。
        </p>
      </div>
    </div>
  )
}
