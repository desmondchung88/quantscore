import { useState } from 'react'
import { Card, Empty, ErrorBox, Loading, Ticker } from '../components/ui'
import { api, fmt } from '../lib/api'
import { useAction, useApi } from '../lib/hooks'

const BLANK = { title: '', body: '', ticker: '', tags: '', rating: '' }

export default function Notes() {
  const [filter, setFilter] = useState({ ticker: '', tag: '', search: '' })
  const [form, setForm] = useState(BLANK)
  const [editing, setEditing] = useState(null)
  const action = useAction()

  const notes = useApi('/notes', {
    ticker: filter.ticker || undefined,
    tag: filter.tag || undefined,
    search: filter.search || undefined,
  })
  const tags = useApi('/notes/tags')
  const activity = useApi('/notes/activity', { limit: 25 })

  function toPayload() {
    return {
      title: form.title || undefined,
      body: form.body,
      ticker: form.ticker ? form.ticker.toUpperCase() : undefined,
      tags: form.tags
        ? form.tags.split(',').map((t) => t.trim()).filter(Boolean)
        : undefined,
      rating: form.rating ? Number(form.rating) : undefined,
    }
  }

  async function save(e) {
    e.preventDefault()
    if (!form.body.trim()) return
    const fn = editing
      ? () => api.put(`/notes/${editing}`, toPayload())
      : () => api.post('/notes', toPayload())
    await action.run(fn, editing ? 'Note updated' : 'Note saved')
      .then(() => {
        setForm(BLANK); setEditing(null)
        notes.reload(); tags.reload(); activity.reload()
      })
      .catch(() => {})
  }

  function edit(n) {
    setEditing(n._id)
    setForm({
      title: n.title || '', body: n.body || '', ticker: n.ticker || '',
      tags: (n.tags || []).join(', '), rating: n.rating || '',
    })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function remove(id) {
    if (!confirm('Delete this note?')) return
    await action.run(() => api.del(`/notes/${id}`), 'Note deleted')
      .then(() => { notes.reload(); tags.reload(); activity.reload() })
      .catch(() => {})
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Research notes</h1>
          <p>
            Full create / read / update / delete against a schemaless MongoDB
            collection. A note can carry a price target, a conviction level or
            nothing at all — no migration required either way.
          </p>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: '340px minmax(0,1fr)' }}>
        <div>
          <Card title={editing ? 'Edit note' : 'New note'}>
            <form onSubmit={save}>
              <div className="field">
                <label>Title</label>
                <input value={form.title}
                       onChange={(e) => setForm({ ...form, title: e.target.value })} />
              </div>
              <div className="field">
                <label>Ticker</label>
                <input placeholder="AAPL" value={form.ticker}
                       onChange={(e) => setForm({ ...form, ticker: e.target.value })} />
              </div>
              <div className="field">
                <label>Body</label>
                <textarea rows={5} value={form.body} required
                          onChange={(e) => setForm({ ...form, body: e.target.value })} />
              </div>
              <div className="field">
                <label>Tags (comma separated)</label>
                <input placeholder="thesis, valuation" value={form.tags}
                       onChange={(e) => setForm({ ...form, tags: e.target.value })} />
              </div>
              <div className="field">
                <label>Conviction (1–5)</label>
                <input type="number" min="1" max="5" value={form.rating}
                       onChange={(e) => setForm({ ...form, rating: e.target.value })} />
              </div>
              <div className="row">
                <button type="submit" disabled={action.pending}>
                  {editing ? 'Save changes' : 'Add note'}
                </button>
                {editing && (
                  <button type="button" className="ghost"
                          onClick={() => { setEditing(null); setForm(BLANK) }}>
                    Cancel
                  </button>
                )}
              </div>
            </form>
            <div style={{ marginTop: 12 }}>
              <ErrorBox error={action.error} />
              {action.message && <div className="ok-box">{action.message}</div>}
            </div>
          </Card>

          <div style={{ height: 16 }} />

          <Card title="Tags" sub="$unwind + $group over your notes">
            {!(tags.data?.tags || []).length ? <Empty>No tags yet.</Empty> : (
              <div className="row" style={{ gap: 6 }}>
                {tags.data.tags.map((t) => (
                  <span key={t.tag} className="badge"
                        style={{ cursor: 'pointer' }}
                        onClick={() => setFilter((f) =>
                          ({ ...f, tag: f.tag === t.tag ? '' : t.tag }))}>
                    {t.tag} <span className="muted">{t.count}</span>
                  </span>
                ))}
              </div>
            )}
          </Card>

          <div style={{ height: 16 }} />

          <Card title="Recent activity"
                sub="activity_logs, expired automatically by a 30-day TTL index">
            {!(activity.data?.activity || []).length ? <Empty /> : (
              <div style={{ maxHeight: 280, overflowY: 'auto', fontSize: 12 }}>
                {activity.data.activity.map((a) => (
                  <div key={a._id} style={{ padding: '5px 0',
                                            borderBottom: '1px solid rgba(37,51,86,0.4)' }}>
                    <span className="mono">{a.action}</span>
                    <div className="muted" style={{ fontSize: 11 }}>
                      {fmt.dateTime(a.created_at)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        <div>
          <Card title="Your notes"
                actions={
                  <div className="row">
                    <input placeholder="Filter by ticker" style={{ width: 140 }}
                           value={filter.ticker}
                           onChange={(e) => setFilter({ ...filter,
                             ticker: e.target.value.toUpperCase() })} />
                    <input placeholder="Search text" style={{ width: 160 }}
                           value={filter.search}
                           onChange={(e) => setFilter({ ...filter,
                             search: e.target.value })} />
                  </div>
                }>
            {filter.tag && (
              <div className="row" style={{ marginBottom: 10 }}>
                <span className="muted" style={{ fontSize: 12 }}>
                  Filtering by tag:
                </span>
                <span className="badge">{filter.tag}</span>
                <button className="ghost sm"
                        onClick={() => setFilter((f) => ({ ...f, tag: '' }))}>
                  Clear
                </button>
              </div>
            )}

            {notes.loading ? <Loading what="notes" />
              : !(notes.data?.notes || []).length ? (
                <Empty>No notes yet. Write your first one on the left.</Empty>
              ) : notes.data.notes.map((n) => (
                <div key={n._id} style={{ padding: '12px 0',
                                          borderBottom: '1px solid rgba(37,51,86,0.5)' }}>
                  <div className="row" style={{ justifyContent: 'space-between',
                                                alignItems: 'flex-start', gap: 12 }}>
                    <div style={{ flex: 1 }}>
                      <div className="row" style={{ gap: 8 }}>
                        {n.ticker && <Ticker symbol={n.ticker} />}
                        <strong>{n.title || 'Untitled'}</strong>
                        {n.rating && (
                          <span className="badge">conviction {n.rating}/5</span>
                        )}
                      </div>
                      <p style={{ margin: '6px 0', whiteSpace: 'pre-wrap' }}>
                        {n.body}
                      </p>
                      {n.price_target && (
                        <div className="muted mono" style={{ fontSize: 11 }}>
                          price target: {JSON.stringify(n.price_target)}
                        </div>
                      )}
                      <div className="row" style={{ gap: 6, marginTop: 6 }}>
                        {(n.tags || []).map((t) => (
                          <span className="badge" key={t}>{t}</span>
                        ))}
                        <span className="muted" style={{ fontSize: 11 }}>
                          updated {fmt.dateTime(n.updated_at)}
                        </span>
                      </div>
                    </div>
                    <div className="row" style={{ gap: 6 }}>
                      <button className="ghost sm" onClick={() => edit(n)}>Edit</button>
                      <button className="danger sm" onClick={() => remove(n._id)}>
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
          </Card>
        </div>
      </div>
    </>
  )
}
