import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import {
  FIELD_LABELS, REVIEW_STATUS_LABELS,
  type EvidenceItem, type RecordDetail,
} from '../types'

export function DetailModal({ recordKey, onClose }: {
  recordKey: string
  onClose: () => void
}) {
  const [detail, setDetail] = useState<RecordDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api.recordDetail(recordKey)
      .then((dto) => { if (!cancelled) setDetail(dto) })
      .catch((exc: ApiError) => { if (!cancelled) setError(exc.detail) })
    return () => { cancelled = true }
  }, [recordKey])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        {error && <p className="error-text">{error}</p>}
        {!detail && !error && <p className="muted">加载中…</p>}
        {detail && (
          <>
            <header className="modal-header">
              <h2>{detail.display_name}</h2>
              <span className={`badge status-${detail.review_status}`}>
                {REVIEW_STATUS_LABELS[detail.review_status] ?? detail.review_status}
              </span>
              <span className="badge">{detail.visibility}</span>
              <button className="btn-ghost" onClick={onClose}>关闭</button>
            </header>

            {detail.source && (
              <p className="muted">
                来源：{detail.source.title}
                {detail.source.published_at ? ` · ${detail.source.published_at.slice(0, 10)}` : ''}
              </p>
            )}
            {detail.source && !detail.source.url && (
              <p className="muted small">来源链接需校内登录后查看（游客不下发）</p>
            )}

            <h3>字段与证据并排</h3>
            <table className="evidence-table">
              <thead>
                <tr><th>字段</th><th>值</th><th>字段级证据</th><th>抽取方式</th></tr>
              </thead>
              <tbody>
                {Object.entries(detail.fields).map(([field, value]) => (
                  <tr key={field}>
                    <th>{FIELD_LABELS[field] ?? field}</th>
                    <td>{value ?? <span className="muted">未提供</span>}</td>
                    <td>{renderEvidence(detail.evidence, field)}</td>
                    <td>{renderMethod(detail.evidence, field)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <p className="muted small">
              {detail.poster.full_access
                ? detail.poster.note
                : `完整海报：${detail.poster.note}`}
              {detail.source?.url && (
                <> · <a href={detail.source.url} target="_blank" rel="noreferrer">CAS 来源链接</a></>
              )}
            </p>
          </>
        )}
      </div>
    </div>
  )
}

function renderEvidence(evidence: EvidenceItem[], field: string) {
  const items = evidence.filter((e) => e.field === field)
  if (items.length === 0) return <span className="muted">无证据</span>
  return (
    <ul className="evidence-list">
      {items.map((e, i) => (
        <li key={i}>
          “{e.text}”
          {e.bbox && <span className="muted small"> [bbox {e.bbox.join(',')}]</span>}
        </li>
      ))}
    </ul>
  )
}

function renderMethod(evidence: EvidenceItem[], field: string) {
  const items = evidence.filter((e) => e.field === field)
  if (items.length === 0) return '—'
  return items.map((e) => e.method).join(' / ')
}
