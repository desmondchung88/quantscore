import { useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { Card, Empty, ErrorBox, Loading, Stat } from '../components/ui'
import { api, fmt } from '../lib/api'
import { useApi } from '../lib/hooks'

const AXIS = { stroke: '#94a3c4', fontSize: 11 }
const TOOLTIP = {
  contentStyle: {
    background: '#16203a', border: '1px solid #253356',
    borderRadius: 8, fontSize: 12,
  },
}

export default function Benchmark() {
  const [ticker, setTicker] = useState('AAPL')
  const [runs, setRuns] = useState(5)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const plans = useApi('/benchmark/explain', { ticker })
  const indexTest = useApi('/benchmark/index-impact', { ticker, runs: 3 })

  async function run() {
    setLoading(true); setError(null)
    try {
      setResult(await api.get('/benchmark/run',
                              { ticker: ticker.toUpperCase(), runs, days: 2200 }))
    } catch (e) {
      setError(e)
    } finally {
      setLoading(false)
    }
  }

  const chart = (result?.scenarios || [])
    .filter((s) => s.mysql.median_ms !== null && s.mongodb.median_ms !== null)
    .map((s) => ({
      name: s.name,
      MySQL: s.mysql.median_ms,
      MongoDB: s.mongodb.median_ms,
    }))

  const sizes = result?.dataset_sizes

  return (
    <>
      <div className="page-head">
        <div>
          <h1>SQL vs NoSQL</h1>
          <p>
            Both engines hold the same two datasets, so each scenario is the
            same question asked twice. Every query runs once to warm the cache
            and then several more times; the median is reported.
          </p>
        </div>
        <div className="row">
          <input value={ticker} style={{ width: 100 }}
                 onChange={(e) => setTicker(e.target.value.toUpperCase())} />
          <select value={runs} style={{ width: 110 }}
                  onChange={(e) => setRuns(Number(e.target.value))}>
            {[3, 5, 7, 10].map((n) => <option key={n} value={n}>{n} runs</option>)}
          </select>
          <button onClick={run} disabled={loading}>
            {loading ? 'Benchmarking…' : 'Run benchmark'}
          </button>
        </div>
      </div>

      <ErrorBox error={error} />

      {sizes && (
        <div className="grid cols-4" style={{ marginBottom: 16 }}>
          <Stat label="News rows (MySQL)"
                value={sizes.mysql_bench_news.toLocaleString()} />
          <Stat label="News documents (MongoDB)"
                value={sizes.mongo_news_articles.toLocaleString()} />
          <Stat label="Price rows (MySQL)"
                value={sizes.mysql_stock_prices.toLocaleString()} />
          <Stat label="Price documents (MongoDB)"
                value={sizes.mongo_bench_prices.toLocaleString()} />
        </div>
      )}

      {loading ? <Loading what="benchmark results" />
        : !result ? (
          <Card>
            <Empty>
              Press <strong>Run benchmark</strong> to time seven query shapes
              across both engines.
            </Empty>
          </Card>
        ) : (
          <>
            <div className="grid cols-4" style={{ marginBottom: 16 }}>
              <Stat label="Scenarios" value={result.summary.scenarios_run} />
              <Stat label="MySQL wins" value={result.summary.mysql_wins} />
              <Stat label="MongoDB wins" value={result.summary.mongodb_wins} />
              <Stat label="Total time"
                    value={`${result.summary.total_mysql_ms} / ${result.summary.total_mongodb_ms} ms`}
                    note="MySQL / MongoDB, summed medians" />
            </div>

            <Card title="Median latency by scenario" sub="Lower is better (ms)">
              {!chart.length ? <Empty /> : (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={chart} margin={{ bottom: 40 }}>
                    <CartesianGrid stroke="#253356" vertical={false} />
                    <XAxis dataKey="name" {...AXIS} angle={-18}
                           textAnchor="end" interval={0} height={60} />
                    <YAxis {...AXIS} width={56} />
                    <Tooltip {...TOOLTIP} formatter={(v) => `${v} ms`} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Bar dataKey="MySQL" fill="#4f8cff" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="MongoDB" fill="#2fbf71" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </Card>

            <div style={{ height: 16 }} />

            <Card title="Detailed results" sub={result.method}>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Scenario</th><th>Dataset</th>
                      <th className="num">MySQL median</th>
                      <th className="num">MongoDB median</th>
                      <th className="num">Rows</th>
                      <th>Faster</th><th className="num">By</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.scenarios.map((s) => (
                      <tr key={s.key}>
                        <td>
                          <div>{s.name}</div>
                          <div className="muted" style={{ fontSize: 11 }}>
                            {s.description}
                          </div>
                          <div className="muted mono" style={{ fontSize: 10 }}>
                            {s.indexes}
                          </div>
                        </td>
                        <td className="muted">{s.dataset}</td>
                        <td className="num">
                          {s.mysql.median_ms !== null
                            ? `${s.mysql.median_ms} ms`
                            : <span className="neg">{s.mysql.error}</span>}
                          {s.mysql.stdev_ms !== undefined && (
                            <div className="muted" style={{ fontSize: 10 }}>
                              ±{s.mysql.stdev_ms}
                            </div>
                          )}
                        </td>
                        <td className="num">
                          {s.mongodb.median_ms !== null
                            ? `${s.mongodb.median_ms} ms`
                            : <span className="neg">{s.mongodb.error}</span>}
                          {s.mongodb.stdev_ms !== undefined && (
                            <div className="muted" style={{ fontSize: 10 }}>
                              ±{s.mongodb.stdev_ms}
                            </div>
                          )}
                        </td>
                        <td className="num muted">
                          {s.mysql.rows_returned ?? '—'} / {s.mongodb.rows_returned ?? '—'}
                        </td>
                        <td>
                          <span className={`badge ${s.faster === 'mysql' ? 'pos'
                            : s.faster === 'mongodb' ? 'neg' : 'neutral'}`}>
                            {s.faster}
                          </span>
                        </td>
                        <td className="num">{s.speedup ? `${s.speedup}×` : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </>
        )}

      <div style={{ height: 16 }} />

      <div className="grid cols-2">
        <Card title="What the index is worth"
              sub="The same query with and without idx_bench_ticker_time">
          {indexTest.loading ? <Loading /> : !indexTest.data ? <Empty /> : (
            <>
              <table>
                <tbody>
                  <tr>
                    <td>With the index</td>
                    <td className="num pos">
                      {indexTest.data.with_index.median_ms} ms
                    </td>
                  </tr>
                  <tr>
                    <td>Forced full scan</td>
                    <td className="num neg">
                      {indexTest.data.without_index.median_ms} ms
                    </td>
                  </tr>
                  <tr>
                    <td style={{ fontWeight: 650 }}>Speed-up</td>
                    <td className="num" style={{ fontWeight: 700 }}>
                      {indexTest.data.speedup ? `${indexTest.data.speedup}×` : '—'}
                    </td>
                  </tr>
                </tbody>
              </table>
              <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
                {indexTest.data.note}
              </p>
            </>
          )}
        </Card>

        <Card title="Query plans" sub="MySQL EXPLAIN next to the MongoDB winning plan">
          {plans.loading ? <Loading /> : !plans.data ? <Empty /> : (
            <>
              <div className="label">MySQL</div>
              <pre className="sql">
                {JSON.stringify(plans.data.mysql_explain, null, 2)}
              </pre>
              <div className="label" style={{ marginTop: 12 }}>MongoDB</div>
              <pre className="sql">
                {JSON.stringify(plans.data.mongodb_winning_plan, null, 2)}
              </pre>
            </>
          )}
        </Card>
      </div>
    </>
  )
}
