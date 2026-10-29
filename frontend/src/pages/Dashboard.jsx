import { Link } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { Card, Delta, Empty, ErrorBox, Grade, Loading, Stat, Ticker } from '../components/ui'
import { fmt } from '../lib/api'
import { useApi } from '../lib/hooks'

const AXIS = { stroke: '#94a3c4', fontSize: 11 }
const TOOLTIP = {
  contentStyle: {
    background: '#16203a', border: '1px solid #253356',
    borderRadius: 8, fontSize: 12,
  },
}

export default function Dashboard() {
  const stats = useApi('/meta/stats')
  const sectors = useApi('/scores/sectors')
  const movers = useApi('/stocks/movers', { limit: 8 })
  const top = useApi('/scores/leaderboard', { limit: 10 })
  const dist = useApi('/scores/distribution')

  const rel = stats.data?.relational
  const docs = stats.data?.documents

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p>
            S&amp;P 500 research across two databases: MySQL holds the companies,
            fundamentals, prices and your portfolio; MongoDB holds the news,
            sentiment, profiles and notes.
          </p>
        </div>
      </div>

      <ErrorBox error={stats.error} />

      {stats.loading ? (
        <Loading what="database statistics" />
      ) : (
        <div className="grid cols-4" style={{ marginBottom: 16 }}>
          <Stat label="Companies" value={rel?.stocks ?? '—'}
                note={`${rel?.sectors ?? 0} sectors`} />
          <Stat label="Price rows (MySQL)"
                value={(rel?.price_rows ?? 0).toLocaleString()}
                note={rel?.first_price_date
                  ? `${fmt.date(rel.first_price_date)} – ${fmt.date(rel.last_price_date)}`
                  : 'not loaded'} />
          <Stat label="News documents (MongoDB)"
                value={(docs?.news_articles ?? 0).toLocaleString()}
                note={`${(docs?.company_profiles ?? 0).toLocaleString()} company profiles`} />
          <Stat label="Simulated trades"
                value={(rel?.transactions ?? 0).toLocaleString()}
                note={`${rel?.portfolios ?? 0} portfolios, ${rel?.users ?? 0} users`} />
        </div>
      )}

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <Card title="Score distribution"
              sub="How the 500 companies spread across the QuantScore range">
          {dist.loading ? <Loading /> : !dist.data?.buckets?.length ? <Empty /> : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={dist.data.buckets}>
                <CartesianGrid stroke="#253356" vertical={false} />
                <XAxis dataKey="bucket" {...AXIS} />
                <YAxis {...AXIS} />
                <Tooltip {...TOOLTIP} />
                <Bar dataKey="companies" radius={[4, 4, 0, 0]}>
                  {dist.data.buckets.map((b, i) => (
                    <Cell key={i} fill={
                      parseInt(b.bucket, 10) >= 60 ? '#2fbf71'
                        : parseInt(b.bucket, 10) >= 45 ? '#4f8cff' : '#f0584f'
                    } />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Sector league table"
              sub="Market-cap weighted QuantScore, from sp_sector_leaderboard()">
          {sectors.loading ? <Loading /> : !sectors.data?.sectors?.length ? <Empty /> : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Sector</th>
                    <th className="num">Cos.</th>
                    <th className="num">Avg</th>
                    <th className="num">Cap-weighted</th>
                  </tr>
                </thead>
                <tbody>
                  {sectors.data.sectors.map((s) => (
                    <tr key={s.sector_name}>
                      <td>{s.sector_name}</td>
                      <td className="num">{s.companies}</td>
                      <td className="num">{fmt.num(s.avg_score, 1)}</td>
                      <td className="num">{fmt.num(s.cap_weighted_score, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <Card title="Top QuantScores"
              sub="Default weighting: valuation 30, profitability 25, growth 25, dividend 20"
              actions={<Link to="/scores" className="muted">View all →</Link>}>
          {top.loading ? <Loading /> : !top.data?.results?.length ? <Empty /> : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th><th>Ticker</th><th>Company</th>
                    <th className="num">Score</th><th>Grade</th>
                  </tr>
                </thead>
                <tbody>
                  {top.data.results.map((r) => (
                    <tr key={r.ticker}>
                      <td className="muted">{r.overall_rank}</td>
                      <td><Ticker symbol={r.ticker} /></td>
                      <td style={{ maxWidth: 190, overflow: 'hidden',
                                   textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.company_name}
                      </td>
                      <td className="num">{fmt.num(r.weighted_score, 1)}</td>
                      <td><Grade grade={r.grade} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="One-month movers" sub="Computed by sp_refresh_latest_prices()">
          {movers.loading ? <Loading /> : !movers.data ? <Empty /> : (
            <div className="grid cols-2">
              <div>
                <div className="label" style={{ marginBottom: 6 }}>Gainers</div>
                {movers.data.gainers.map((s) => (
                  <div className="row" key={s.ticker}
                       style={{ justifyContent: 'space-between', padding: '4px 0' }}>
                    <Ticker symbol={s.ticker} />
                    <Delta value={s.ret_1m} />
                  </div>
                ))}
              </div>
              <div>
                <div className="label" style={{ marginBottom: 6 }}>Losers</div>
                {movers.data.losers.map((s) => (
                  <div className="row" key={s.ticker}
                       style={{ justifyContent: 'space-between', padding: '4px 0' }}>
                    <Ticker symbol={s.ticker} />
                    <Delta value={s.ret_1m} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>

      <Card title="Datasets loaded" sub="Provenance recorded in the data_imports table">
        {!stats.data?.imports?.length ? <Empty>No imports recorded yet.</Empty> : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Dataset</th><th>Version / period</th>
                  <th className="num">Rows</th><th>Imported</th>
                </tr>
              </thead>
              <tbody>
                {stats.data.imports.map((im, i) => (
                  <tr key={i}>
                    <td>
                      {im.source_url
                        ? <a href={im.source_url} target="_blank" rel="noreferrer">
                            {im.dataset_name}
                          </a>
                        : im.dataset_name}
                    </td>
                    <td className="mono muted">{im.dataset_version}</td>
                    <td className="num">{(im.row_count || 0).toLocaleString()}</td>
                    <td className="muted">{fmt.dateTime(im.imported_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  )
}
