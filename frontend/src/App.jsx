import { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { api, auth } from './lib/api'

import Dashboard from './pages/Dashboard'
import StockSearch from './pages/StockSearch'
import StockDetail from './pages/StockDetail'
import Scores from './pages/Scores'
import Screener from './pages/Screener'
import Portfolio from './pages/Portfolio'
import Sentiment from './pages/Sentiment'
import Notes from './pages/Notes'
import Watchlists from './pages/Watchlists'
import Benchmark from './pages/Benchmark'
import Database from './pages/Database'
import Login from './pages/Login'

const NAV = [
  { section: 'Research' },
  { to: '/', label: 'Dashboard', end: true },
  { to: '/search', label: 'Stock search' },
  { to: '/scores', label: 'QuantScore' },
  { to: '/screener', label: 'Screener' },
  { to: '/sentiment', label: 'Market sentiment' },
  { section: 'My account' },
  { to: '/portfolio', label: 'Portfolio', auth: true },
  { to: '/watchlists', label: 'Watchlists', auth: true },
  { to: '/notes', label: 'Research notes', auth: true },
  { section: 'Under the hood' },
  { to: '/benchmark', label: 'SQL vs NoSQL' },
  { to: '/database', label: 'Database design' },
]

export default function App() {
  const [user, setUser] = useState(auth.user)
  const [health, setHealth] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    api.get('/meta/health').then(setHealth).catch(() => setHealth({ status: 'down' }))
  }, [])

  // Re-validate a stored token on load; clear it if the API rejects it.
  useEffect(() => {
    if (!auth.token) return
    api.get('/auth/me')
      .then((d) => { auth.save(auth.token, d.user); setUser(d.user) })
      .catch(() => { auth.clear(); setUser(null) })
  }, [])

  function onLogin(token, u) {
    auth.save(token, u)
    setUser(u)
    navigate('/portfolio')
  }

  function logout() {
    auth.clear()
    setUser(null)
    navigate('/')
  }

  const requireAuth = (element) =>
    user ? element : <Navigate to="/login" replace />

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          Quant<span>Score</span>
          <small>S&amp;P 500 research platform</small>
        </div>

        {NAV.map((item, i) =>
          item.section ? (
            <div className="nav-section" key={`s${i}`}>{item.section}</div>
          ) : (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              {item.label}
            </NavLink>
          ),
        )}

        <div style={{ marginTop: 'auto', paddingTop: 20 }}>
          {user ? (
            <div className="card" style={{ padding: 12 }}>
              <div style={{ fontWeight: 600 }}>{user.username}</div>
              <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
                {user.email}
              </div>
              <button className="ghost sm" onClick={logout}>Sign out</button>
            </div>
          ) : (
            <NavLink to="/login" className="nav-link">Sign in</NavLink>
          )}

          {health && (
            <div className="muted" style={{ fontSize: 11, padding: '12px 12px 0' }}>
              <div>
                MySQL{' '}
                <span className={health.mysql?.connected ? 'pos' : 'neg'}>
                  {health.mysql?.connected ? 'connected' : 'down'}
                </span>
              </div>
              <div>
                MongoDB{' '}
                <span className={health.mongodb?.connected ? 'pos' : 'neg'}>
                  {health.mongodb?.connected ? 'connected' : 'down'}
                </span>
              </div>
            </div>
          )}
        </div>
      </aside>

      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/search" element={<StockSearch />} />
          <Route path="/stocks/:ticker" element={<StockDetail />} />
          <Route path="/scores" element={<Scores />} />
          <Route path="/screener" element={<Screener />} />
          <Route path="/sentiment" element={<Sentiment />} />
          <Route path="/benchmark" element={<Benchmark />} />
          <Route path="/database" element={<Database />} />
          <Route path="/login" element={<Login onLogin={onLogin} />} />
          <Route path="/portfolio" element={requireAuth(<Portfolio />)} />
          <Route path="/watchlists" element={requireAuth(<Watchlists />)} />
          <Route path="/notes" element={requireAuth(<Notes />)} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
