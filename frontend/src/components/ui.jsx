import { Link } from 'react-router-dom'
import { fmt } from '../lib/api'

export function Card({ title, sub, children, actions, className = '' }) {
  return (
    <div className={`card ${className}`}>
      {(title || actions) && (
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 4 }}>
          {title && <h2 style={{ margin: 0 }}>{title}</h2>}
          {actions}
        </div>
      )}
      {sub && <p className="sub">{sub}</p>}
      {children}
    </div>
  )
}

export function Stat({ label, value, note, tone }) {
  return (
    <div className="card stat">
      <span className="label">{label}</span>
      <span className={`value ${tone || ''}`}>{value}</span>
      {note && <span className="note">{note}</span>}
    </div>
  )
}

export function Loading({ what = 'data' }) {
  return (
    <div className="loading">
      <span className="spinner" /> <span style={{ marginLeft: 8 }}>Loading {what}…</span>
    </div>
  )
}

export function Empty({ children = 'Nothing to show yet.' }) {
  return <div className="empty">{children}</div>
}

export function ErrorBox({ error }) {
  if (!error) return null
  return <div className="error-box">{error.message || String(error)}</div>
}

export function Grade({ grade }) {
  if (!grade) return <span className="muted">—</span>
  return <span className={`grade grade-${grade}`}>{grade}</span>
}

export function Delta({ value, digits = 2 }) {
  if (value === null || value === undefined) return <span className="muted">—</span>
  const cls = value > 0 ? 'pos' : value < 0 ? 'neg' : 'muted'
  const sign = value > 0 ? '+' : ''
  return <span className={cls}>{sign}{(value * 100).toFixed(digits)}%</span>
}

export function ScoreBar({ value, max = 100 }) {
  const v = Math.max(0, Math.min(max, value || 0))
  const pct = (v / max) * 100
  const color = v >= 65 ? 'var(--pos)' : v >= 45 ? 'var(--accent)' : 'var(--neg)'
  return (
    <div className="row" style={{ gap: 8, flexWrap: 'nowrap' }}>
      <div className="bar-track" style={{ flex: 1, minWidth: 48 }}>
        <div className="bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="num mono" style={{ width: 42 }}>{fmt.num(v, 1)}</span>
    </div>
  )
}

export function SentimentBadge({ label, score }) {
  const cls = label === 'positive' ? 'pos' : label === 'negative' ? 'neg' : 'neutral'
  return (
    <span className={`badge ${cls}`}>
      {label}{score !== undefined && score !== null ? ` ${score > 0 ? '+' : ''}${Number(score).toFixed(2)}` : ''}
    </span>
  )
}

export function Ticker({ symbol }) {
  if (!symbol) return <span className="muted">—</span>
  return <Link className="ticker-link" to={`/stocks/${symbol}`}>{symbol}</Link>
}
