// Thin fetch wrapper: attaches the bearer token, unwraps JSON and turns
// non-2xx responses into Errors carrying the API's own message.

const TOKEN_KEY = 'quantscore.token'
const USER_KEY = 'quantscore.user'

export const auth = {
  get token() {
    return localStorage.getItem(TOKEN_KEY)
  },
  get user() {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
    } catch {
      return null
    }
  },
  save(token, user) {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  },
}

async function request(path, { method = 'GET', body, params } = {}) {
  let url = `/api${path}`
  if (params) {
    const search = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') search.append(k, v)
    })
    const qs = search.toString()
    if (qs) url += `?${qs}`
  }

  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`

  const res = await fetch(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (res.status === 204) return null

  const text = await res.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = { detail: text }
  }

  if (!res.ok) {
    if (res.status === 401) auth.clear()
    const detail = data?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
          : `Request failed (${res.status})`
    const err = new Error(message)
    err.status = res.status
    throw err
  }
  return data
}

export const api = {
  get: (path, params) => request(path, { params }),
  post: (path, body, params) => request(path, { method: 'POST', body, params }),
  put: (path, body) => request(path, { method: 'PUT', body }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
  del: (path) => request(path, { method: 'DELETE' }),
}

// ---- formatting helpers shared by every page ------------------------
export const fmt = {
  money(v, digits = 2) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—'
    return v.toLocaleString(undefined, {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })
  },
  compact(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—'
    const abs = Math.abs(v)
    if (abs >= 1e12) return `$${(v / 1e12).toFixed(2)}T`
    if (abs >= 1e9) return `$${(v / 1e9).toFixed(2)}B`
    if (abs >= 1e6) return `$${(v / 1e6).toFixed(2)}M`
    if (abs >= 1e3) return `$${(v / 1e3).toFixed(1)}K`
    return `$${v.toFixed(2)}`
  },
  pct(v, digits = 2) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—'
    return `${(v * 100).toFixed(digits)}%`
  },
  num(v, digits = 2) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—'
    return Number(v).toFixed(digits)
  },
  date(v) {
    if (!v) return '—'
    const d = new Date(v)
    return Number.isNaN(d.getTime()) ? String(v).slice(0, 10) : d.toLocaleDateString()
  },
  dateTime(v) {
    if (!v) return '—'
    const d = new Date(v)
    return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString()
  },
}
