import { useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  Card, Empty, ErrorBox, Loading, SentimentBadge, Ticker,
} from '../components/ui'
import { api, fmt } from '../lib/api'
import { useApi, useDebounced } from '../lib/hooks'

const AXIS = { stroke: '#94a3c4', fontSize: 11 }
const TOOLTIP = {
  contentStyle: {
    background: '#16203a', border: '1px solid #253356',
    borderRadius: 8, fontSize: 12,
  },
}

export default function Sentiment() {
  const [ticker, setTicker] = useState('')
  const [label, setLabel] = useState('')
  const [search, setSearch] = useState('')
  const [granularity, setGranularity] = useState('month')
  const [live, setLive] = useState('Nvidia shares surge after earnings beat estimates')
  const [scored, setScored] = useState(null)

  const dTicker = useDebounced(ticker.toUpperCase(), 350)
  const dSearch = useDebounced(search, 400)

  const feed = useApi('/news/feed', {
    ticker: dTicker || undefined,
    label: label || undefined,
    search: dSearch || undefined,
    limit: 40,
  })
  const timeline = useApi('/news/timeline', {
    ticker: dTicker || undefined, days: 2200, granularity,
  })
  const board = useApi('/news/leaderboard', { days: 2200, min_articles: 50, limit: 12 })
  const publishers = useApi('/news/publishers', { days: 2200, limit: 10 })
  const dist = useApi('/news/distribution', { ticker: dTicker || undefined })

  async function scoreLive() {
    setScored(await api.post('/news/score', { text: live }))
  }

  const buckets = (dist.data?.buckets || []).map((b) => ({
    band: b.lower_bound === 'other' ? 'other' : String(b.lower_bound),
    count: b.count,
    bound: Number(b.lower_bound),
  }))

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Market sentiment</h1>
          <p>
            Every headline is scored at load time by a finance lexicon and
            stored with its matched terms. The feed, the time-series and the
            leaderboards are all MongoDB aggregation pipelines.
          </p>
        </div>
      </div>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="card">
          <label>Ticker</label>
          <input placeholder="All tickers" value={ticker}
                 onChange={(e) => setTicker(e.target.value)} />
        </div>
        <div className="card">
          <label>Sentiment</label>
          <select value={label} onChange={(e) => setLabel(e.target.value)}>
            <option value="">All</option>
            <option value="positive">Positive</option>
            <option value="neutral">Neutral</option>
            <option value="negative">Negative</option>
          </select>
        </div>
        <div className="card">
          <label>Full-text search</label>
          <input placeholder="e.g. earnings, lawsuit" value={search}
                 onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="card">
          <label>Timeline granularity</label>
          <select value={granularity} onChange={(e) => setGranularity(e.target.value)}>
            <option value="day">Daily</option>
            <option value="week">Weekly</option>
            <option value="month">Monthly</option>
          </select>
        </div>
      </div>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <Card title={`Sentiment over time${dTicker ? ` — ${dTicker}` : ''}`}
              sub="$dateTrunc + $group aggregation">
          {timeline.loading ? <Loading /> : !timeline.data?.timeline?.length ? (
            <Empty>No headlines in this window.</Empty>
          ) : (
            <ResponsiveContainer width="100%" height={250}>
              <ComposedChart data={timeline.data.timeline}>
                <CartesianGrid stroke="#253356" vertical={false} />
                <XAxis dataKey="period" {...AXIS} minTickGap={30} />
                <YAxis yAxisId="left" {...AXIS} width={52} />
                <YAxis yAxisId="right" orientation="right" {...AXIS} width={46}
                       domain={[-1, 1]} />
                <Tooltip {...TOOLTIP} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar yAxisId="left" dataKey="articles" fill="#253f78"
                     name="Articles" radius={[3, 3, 0, 0]} />
                <Line yAxisId="right" type="monotone" dataKey="avg_sentiment"
                      stroke="#4f8cff" strokeWidth={2} dot={false}
                      name="Avg sentiment" />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Score distribution"
              sub="$bucket over the raw sentiment scores">
          {dist.loading ? <Loading /> : !buckets.length ? <Empty /> : (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={buckets}>
                <CartesianGrid stroke="#253356" vertical={false} />
                <XAxis dataKey="band" {...AXIS} />
                <YAxis {...AXIS} width={56} />
                <Tooltip {...TOOLTIP} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {buckets.map((b, i) => (
                    <Cell key={i} fill={b.bound >= 0.15 ? '#2fbf71'
                      : b.bound <= -0.15 ? '#f0584f' : '#8da2c9'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      <div className="grid cols-3" style={{ marginBottom: 16 }}>
        <Card title="Most positively covered"
              sub="$facet, one pass over the matched set">
          {board.loading ? <Loading /> : (
            <table>
              <tbody>
                {(board.data?.most_positive || []).map((r) => (
                  <tr key={r.ticker}>
                    <td><Ticker symbol={r.ticker} /></td>
                    <td className="num muted">{r.articles}</td>
                    <td className="num pos">+{fmt.num(r.avg_sentiment, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Most negatively covered">
          {board.loading ? <Loading /> : (
            <table>
              <tbody>
                {(board.data?.most_negative || []).map((r) => (
                  <tr key={r.ticker}>
                    <td><Ticker symbol={r.ticker} /></td>
                    <td className="num muted">{r.articles}</td>
                    <td className="num neg">{fmt.num(r.avg_sentiment, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Publishers" sub="Coverage volume and tone">
          {publishers.loading ? <Loading /> : (
            <table>
              <tbody>
                {(publishers.data?.publishers || []).map((p) => (
                  <tr key={p.publisher}>
                    <td style={{ maxWidth: 130, overflow: 'hidden',
                                 textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.publisher}
                    </td>
                    <td className="num muted">{p.articles.toLocaleString()}</td>
                    <td className={`num ${p.avg_sentiment > 0 ? 'pos' : 'neg'}`}>
                      {p.avg_sentiment > 0 ? '+' : ''}{fmt.num(p.avg_sentiment, 3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <Card title="Score a headline yourself"
            sub="The same lexicon that scored every document at load time">
        <div className="row" style={{ flexWrap: 'nowrap' }}>
          <input value={live} onChange={(e) => setLive(e.target.value)}
                 placeholder="Type a headline…" />
          <button onClick={scoreLive}>Score</button>
        </div>
        {scored && (
          <div className="row" style={{ marginTop: 12, gap: 12 }}>
            <SentimentBadge label={scored.label} score={scored.score} />
            <span className="muted" style={{ fontSize: 12 }}>
              matched: {scored.matched_terms.length
                ? scored.matched_terms.join(', ')
                : 'no lexicon terms found'}
            </span>
          </div>
        )}
      </Card>

      <div style={{ height: 16 }} />

      <Card title="Headline feed"
            sub={feed.data
              ? `${feed.data.capped ? '10,000+' : feed.data.total.toLocaleString()} matching documents`
              : null}>
        <ErrorBox error={feed.error} />
        {feed.loading ? <Loading what="headlines" />
          : !feed.data?.articles?.length ? <Empty>No headlines match.</Empty>
          : feed.data.articles.map((a) => (
            <div key={a._id} style={{ padding: '10px 0',
                                      borderBottom: '1px solid rgba(37,51,86,0.5)' }}>
              <div className="row" style={{ justifyContent: 'space-between',
                                            gap: 12, alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                  <div>
                    {a.url
                      ? <a href={a.url} target="_blank" rel="noreferrer">{a.headline}</a>
                      : a.headline}
                  </div>
                  <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                    <Ticker symbol={a.ticker} /> · {a.publisher || 'Unknown publisher'}
                    {' · '}{fmt.dateTime(a.published_at)}
                    {a.sentiment?.terms?.length
                      ? ` · matched: ${a.sentiment.terms.join(', ')}` : ''}
                  </div>
                </div>
                <SentimentBadge label={a.sentiment?.label} score={a.sentiment?.score} />
              </div>
            </div>
          ))}
      </Card>
    </>
  )
}
