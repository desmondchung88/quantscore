import { useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  Area, AreaChart, CartesianGrid, Legend, Line, PolarAngleAxis, PolarGrid,
  PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  Card, Delta, Empty, ErrorBox, Grade, Loading, SentimentBadge, Stat,
} from '../components/ui'
import { fmt } from '../lib/api'
import { useApi } from '../lib/hooks'

const AXIS = { stroke: '#94a3c4', fontSize: 11 }
const TOOLTIP = {
  contentStyle: {
    background: '#16203a', border: '1px solid #253356',
    borderRadius: 8, fontSize: 12,
  },
}
const RANGES = [
  { label: '6M', days: 126 }, { label: '1Y', days: 252 },
  { label: '3Y', days: 756 }, { label: 'Max', days: 2000 },
]

export default function StockDetail() {
  const { ticker } = useParams()
  const [days, setDays] = useState(252)
  const detail = useApi(`/stocks/${ticker}`)
  const history = useApi(`/stocks/${ticker}/history`, { days })

  if (detail.loading) return <Loading what={ticker} />
  if (detail.error) return <ErrorBox error={detail.error} />
  if (!detail.data) return <Empty />

  const { stock, sector_averages: sector, sector_rank: rank,
          comparisons, sentiment, profile } = detail.data

  const radar = [
    { factor: 'Valuation', score: stock.valuation_score, sector: 50 },
    { factor: 'Profitability', score: stock.profitability_score, sector: 50 },
    { factor: 'Growth', score: stock.growth_score, sector: 50 },
    { factor: 'Dividend', score: stock.dividend_score, sector: 50 },
  ]

  const series = (history.data?.history || []).map((p) => ({
    date: String(p.price_date).slice(0, 10),
    close: p.close_price,
    ma50: p.ma50,
  }))

  return (
    <>
      <div className="page-head">
        <div>
          <h1>
            {stock.ticker}{' '}
            <span className="muted" style={{ fontSize: 18, fontWeight: 400 }}>
              {stock.name || stock.company_name}
            </span>
          </h1>
          <p>
            {stock.sector_name}
            {rank && ` · ranked ${rank.rnk} of ${rank.n} in its sector`}
            {stock.last_price_date && ` · last close ${fmt.date(stock.last_price_date)}`}
          </p>
        </div>
        <div className="row">
          <Grade grade={stock.grade} />
          <div className="stat" style={{ alignItems: 'flex-end' }}>
            <span className="label">QuantScore</span>
            <span className="value">{fmt.num(stock.total_score, 1)}</span>
          </div>
        </div>
      </div>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <Stat label="Last close" value={fmt.money(stock.last_close)}
              note={stock.snapshot_price
                ? `Snapshot ${fmt.money(stock.snapshot_price)}` : null} />
        <Stat label="Market cap" value={fmt.compact(stock.market_cap)}
              note={stock.ebitda ? `EBITDA ${fmt.compact(stock.ebitda)}` : null} />
        <Stat label="1-year return"
              value={<Delta value={stock.ret_1y} />}
              note={`30d vol ${fmt.pct(stock.vol_30d)}`} />
        <Stat label="52-week range"
              value={`${fmt.num(stock.week52_low, 0)}–${fmt.num(stock.week52_high, 0)}`}
              note={stock.range_position !== null && stock.range_position !== undefined
                ? `${(stock.range_position * 100).toFixed(0)}% of the way up`
                : null} />
      </div>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <Card title="Price history"
              actions={
                <div className="row" style={{ gap: 4 }}>
                  {RANGES.map((r) => (
                    <button key={r.days}
                            className={`sm ${days === r.days ? '' : 'ghost'}`}
                            onClick={() => setDays(r.days)}>
                      {r.label}
                    </button>
                  ))}
                </div>
              }>
          {history.loading ? <Loading what="prices" /> : !series.length ? <Empty /> : (
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={series}>
                <defs>
                  <linearGradient id="px" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#4f8cff" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="#4f8cff" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#253356" vertical={false} />
                <XAxis dataKey="date" {...AXIS} minTickGap={40} />
                <YAxis {...AXIS} domain={['auto', 'auto']} width={56} />
                <Tooltip {...TOOLTIP} formatter={(v) => fmt.money(v)} />
                <Area type="monotone" dataKey="close" stroke="#4f8cff"
                      fill="url(#px)" strokeWidth={2} name="Close" />
                <Line type="monotone" dataKey="ma50" stroke="#e7b43c"
                      dot={false} strokeWidth={1.4} name="50-day MA" />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="QuantScore breakdown"
              sub="50 is the sector average; higher is better than the sector">
          <ResponsiveContainer width="100%" height={260}>
            <RadarChart data={radar} outerRadius="72%">
              <PolarGrid stroke="#253356" />
              <PolarAngleAxis dataKey="factor" {...AXIS} />
              <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
              <Radar name={stock.ticker} dataKey="score" stroke="#4f8cff"
                     fill="#4f8cff" fillOpacity={0.4} />
              <Radar name="Sector average" dataKey="sector" stroke="#94a3c4"
                     fill="#94a3c4" fillOpacity={0.08} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Tooltip {...TOOLTIP} />
            </RadarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <Card title="Versus its sector"
              sub={sector ? `${sector.sector_name}, ${sector.company_count} companies`
                          : null}>
          {!comparisons?.length ? <Empty>No comparable ratios available.</Empty> : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th className="num">{stock.ticker}</th>
                    <th className="num">Sector avg</th>
                    <th className="num">Difference</th>
                    <th>Read</th>
                  </tr>
                </thead>
                <tbody>
                  {comparisons.map((c) => (
                    <tr key={c.metric}>
                      <td>{c.metric}</td>
                      <td className="num">{fmt.num(c.value, 2)}</td>
                      <td className="num muted">{fmt.num(c.sector_average, 2)}</td>
                      <td className="num">
                        <span className={c.verdict.startsWith('better') ? 'pos' : 'neg'}>
                          {c.delta_pct > 0 ? '+' : ''}{c.delta_pct}%
                        </span>
                      </td>
                      <td className="muted" style={{ fontSize: 12 }}>{c.verdict}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="News sentiment"
              sub={sentiment ? `${sentiment.articles.toLocaleString()} headlines in the last ${sentiment.window_days} days (MongoDB)` : null}>
          {!sentiment || !sentiment.articles ? (
            <Empty>No headlines for this ticker in the loaded window.</Empty>
          ) : (
            <>
              <div className="row" style={{ gap: 18, marginBottom: 12 }}>
                <div className="stat">
                  <span className="label">Average score</span>
                  <span className={`value ${sentiment.avg_sentiment > 0 ? 'pos'
                                   : sentiment.avg_sentiment < 0 ? 'neg' : ''}`}>
                    {sentiment.avg_sentiment > 0 ? '+' : ''}
                    {fmt.num(sentiment.avg_sentiment, 3)}
                  </span>
                </div>
                <div className="row" style={{ gap: 6 }}>
                  <span className="badge pos">{sentiment.positive} positive</span>
                  <span className="badge neutral">{sentiment.neutral} neutral</span>
                  <span className="badge neg">{sentiment.negative} negative</span>
                </div>
              </div>
              {(sentiment.recent || []).map((a) => (
                <div key={a._id} style={{ padding: '8px 0',
                                          borderTop: '1px solid rgba(37,51,86,0.5)' }}>
                  <div className="row" style={{ justifyContent: 'space-between',
                                                gap: 10, alignItems: 'flex-start' }}>
                    <span style={{ flex: 1 }}>
                      {a.url ? <a href={a.url} target="_blank" rel="noreferrer">
                                 {a.headline}
                               </a> : a.headline}
                    </span>
                    <SentimentBadge label={a.sentiment?.label}
                                    score={a.sentiment?.score} />
                  </div>
                  <div className="muted" style={{ fontSize: 11 }}>
                    {a.publisher || 'Unknown'} · {fmt.date(a.published_at)}
                  </div>
                </div>
              ))}
            </>
          )}
        </Card>
      </div>

      {profile && (
        <Card title="Company profile"
              sub="Variable-schema document from the MongoDB company_profiles collection">
          <div className="row" style={{ gap: 6, marginBottom: 12 }}>
            {(profile.tags || []).map((t) => (
              <span className="badge" key={t}>{t}</span>
            ))}
          </div>
          <pre className="sql">{JSON.stringify(profile, null, 2)}</pre>
        </Card>
      )}
    </>
  )
}
