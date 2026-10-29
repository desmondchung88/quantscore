import { useState } from 'react'
import {
  Card, Delta, Empty, ErrorBox, Grade, Loading, ScoreBar, Ticker,
} from '../components/ui'
import { fmt } from '../lib/api'
import { useApi } from '../lib/hooks'

const PRESETS = {
  Balanced: { valuation: 0.30, profitability: 0.25, growth: 0.25, dividend: 0.20 },
  Value: { valuation: 0.55, profitability: 0.25, growth: 0.05, dividend: 0.15 },
  Growth: { valuation: 0.10, profitability: 0.25, growth: 0.60, dividend: 0.05 },
  Income: { valuation: 0.20, profitability: 0.20, growth: 0.05, dividend: 0.55 },
  Quality: { valuation: 0.20, profitability: 0.55, growth: 0.20, dividend: 0.05 },
}

export default function Scores() {
  const [w, setW] = useState(PRESETS.Balanced)
  const [sector, setSector] = useState('')
  const [minCap, setMinCap] = useState(0)
  const [expand, setExpand] = useState(null)

  const sectors = useApi('/stocks/sectors')
  const board = useApi('/scores/leaderboard', {
    ...w, sector: sector || undefined, min_market_cap: minCap, limit: 60,
  })
  const detail = useApi(expand ? `/scores/${expand}` : null, w)

  const total = Object.values(w).reduce((a, b) => a + b, 0)

  function setFactor(key, value) {
    setW((prev) => ({ ...prev, [key]: Number(value) }))
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>QuantScore</h1>
          <p>
            Four factors, each scored against the company's own sector average,
            then combined with weights you control. 50 means exactly average
            for the sector — nothing here is a black box.
          </p>
        </div>
      </div>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <Card title="Factor weights"
              sub={`Weights are normalised before scoring (currently summing to ${total.toFixed(2)})`}>
          <div className="row" style={{ marginBottom: 14 }}>
            {Object.keys(PRESETS).map((name) => (
              <button key={name} className="ghost sm"
                      onClick={() => setW(PRESETS[name])}>
                {name}
              </button>
            ))}
          </div>

          {Object.entries(w).map(([key, value]) => (
            <div className="field" key={key}>
              <label style={{ textTransform: 'capitalize' }}>
                {key} — {(value / total * 100).toFixed(0)}% of the score
              </label>
              <input type="range" min="0" max="1" step="0.05" value={value}
                     onChange={(e) => setFactor(key, e.target.value)} />
            </div>
          ))}
        </Card>

        <Card title="Universe filter">
          <div className="field">
            <label>Sector</label>
            <select value={sector} onChange={(e) => setSector(e.target.value)}>
              <option value="">All sectors</option>
              {(sectors.data?.sectors || []).map((s) => (
                <option key={s.sector_name} value={s.sector_name}>
                  {s.sector_name} ({s.company_count})
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Minimum market cap</label>
            <select value={minCap} onChange={(e) => setMinCap(Number(e.target.value))}>
              <option value={0}>No minimum</option>
              <option value={1e9}>$1B+</option>
              <option value={10e9}>$10B+</option>
              <option value={50e9}>$50B+</option>
              <option value={200e9}>$200B+ (mega cap)</option>
            </select>
          </div>
          <p className="muted" style={{ fontSize: 12 }}>
            The ranking runs as a single SQL statement over the
            <code> v_stock_scores_total </code> view, using
            <code> RANK() OVER </code> for both the overall and the
            within-sector position.
          </p>
          {board.data && (
            <div className="stat" style={{ marginTop: 10 }}>
              <span className="label">Companies in scope</span>
              <span className="value">{board.data.total}</span>
            </div>
          )}
        </Card>
      </div>

      <Card title="Ranking" sub="Click a row to see how the score was built">
        <ErrorBox error={board.error} />
        {board.loading ? <Loading what="rankings" />
          : !board.data?.results?.length ? <Empty />
          : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th><th>Ticker</th><th>Company</th><th>Sector</th>
                    <th className="num">Score</th><th>Grade</th>
                    <th style={{ minWidth: 110 }}>Valuation</th>
                    <th style={{ minWidth: 110 }}>Profit</th>
                    <th style={{ minWidth: 110 }}>Growth</th>
                    <th style={{ minWidth: 110 }}>Dividend</th>
                    <th className="num">1y</th>
                  </tr>
                </thead>
                <tbody>
                  {board.data.results.map((r) => (
                    <tr key={r.ticker}
                        onClick={() => setExpand(expand === r.ticker ? null : r.ticker)}
                        style={{ cursor: 'pointer' }}>
                      <td className="muted">{r.overall_rank}</td>
                      <td><Ticker symbol={r.ticker} /></td>
                      <td style={{ maxWidth: 180, overflow: 'hidden',
                                   textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.company_name}
                      </td>
                      <td className="muted" style={{ fontSize: 12 }}>{r.sector_name}</td>
                      <td className="num" style={{ fontWeight: 650 }}>
                        {fmt.num(r.weighted_score, 1)}
                      </td>
                      <td><Grade grade={r.grade} /></td>
                      <td><ScoreBar value={r.valuation_score} /></td>
                      <td><ScoreBar value={r.profitability_score} /></td>
                      <td><ScoreBar value={r.growth_score} /></td>
                      <td><ScoreBar value={r.dividend_score} /></td>
                      <td className="num"><Delta value={r.ret_1y} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </Card>

      {expand && (
        <>
          <div style={{ height: 16 }} />
          <Card title={`How ${expand} scores`}
                actions={<button className="ghost sm" onClick={() => setExpand(null)}>
                           Close
                         </button>}>
            {detail.loading ? <Loading /> : !detail.data ? <Empty /> : (
              <>
                <p className="muted" style={{ marginTop: 0 }}>
                  {detail.data.methodology}
                </p>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Factor</th><th className="num">Sub-score</th>
                        <th className="num">Weight</th>
                        <th className="num">Contribution</th>
                        <th>Inputs</th><th>Reading</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.data.factors.map((f) => (
                        <tr key={f.factor}>
                          <td style={{ textTransform: 'capitalize' }}>{f.factor}</td>
                          <td className="num">{fmt.num(f.score, 1)}</td>
                          <td className="num">{(f.weight * 100).toFixed(0)}%</td>
                          <td className="num" style={{ fontWeight: 650 }}>
                            {fmt.num(f.contribution, 2)}
                          </td>
                          <td className="mono muted" style={{ fontSize: 11 }}>
                            {Object.entries(f.inputs)
                              .map(([k, v]) => `${k}=${v === null || v === undefined
                                ? 'n/a' : Number(v).toFixed(3)}`)
                              .join('  ')}
                          </td>
                          <td className="muted" style={{ fontSize: 12 }}>
                            {f.interpretation}
                          </td>
                        </tr>
                      ))}
                      <tr>
                        <td colSpan={3} style={{ fontWeight: 650 }}>
                          Weighted total
                        </td>
                        <td className="num" style={{ fontWeight: 700 }}>
                          {fmt.num(detail.data.weighted_score, 2)}
                        </td>
                        <td colSpan={2}>
                          <Grade grade={detail.data.grade} />{' '}
                          <span className="muted" style={{ fontSize: 12 }}>
                            vs {detail.data.sector_peers} sector peers
                          </span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </Card>
        </>
      )}
    </>
  )
}
