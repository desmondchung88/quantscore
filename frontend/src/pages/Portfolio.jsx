import { useEffect, useState } from 'react'
import {
  Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  Card, Delta, Empty, ErrorBox, Grade, Loading, Stat, Ticker,
} from '../components/ui'
import { api, fmt } from '../lib/api'
import { useAction, useApi } from '../lib/hooks'

const AXIS = { stroke: '#94a3c4', fontSize: 11 }
const TOOLTIP = {
  contentStyle: {
    background: '#16203a', border: '1px solid #253356',
    borderRadius: 8, fontSize: 12,
  },
}
const PIE = ['#4f8cff', '#2fbf71', '#e7b43c', '#f0584f', '#a97bff',
             '#38c6d9', '#f08f4f', '#7ad67a', '#d97ab0', '#8da2c9']

export default function Portfolio() {
  const list = useApi('/portfolios')
  const [active, setActive] = useState(null)
  const [tab, setTab] = useState('holdings')
  const trade = useAction()
  const manage = useAction()

  const [form, setForm] = useState({ ticker: '', side: 'BUY', quantity: 10 })
  const [newName, setNewName] = useState('')

  useEffect(() => {
    const items = list.data?.portfolios || []
    if (items.length && !items.some((p) => p.portfolio_id === active)) {
      setActive(items[0].portfolio_id)
    }
  }, [list.data, active])

  const detail = useApi(active ? `/portfolios/${active}` : null)
  const risk = useApi(active ? `/portfolios/${active}/risk` : null, { days: 365 })
  const series = useApi(active ? `/portfolios/${active}/history` : null, { days: 365 })

  function refreshAll() {
    list.reload(); detail.reload(); risk.reload(); series.reload()
  }

  async function submitTrade(e) {
    e.preventDefault()
    if (!form.ticker.trim()) return
    await trade.run(
      () => api.post(`/portfolios/${active}/trade`, {
        ticker: form.ticker.trim().toUpperCase(),
        side: form.side,
        quantity: Number(form.quantity),
      }),
      `${form.side} ${form.quantity} ${form.ticker.toUpperCase()} executed`,
    ).then(refreshAll).catch(() => {})
  }

  async function createPortfolio() {
    if (!newName.trim()) return
    await manage.run(
      () => api.post('/portfolios', { name: newName.trim(), initial_cash: 100000 }),
      'Portfolio created',
    ).then(() => { setNewName(''); list.reload() }).catch(() => {})
  }

  async function deletePortfolio() {
    if (!active) return
    if (!confirm('Delete this portfolio and its entire trade history?')) return
    await manage.run(() => api.del(`/portfolios/${active}`), 'Portfolio deleted')
      .then(() => { setActive(null); list.reload() }).catch(() => {})
  }

  const summary = detail.data?.summary
  const holdings = detail.data?.holdings || []
  const analytics = risk.data || {}

  const valueSeries = (series.data?.series || []).map((p) => ({
    date: String(p.price_date).slice(0, 10),
    value: p.value,
  }))

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Virtual portfolio</h1>
          <p>
            Trades run through the <code>sp_execute_trade</code> stored
            procedure: it locks the portfolio row, checks your cash or your
            holdings in a trigger, writes the ledger entry and commits — or
            rolls the whole thing back.
          </p>
        </div>
        <div className="row">
          <select value={active || ''} style={{ width: 200 }}
                  onChange={(e) => setActive(Number(e.target.value))}>
            {(list.data?.portfolios || []).map((p) => (
              <option key={p.portfolio_id} value={p.portfolio_id}>{p.name}</option>
            ))}
          </select>
          <button className="ghost" onClick={deletePortfolio} disabled={!active}>
            Delete
          </button>
        </div>
      </div>

      <ErrorBox error={list.error || manage.error} />
      {manage.message && <div className="ok-box">{manage.message}</div>}

      {list.loading ? <Loading what="portfolios" />
        : !(list.data?.portfolios || []).length ? (
          <Card title="Create your first portfolio">
            <div className="row">
              <input placeholder="Portfolio name" value={newName}
                     style={{ maxWidth: 260 }}
                     onChange={(e) => setNewName(e.target.value)} />
              <button onClick={createPortfolio} disabled={manage.pending}>
                Create with $100,000
              </button>
            </div>
          </Card>
        ) : (
        <>
          <div className="grid cols-4" style={{ marginBottom: 16 }}>
            <Stat label="Total value" value={fmt.money(summary?.total_value)}
                  note={`Cash ${fmt.money(summary?.cash_balance)}`} />
            <Stat label="Market value" value={fmt.money(summary?.market_value)}
                  note={`${summary?.positions || 0} positions`} />
            <Stat label="Total P&L"
                  value={fmt.money(summary?.total_pnl)}
                  tone={(summary?.total_pnl || 0) >= 0 ? 'pos' : 'neg'}
                  note={summary?.total_return !== null
                    && summary?.total_return !== undefined
                    ? fmt.pct(summary.total_return) : null} />
            <Stat label="Cost basis" value={fmt.money(summary?.cost_basis)}
                  note={`Started with ${fmt.money(summary?.initial_cash)}`} />
          </div>

          <div className="grid cols-2" style={{ marginBottom: 16 }}>
            <Card title="Place a simulated trade"
                  sub="Executed at the most recent close in the database">
              <form onSubmit={submitTrade}>
                <div className="row" style={{ flexWrap: 'nowrap', alignItems: 'flex-end' }}>
                  <div className="field" style={{ flex: 2, marginBottom: 0 }}>
                    <label>Ticker</label>
                    <input placeholder="AAPL" value={form.ticker}
                           onChange={(e) => setForm({ ...form, ticker: e.target.value })} />
                  </div>
                  <div className="field" style={{ flex: 1, marginBottom: 0 }}>
                    <label>Side</label>
                    <select value={form.side}
                            onChange={(e) => setForm({ ...form, side: e.target.value })}>
                      <option>BUY</option><option>SELL</option>
                    </select>
                  </div>
                  <div className="field" style={{ flex: 1, marginBottom: 0 }}>
                    <label>Quantity</label>
                    <input type="number" min="0.000001" step="any" value={form.quantity}
                           onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
                  </div>
                  <button type="submit" disabled={trade.pending}>
                    {trade.pending ? '…' : 'Execute'}
                  </button>
                </div>
              </form>
              <div style={{ marginTop: 12 }}>
                <ErrorBox error={trade.error} />
                {trade.message && <div className="ok-box">{trade.message}</div>}
              </div>
              <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
                Try selling more shares than you own, or buying beyond your cash —
                the database refuses both and the transaction rolls back.
              </p>
            </Card>

            <Card title="Portfolio value"
                  sub="Current positions valued back through history">
              {series.loading ? <Loading /> : !valueSeries.length ? (
                <Empty>Buy something to see a value series.</Empty>
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={valueSeries}>
                    <defs>
                      <linearGradient id="pv" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#2fbf71" stopOpacity={0.45} />
                        <stop offset="100%" stopColor="#2fbf71" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#253356" vertical={false} />
                    <XAxis dataKey="date" {...AXIS} minTickGap={40} />
                    <YAxis {...AXIS} width={64}
                           tickFormatter={(v) => fmt.compact(v)} />
                    <Tooltip {...TOOLTIP} formatter={(v) => fmt.money(v)} />
                    <Area type="monotone" dataKey="value" stroke="#2fbf71"
                          fill="url(#pv)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </Card>
          </div>

          <div className="tabs">
            {['holdings', 'risk', 'transactions'].map((t) => (
              <div key={t} className={`tab ${tab === t ? 'active' : ''}`}
                   onClick={() => setTab(t)}
                   style={{ textTransform: 'capitalize' }}>
                {t === 'risk' ? 'Risk analytics' : t}
              </div>
            ))}
          </div>

          {tab === 'holdings' && (
            <Card title="Holdings" sub="Derived from the transaction ledger by v_portfolio_holdings">
              {detail.loading ? <Loading /> : !holdings.length ? (
                <Empty>No open positions.</Empty>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Ticker</th><th>Company</th><th>Sector</th>
                        <th className="num">Qty</th><th className="num">Avg cost</th>
                        <th className="num">Last</th><th className="num">Value</th>
                        <th className="num">Unrealised</th><th className="num">Weight</th>
                        <th>Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {holdings.map((h) => (
                        <tr key={h.stock_id}>
                          <td><Ticker symbol={h.ticker} /></td>
                          <td style={{ maxWidth: 160, overflow: 'hidden',
                                       textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {h.company_name}
                          </td>
                          <td className="muted" style={{ fontSize: 12 }}>
                            {h.sector_name}
                          </td>
                          <td className="num">{fmt.num(h.net_quantity, 2)}</td>
                          <td className="num">{fmt.money(h.avg_cost)}</td>
                          <td className="num">{fmt.money(h.last_close)}</td>
                          <td className="num">{fmt.money(h.market_value)}</td>
                          <td className="num">
                            <span className={h.unrealised_pnl >= 0 ? 'pos' : 'neg'}>
                              {fmt.money(h.unrealised_pnl)}
                            </span>{' '}
                            <Delta value={h.unrealised_pct} />
                          </td>
                          <td className="num">{fmt.pct(h.weight, 1)}</td>
                          <td className="row" style={{ gap: 6 }}>
                            <Grade grade={h.grade} />
                            <span className="muted">{fmt.num(h.total_score, 0)}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          )}

          {tab === 'risk' && (
            risk.loading ? <Loading what="risk analytics" /> : (
              <>
                <div className="grid cols-4" style={{ marginBottom: 16 }}>
                  <Stat label="Annualised volatility"
                        value={fmt.pct(analytics.annualised_volatility)}
                        note={`${analytics.observations || 0} trading days`} />
                  <Stat label="Sharpe ratio"
                        value={fmt.num(analytics.sharpe_ratio, 2)}
                        note="vs 2% risk-free" />
                  <Stat label="Max drawdown"
                        value={fmt.pct(analytics.max_drawdown)} tone="neg"
                        note="Peak to trough" />
                  <Stat label="Beta"
                        value={analytics.beta === null || analytics.beta === undefined
                          ? 'n/a' : fmt.num(analytics.beta, 2)}
                        note={analytics.beta_basis
                          ? `vs ${analytics.beta_basis}` : 'no benchmark available'} />
                </div>

                <div className="grid cols-2">
                  <Card title="Risk measures">
                    {analytics.note ? <Empty>{analytics.note}</Empty> : (
                      <div className="table-wrap">
                        <table>
                          <tbody>
                            {[
                              ['Period return', fmt.pct(analytics.period_return)],
                              ['Annualised return', fmt.pct(analytics.annualised_return)],
                              ['Daily volatility', fmt.pct(analytics.daily_volatility)],
                              ['Value at risk (95%, 1 day)', fmt.pct(analytics.var_95_daily)],
                              ['Conditional VaR (95%)', fmt.pct(analytics.cvar_95_daily)],
                              ['Best day', fmt.pct(analytics.best_day)],
                              ['Worst day', fmt.pct(analytics.worst_day)],
                              ['Positive days', fmt.pct(analytics.positive_days_pct, 1)],
                            ].map(([k, v]) => (
                              <tr key={k}>
                                <td className="muted">{k}</td>
                                <td className="num">{v}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    {analytics.concentration && (
                      <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
                        Concentration (HHI) {fmt.num(analytics.concentration.hhi, 3)} —{' '}
                        <strong>{analytics.concentration.verdict}</strong>. Largest
                        position {analytics.concentration.largest_position_pct}% of the
                        book, effective number of positions{' '}
                        {fmt.num(analytics.concentration.effective_positions, 1)}.
                      </p>
                    )}
                  </Card>

                  <Card title="Sector allocation">
                    {!(analytics.sector_allocation || []).length ? <Empty /> : (
                      <ResponsiveContainer width="100%" height={260}>
                        <PieChart>
                          <Pie data={analytics.sector_allocation} dataKey="market_value"
                               nameKey="sector_name" innerRadius={55} outerRadius={95}
                               paddingAngle={2}>
                            {analytics.sector_allocation.map((_, i) => (
                              <Cell key={i} fill={PIE[i % PIE.length]} />
                            ))}
                          </Pie>
                          <Tooltip {...TOOLTIP} formatter={(v) => fmt.money(v)} />
                        </PieChart>
                      </ResponsiveContainer>
                    )}
                    <div className="row" style={{ gap: 8, fontSize: 11 }}>
                      {(analytics.sector_allocation || []).map((s, i) => (
                        <span key={s.sector_name} className="badge">
                          <span style={{ color: PIE[i % PIE.length] }}>●</span>{' '}
                          {s.sector_name}
                        </span>
                      ))}
                    </div>
                  </Card>
                </div>
              </>
            )
          )}

          {tab === 'transactions' && (
            <Card title="Trade ledger" sub="Every row written by sp_execute_trade">
              {!(detail.data?.transactions || []).length ? <Empty /> : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>When</th><th>Side</th><th>Ticker</th><th>Company</th>
                        <th className="num">Qty</th><th className="num">Price</th>
                        <th className="num">Gross</th><th className="num">Fees</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.data.transactions.map((t) => (
                        <tr key={t.transaction_id}>
                          <td className="muted">{fmt.dateTime(t.executed_at)}</td>
                          <td>
                            <span className={`badge ${t.transaction_type === 'BUY'
                              ? 'pos' : 'neg'}`}>{t.transaction_type}</span>
                          </td>
                          <td><Ticker symbol={t.ticker} /></td>
                          <td style={{ maxWidth: 180, overflow: 'hidden',
                                       textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {t.company_name}
                          </td>
                          <td className="num">{fmt.num(t.quantity, 2)}</td>
                          <td className="num">{fmt.money(t.execution_price)}</td>
                          <td className="num">{fmt.money(t.gross_value)}</td>
                          <td className="num muted">{fmt.money(t.fees, 4)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          )}

          <div style={{ height: 16 }} />
          <Card title="New portfolio">
            <div className="row">
              <input placeholder="Portfolio name" value={newName}
                     style={{ maxWidth: 260 }}
                     onChange={(e) => setNewName(e.target.value)} />
              <button className="ghost" onClick={createPortfolio}
                      disabled={manage.pending || !newName.trim()}>
                Create with $100,000
              </button>
            </div>
          </Card>
        </>
      )}
    </>
  )
}
