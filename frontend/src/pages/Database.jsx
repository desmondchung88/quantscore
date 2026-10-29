import { useState } from 'react'
import { Card, Empty, ErrorBox, Loading } from '../components/ui'
import { useApi } from '../lib/hooks'

export default function Database() {
  const [tab, setTab] = useState('tables')
  const schema = useApi('/meta/schema')

  if (schema.loading) return <Loading what="the database catalogue" />
  if (schema.error) return <ErrorBox error={schema.error} />
  if (!schema.data) return <Empty />

  const rel = schema.data.relational
  const collections = schema.data.documents.collections || []
  const byTable = {}
  rel.columns.forEach((c) => {
    (byTable[c.table_name] ||= []).push(c)
  })

  const TABS = {
    tables: 'Tables & columns',
    keys: 'Keys & constraints',
    indexes: 'Indexes',
    programs: 'Views, triggers & procedures',
    documents: 'MongoDB collections',
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Database design</h1>
          <p>
            Read live from <code>information_schema</code> and from MongoDB's
            own index metadata — this page reflects the database as it actually
            is, not a diagram that drifted out of date.
          </p>
        </div>
      </div>

      <div className="tabs">
        {Object.entries(TABS).map(([k, label]) => (
          <div key={k} className={`tab ${tab === k ? 'active' : ''}`}
               onClick={() => setTab(k)}>
            {label}
          </div>
        ))}
      </div>

      {tab === 'tables' && (
        <div className="grid cols-2">
          {rel.tables.filter((t) => t.type === 'BASE TABLE').map((t) => (
            <Card key={t.name} title={t.name}
                  sub={`${(byTable[t.name] || []).length} columns · approx ${(t.approx_rows || 0).toLocaleString()} rows`}>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Column</th><th>Type</th><th>Null</th><th>Key</th></tr>
                  </thead>
                  <tbody>
                    {(byTable[t.name] || []).map((c) => (
                      <tr key={c.column_name}>
                        <td className="mono">{c.column_name}</td>
                        <td className="muted mono" style={{ fontSize: 11 }}>
                          {c.data_type}
                        </td>
                        <td className="muted">{c.nullable}</td>
                        <td>
                          {c.key_type && (
                            <span className="badge">{c.key_type}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ))}
        </div>
      )}

      {tab === 'keys' && (
        <Card title="Foreign keys"
              sub="Referential integrity enforced by the database, not the application">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Constraint</th><th>Child table</th><th>Child column</th>
                  <th>References</th><th>Parent column</th>
                </tr>
              </thead>
              <tbody>
                {rel.foreign_keys.map((fk, i) => (
                  <tr key={i}>
                    <td className="mono" style={{ fontSize: 11 }}>{fk.name}</td>
                    <td>{fk.child}</td>
                    <td className="mono muted">{fk.child_column}</td>
                    <td>{fk.parent}</td>
                    <td className="mono muted">{fk.parent_column}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {tab === 'indexes' && (
        <Card title="Indexes"
              sub="Composite keys on the time-series carry most of the read load">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Table</th><th>Index</th><th>Columns</th>
                  <th>Type</th><th>Unique</th>
                </tr>
              </thead>
              <tbody>
                {rel.indexes.map((ix, i) => (
                  <tr key={i}>
                    <td>{ix.table_name}</td>
                    <td className="mono" style={{ fontSize: 11 }}>{ix.index_name}</td>
                    <td className="mono muted" style={{ fontSize: 11 }}>
                      {ix.columns}
                    </td>
                    <td className="muted">{ix.index_type}</td>
                    <td>{Number(ix.is_unique) ? <span className="badge">unique</span> : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {tab === 'programs' && (
        <div className="grid cols-2">
          <Card title="Views" sub="Layered so each one has a single responsibility">
            <table>
              <tbody>
                {rel.tables.filter((t) => t.type === 'VIEW').map((v) => (
                  <tr key={v.name}><td className="mono">{v.name}</td></tr>
                ))}
              </tbody>
            </table>
          </Card>

          <Card title="Stored procedures">
            <table>
              <tbody>
                {rel.routines.map((r) => (
                  <tr key={r.name}>
                    <td className="mono">{r.name}</td>
                    <td className="muted" style={{ fontSize: 12 }}>{r.comment}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          <Card title="Triggers"
                sub="Invariants that span rows, so they cannot be CHECK constraints">
            <table>
              <thead>
                <tr><th>Trigger</th><th>Timing</th><th>Event</th><th>Table</th></tr>
              </thead>
              <tbody>
                {rel.triggers.map((t) => (
                  <tr key={t.name}>
                    <td className="mono" style={{ fontSize: 11 }}>{t.name}</td>
                    <td>{t.timing}</td>
                    <td>{t.event}</td>
                    <td className="muted">{t.on_table}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          <Card title="Rules enforced in the database">
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.8 }}>
              <li>A SELL can never exceed the shares held (no short selling).</li>
              <li>A BUY can never exceed the cash balance (no margin).</li>
              <li>Cash is adjusted by trigger on every ledger insert.</li>
              <li>Quantities and prices must be positive (CHECK constraints).</li>
              <li>52-week high must not be below 52-week low.</li>
              <li>Deleting a user cascades to portfolios, trades and watchlists.</li>
              <li>A stock with trade history cannot be deleted (ON DELETE RESTRICT).</li>
            </ul>
          </Card>
        </div>
      )}

      {tab === 'documents' && (
        <div className="grid cols-2">
          {collections.map((c) => (
            <Card key={c.name} title={c.name}
                  sub={`${(c.documents || 0).toLocaleString()} documents`}>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Index</th><th>Keys</th><th>Properties</th></tr>
                  </thead>
                  <tbody>
                    {(c.indexes || []).map((ix) => (
                      <tr key={ix.name}>
                        <td className="mono" style={{ fontSize: 11 }}>{ix.name}</td>
                        <td className="mono muted" style={{ fontSize: 11 }}>
                          {(ix.keys || []).map(([k, v]) => `${k}:${v}`).join(', ')}
                        </td>
                        <td>
                          {ix.unique && <span className="badge">unique</span>}{' '}
                          {ix.ttl_seconds && (
                            <span className="badge">
                              TTL {Math.round(ix.ttl_seconds / 86400)}d
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ))}
          <Card title="Why these live in MongoDB">
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.8 }}>
              <li>
                <strong>news_articles</strong> — millions of documents with a
                nested sentiment sub-document and optional fields per source.
                A document validator keeps the required shape without a rigid
                schema.
              </li>
              <li>
                <strong>company_profiles</strong> — a bank carries Basel fields,
                a REIT carries occupancy, a biotech carries trial phases.
                Modelling that relationally means sparse columns or a dozen
                side tables.
              </li>
              <li>
                <strong>research_notes</strong> — free-form user content with
                arbitrary extra keys.
              </li>
              <li>
                <strong>activity_logs</strong> — append-only and self-expiring
                through a TTL index.
              </li>
            </ul>
          </Card>
        </div>
      )}
    </>
  )
}
