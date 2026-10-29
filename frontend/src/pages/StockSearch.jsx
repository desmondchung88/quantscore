import { useState } from 'react'
import { Card, Delta, Empty, ErrorBox, Loading, Ticker } from '../components/ui'
import { fmt } from '../lib/api'
import { useApi, useDebounced } from '../lib/hooks'

export default function StockSearch() {
  const [term, setTerm] = useState('')
  const debounced = useDebounced(term, 250)
  const results = useApi(debounced.length >= 1 ? '/stocks/search' : null,
                         { q: debounced, limit: 40 })
  const sectors = useApi('/stocks/sectors')

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Stock search</h1>
          <p>
            Search by ticker or company name. Every ratio on the stock page is
            shown next to its sector average, so a number always arrives with
            its context.
          </p>
        </div>
      </div>

      <Card className="" title="Find a company">
        <input
          autoFocus
          placeholder="Try AAPL, Johnson, or energy names…"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
        />
        <ErrorBox error={results.error} />

        {debounced.length === 0 ? (
          <Empty>Start typing to search the S&amp;P 500.</Empty>
        ) : results.loading ? (
          <Loading what="matches" />
        ) : !results.data?.results?.length ? (
          <Empty>No company matches “{debounced}”.</Empty>
        ) : (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th>Ticker</th><th>Company</th><th>Sector</th>
                  <th className="num">Last</th>
                  <th className="num">Market cap</th>
                  <th className="num">P/E</th>
                  <th className="num">Yield</th>
                  <th className="num">1y</th>
                </tr>
              </thead>
              <tbody>
                {results.data.results.map((s) => (
                  <tr key={s.ticker}>
                    <td><Ticker symbol={s.ticker} /></td>
                    <td>{s.company_name}</td>
                    <td className="muted">{s.sector_name}</td>
                    <td className="num">{fmt.money(s.last_close)}</td>
                    <td className="num">{fmt.compact(s.market_cap)}</td>
                    <td className="num">{fmt.num(s.pe_ratio, 1)}</td>
                    <td className="num">
                      {s.dividend_yield ? `${fmt.num(s.dividend_yield, 2)}%` : '—'}
                    </td>
                    <td className="num"><Delta value={s.ret_1y} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div style={{ height: 16 }} />

      <Card title="Browse by sector"
            sub="Sector aggregates come from the v_sector_averages view">
        {sectors.loading ? <Loading /> : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Sector</th>
                  <th className="num">Companies</th>
                  <th className="num">Avg P/E</th>
                  <th className="num">Avg P/S</th>
                  <th className="num">Avg P/B</th>
                  <th className="num">Avg yield</th>
                  <th className="num">Avg 1y</th>
                  <th className="num">Total cap</th>
                </tr>
              </thead>
              <tbody>
                {(sectors.data?.sectors || []).map((s) => (
                  <tr key={s.sector_name}>
                    <td>{s.sector_name}</td>
                    <td className="num">{s.company_count}</td>
                    <td className="num">{fmt.num(s.avg_pe, 1)}</td>
                    <td className="num">{fmt.num(s.avg_ps, 2)}</td>
                    <td className="num">{fmt.num(s.avg_pb, 2)}</td>
                    <td className="num">{fmt.num(s.avg_div_yield, 2)}%</td>
                    <td className="num"><Delta value={s.avg_ret_1y} /></td>
                    <td className="num">{fmt.compact(s.total_market_cap)}</td>
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
