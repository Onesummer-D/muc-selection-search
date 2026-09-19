import { REVIEW_STATUS_LABELS, type AnswerResponse } from '../types'

export function AnswerPanel({ answer }: { answer: AnswerResponse }) {
  return (
    <section className={`answer-panel${answer.degraded ? ' degraded' : ''}`}>
      <header className="answer-header">
        <h3>AI 回答</h3>
        {answer.degraded && (
          <span className="badge badge-warn" title={answer.degraded_reason ?? ''}>
            降级模式
          </span>
        )}
        {answer.insufficient_evidence && (
          <span className="badge badge-warn">证据不足</span>
        )}
      </header>
      {answer.degraded_reason && (
        <p className="degraded-note">{answer.degraded_reason}</p>
      )}
      <p className="answer-text">{answer.answer}</p>
      {answer.citations.length > 0 && (
        <ol className="citation-list">
          {answer.citations.map((c) => (
            <li key={c.index}>
              <span className="citation-record">{c.record_key}</span>
              <span className="muted"> · {c.field} · {c.text}</span>
              <span className={`badge status-${c.review_status}`}>
                {REVIEW_STATUS_LABELS[c.review_status] ?? c.review_status}
              </span>
            </li>
          ))}
        </ol>
      )}
      <p className="muted small">
        AI 只总结资料相关性，不构成去向建议；每个结论都对应可检查的字段证据。
      </p>
    </section>
  )
}
