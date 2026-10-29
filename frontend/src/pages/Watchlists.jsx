import { useEffect, useState } from 'react'
import { Card, Delta, Empty, ErrorBox, Grade, Loading, Ticker } from '../components/ui'
import { api, fmt } from '../lib/api'
import { useAction, useApi } from '../lib/hooks'

export default function Watchlists() {
  const lists = useApi('/watchlists')
  const [active, setActive] = useState(null)
  const [newList, setNewList] = useState('')
  const [newTicker, setNewTicker] = useState('')
  const action = useAction()

  useEffect(() => {
    const items = lists.data?.watchlists || []
    if (items.length && !items.some((w) => w.watchlist_id === active)) {
      setActive(items[0].watchlist_id)
    }
  }, [lists.data, active])

  const detail = useApi(active ? `/watchlists/${active}` : null)

  async function createList() {
    if (!newList.trim()) return
    await action.run(() => api.post('/watchlists', { name: newList.trim() }),
                     'Watchlist created')
      .then(() => { setNewList(''); lists.reload() }).catch(() => {})
  }

  async function addTicker(e) {
    e.preventDefault()
    if (!newTicker.trim() || !active) return
    await action.run(
      () => api.post(`/watchlists/${active}/stocks`,
                     { ticker: newTicker.trim().toUpperCase() }),
      `${newTicker.toUpperCase()} added`,
    ).then(() => { setNewTicker(''); detail.reload(); lists.reload() }).catch(() => {})
  }

  async function removeTicker(ticker) {
    await action.run(() => api.del(`/watchlists/${active}/stocks/${ticker}`))
      .then(() => { detail.reload(); lists.reload() }).catch(() => {})
  }

  async function deleteList() {
    if (!confirm('Delete this watchlist?')) return
    await action.run(() => api.del(`/watchlists/${active}`), 'Watchlist deleted')
      .then(() => { setActive(null); lists.reload() }).catch(() => {})
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Watchlists</h1>
          <p>
            The many-to-many side of the schema: a watchlist holds many stocks
            and a stock sits on many watchlists, joined through the
            <code> watchlist_stocks </code> table with a composite primary key.
          </p>
        </div>
        <div className="row">
          <select value={active || ''} style={{ width: 200 }}
                  onChange={(e) => setActive(Number(e.target.value))}>
            {(lists.data?.watchlists || []).map((w) => (
              <option key={w.watchlist_id} value={w.watchlist_id}>
                {w.name} ({w.stock_count})
              </option>
            ))}
          </select>
          <button className="ghost" onClick={deleteList} disabled={!active}>
            Delete
          </button>
        </div>
      </div>

      <ErrorBox error={lists.error || action.error} />
      {action.message && <div className="ok-box">{action.message}</div>}

      <div className="grid" style={{ gridTemplateColumns: '300px minmax(0,1fr)' }}>
        <div>
          <Card title="New watchlist">
            <div className="field">
              <input placeholder="e.g. Dividend aristocrats" value={newList}
                     onChange={(e) => setNewList(e.target.value)} />
            </div>
            <button onClick={createList} disabled={action.pending || !newList.trim()}>
              Create
            </button>
          </Card>

          {active && (
            <>
              <div style={{ height: 16 }} />
              <Card title="Add a stock">
                <form onSubmit={addTicker}>
                  <div className="field">
                    <input placeholder="Ticker, e.g. KO" value={newTicker}
                           onChange={(e) => setNewTicker(e.target.value.toUpperCase())} />
                  </div>
                  <button type="submit" disabled={action.pending}>Add</button>
                </form>
              </Card>
            </>
          )}
        </div>

        <div>
          <Card title={detail.data?.watchlist?.name || 'Watchlist'}
                sub="Joined to v_stock_scores_total so each row carries its live score">
            {lists.loading || detail.loading ? <Loading />
              : !(lists.data?.watchlists || []).length ? (
                <Empty>Create your first watchlist on the left.</Empty>
              ) : !(detail.data?.stocks || []).length ? (
                <Empty>This watchlist is empty.</Empty>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Ticker</th><th>Company</th><th>Sector</th>
                        <th className="num">Last</th><th className="num">P/E</th>
                        <th className="num">Yield</th><th className="num">1y</th>
                        <th className="num">Score</th><th>Grade</th>
                        <th>Added</th><th />
                      </tr>
                    </thead>
                    <tbody>
                      {detail.data.stocks.map((s) => (
                        <tr key={s.ticker}>
                          <td><Ticker symbol={s.ticker} /></td>
                          <td style={{ maxWidth: 180, overflow: 'hidden',
                                       textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {s.company_name}
                          </td>
                          <td className="muted" style={{ fontSize: 12 }}>
                            {s.sector_name}
                          </td>
                          <td className="num">{fmt.money(s.last_close)}</td>
                          <td className="num">{fmt.num(s.pe_ratio, 1)}</td>
                          <td className="num">
                            {s.dividend_yield ? `${fmt.num(s.dividend_yield, 2)}%` : '—'}
                          </td>
                          <td className="num"><Delta value={s.ret_1y} /></td>
                          <td className="num">{fmt.num(s.total_score, 1)}</td>
                          <td><Grade grade={s.grade} /></td>
                          <td className="muted" style={{ fontSize: 11 }}>
                            {fmt.date(s.added_at)}
                          </td>
                          <td>
                            <button className="ghost sm"
                                    onClick={() => removeTicker(s.ticker)}>
                              Remove
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
          </Card>
        </div>
      </div>
    </>
  )
}
