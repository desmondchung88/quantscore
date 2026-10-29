import { useEffect, useState } from 'react'
import {
  Card, Delta, Empty, ErrorBox, Grade, Loading, ScoreBar, Stat, Ticker,
} from '../components/ui'
import { api, fmt } from '../lib/api'
import { useApi } from '../lib/hooks'

const NUMERIC = [
  { key: 'market_cap', label: 'Market cap ($)', step: 1e9 },
  { key: 'pe_ratio', label: 'P/E ratio' },
  { key: 'price_sales_ratio', label: 'P/S ratio' },
  { key: 'price_book_ratio', label: 'P/B ratio' },
  { key: 'dividend_yield', label: 'Dividend yield (%)' },
  { key: 'eps', label: 'EPS ($)' },
  { key: 'ret_1y', label: '1-year return (0.1 = 10%)' },
  { key: 'total_score', label: 'QuantScore' },
]

const COLUMNS = [
  { key: 'ticker', label: 'Ticker' },
  { key: 'company_name', label: 'Company' },
  { key: 'sector_name', label: 'Sector' },
  { key: 'last_close', label: 'Last', num: true },
  { key: 'market_cap', label: 'Market cap', num: true },
  { key: 'pe_ratio', label: 'P/E', num: true },
  { key: 'price_sales_ratio', label: 'P/S', num: true },
  { key: 'dividend_yield', label: 'Yield', num: true },
  { key: 'ret_1y', label: '1y', num: true },
  { key: 'total_score', label: 'Score', num: true },
]

const EMPTY = { sectors: [], grades: [], exclude_null_pe: false }

export default function Screener() {
  const options = useApi('/screener/options')
  const [filters, setFilters] = useState(EMPTY)
  const [sortBy, setSortBy] = useState('total_score')
  const [sortDir, setSortDir] = useState('desc')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState([])
  const [comparison, setComparison] = useState(null)

  async function run(overrides = {}) {
    setLoading(true); setError(null)
    const body = {
      ...Object.fromEntries(
        Object.entries(filters).filter(([, v]) =>
          v !== '' && v !== null && v !== undefined &&
          !(Array.isArray(v) && v.length === 0)),
      ),
      sort_by: sortBy, sort_dir: sortDir, limit: 100,
      ...overrides,
    }
    try {
      setResult(await api.post('/screener/run', body))
    } catch (e) {
      setError(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { run() }, [sortBy, sortDir]) // eslint-disable-line

  function setNum(key, value) {
    setFilters((f) => ({ ...f, [key]: value === '' ? undefined : Number(value) }))
  }

  function toggleArray(key, value) {
    setFilters((f) => {
      const current = f[key] || []
      return {
        ...f,
        [key]: current.includes(value)
          ? current.filter((v) => v !== value)
          : [...current, value],
      }
    })
  }

  function toggleSelect(ticker) {
    setSelected((s) => s.includes(ticker)
      ? s.filter((t) => t !== ticker)
      : s.length >= 8 ? s : [...s, ticker])
  }

  async function compare() {
    if (selected.length < 2) return
    setComparison(await api.post('/screener/compare', { tickers: selected }))
  }

  function sortOn(key) {
    if (sortBy === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortBy(key); setSortDir('desc') }
  }

  const stats = result?.stats

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Screener</h1>
          <p>
            Compose filters across fundamentals, returns and QuantScore factors.
            Every filter becomes a bound parameter in one SQL statement; the
            summary row aggregates the whole match set, not just this page.
          </p>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: '300px minmax(0,1fr)' }}>
        <div>
          <Card title="Filters">
            <div className="field">
              <label>Search</label>
              <input placeholder="Ticker or name"
                     value={filters.search || ''}
                     onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))} />
            </div>

            {NUMERIC.map((n) => (
              <div className="field" key={n.key}>
                <label>{n.label}</label>
                <div className="row" style={{ flexWrap: 'nowrap' }}>
                  <input type="number" placeholder="min"
                         value={filters[`min_${n.key}`] ?? ''}
                         onChange={(e) => setNum(`min_${n.key}`, e.target.value)} />
                  <input type="number" placeholder="max"
                         value={filters[`max_${n.key}`] ?? ''}
                         onChange={(e) => setNum(`max_${n.key}`, e.target.value)} />
                </div>
              </div>
            ))}

            <div className="field">
              <label>Grades</label>
              <div className="row" style={{ gap: 4 }}>
                {(options.data?.grades || []).map((g) => (
                  <button key={g}
                          className={`sm ${(filters.grades || []).includes(g) ? '' : 'ghost'}`}
                          onClick={() => toggleArray('grades', g)}>
                    {g}
                  </button>
                ))}
              </div>
            </div>

            <div className="field">
              <label>Sectors</label>
              <div style={{ maxHeight: 180, overflowY: 'auto' }}>
                {(options.data?.sectors || []).map((s) => (
                  <label key={s.sector_name}
                         style={{ display: 'flex', gap: 8, alignItems: 'center',
                                  marginBottom: 4, color: 'var(--text)' }}>
                    <input type="checkbox" style={{ width: 'auto' }}
                           checked={(filters.sectors || []).includes(s.sector_name)}
                           onChange={() => toggleArray('sectors', s.sector_name)} />
                    <span style={{ fontSize: 12 }}>
                      {s.sector_name} <span className="muted">({s.companies})</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <label style={{ display: 'flex', gap: 8, alignItems: 'center',
                            color: 'var(--text)', marginBottom: 12 }}>
              <input type="checkbox" style={{ width: 'auto' }}
                     checked={!!filters.exclude_null_pe}
                     onChange={(e) => setFilters((f) =>
                       ({ ...f, exclude_null_pe: e.target.checked }))} />
              <span style={{ fontSize: 12 }}>Profitable only (P/E &gt; 0)</span>
            </label>

            <div className="row">
              <button onClick={() => run()} disabled={loading}>
                {loading ? 'Running…' : 'Run screen'}
              </button>
              <button className="ghost" onClick={() => { setFilters(EMPTY); setSelected([]) }}>
                Reset
              </button>
            </div>
          </Card>
        </div>

        <div>
          <ErrorBox error={error} />

          {stats && (
            <div className="grid cols-4" style={{ marginBottom: 16 }}>
              <Stat label="Matches" value={stats.matches}
                    note={`${stats.sectors_covered} sectors`} />
              <Stat label="Avg QuantScore" value={fmt.num(stats.avg_score, 1)} />
              <Stat label="Avg P/E" value={fmt.num(stats.avg_pe, 1)}
                    note={`Avg yield ${fmt.num(stats.avg_dividend_yield, 2)}%`} />
              <Stat label="Combined market cap"
                    value={fmt.compact(stats.total_market_cap)}
                    note={`Avg 1y ${fmt.num(stats.avg_ret_1y_pct, 1)}%`} />
            </div>
          )}

          <Card
            title={`Results${result ? ` (${result.results.length} shown)` : ''}`}
            actions={
              <div className="row">
                <span className="muted" style={{ fontSize: 12 }}>
                  {selected.length} selected
                </span>
                <button className="sm" disabled={selected.length < 2} onClick={compare}>
                  Compare
                </button>
              </div>
            }
          >
            {loading ? <Loading what="results" />
              : !result?.results?.length ? <Empty>No company matches these filters.</Empty>
              : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th />
                        {COLUMNS.map((c) => (
                          <th key={c.key}
                              className={`sortable ${c.num ? 'num' : ''}`}
                              onClick={() => sortOn(c.key)}>
                            {c.label}
                            {sortBy === c.key && (sortDir === 'asc' ? ' ▲' : ' ▼')}
                          </th>
                        ))}
                        <th>Grade</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.results.map((r) => (
                        <tr key={r.ticker}>
                          <td>
                            <input type="checkbox" style={{ width: 'auto' }}
                                   checked={selected.includes(r.ticker)}
                                   onChange={() => toggleSelect(r.ticker)} />
                          </td>
                          <td><Ticker symbol={r.ticker} /></td>
                          <td style={{ maxWidth: 170, overflow: 'hidden',
                                       textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {r.company_name}
                          </td>
                          <td className="muted" style={{ fontSize: 12 }}>
                            {r.sector_name}
                          </td>
                          <td className="num">{fmt.money(r.last_close)}</td>
                          <td className="num">{fmt.compact(r.market_cap)}</td>
                          <td className="num">{fmt.num(r.pe_ratio, 1)}</td>
                          <td className="num">{fmt.num(r.price_sales_ratio, 2)}</td>
                          <td className="num">
                            {r.dividend_yield ? `${fmt.num(r.dividend_yield, 2)}%` : '—'}
                          </td>
                          <td className="num"><Delta value={r.ret_1y} /></td>
                          <td className="num">{fmt.num(r.total_score, 1)}</td>
                          <td><Grade grade={r.grade} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
          </Card>

          {result?.by_sector?.length > 1 && (
            <>
              <div style={{ height: 16 }} />
              <Card title="Matches by sector"
                    sub="GROUP BY over the same filtered set">
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr><th>Sector</th><th className="num">Companies</th>
                          <th className="num">Avg score</th></tr>
                    </thead>
                    <tbody>
                      {result.by_sector.map((s) => (
                        <tr key={s.sector_name}>
                          <td>{s.sector_name}</td>
                          <td className="num">{s.companies}</td>
                          <td className="num">{fmt.num(s.avg_score, 1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </>
          )}

          {comparison?.stocks?.length > 0 && (
            <>
              <div style={{ height: 16 }} />
              <Card title="Side-by-side comparison"
                    actions={<button className="ghost sm"
                                     onClick={() => setComparison(null)}>Close</button>}>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Metric</th>
                        {comparison.stocks.map((s) => (
                          <th key={s.ticker} className="num">{s.ticker}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        ['Company', (s) => s.company_name],
                        ['Sector', (s) => s.sector_name],
                        ['Last close', (s) => fmt.money(s.last_close)],
                        ['Market cap', (s) => fmt.compact(s.market_cap)],
                        ['P/E', (s) => fmt.num(s.pe_ratio, 1)],
                        ['P/S', (s) => fmt.num(s.price_sales_ratio, 2)],
                        ['P/B', (s) => fmt.num(s.price_book_ratio, 2)],
                        ['Dividend yield', (s) => s.dividend_yield
                          ? `${fmt.num(s.dividend_yield, 2)}%` : '—'],
                        ['EPS', (s) => fmt.money(s.eps)],
                        ['1-year return', (s) => fmt.pct(s.ret_1y)],
                        ['Valuation', (s) => fmt.num(s.valuation_score, 1)],
                        ['Profitability', (s) => fmt.num(s.profitability_score, 1)],
                        ['Growth', (s) => fmt.num(s.growth_score, 1)],
                        ['Dividend', (s) => fmt.num(s.dividend_score, 1)],
                        ['QuantScore', (s) => fmt.num(s.total_score, 1)],
                        ['Grade', (s) => s.grade],
                      ].map(([label, get]) => (
                        <tr key={label}>
                          <td className="muted">{label}</td>
                          {comparison.stocks.map((s) => (
                            <td key={s.ticker} className="num">{get(s)}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </>
          )}
        </div>
      </div>
    </>
  )
}
