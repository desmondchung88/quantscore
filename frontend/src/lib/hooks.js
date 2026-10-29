import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'

/** GET a path and track loading/error. `deps` controls refetching. */
export function useApi(path, params, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(Boolean(path))
  const [nonce, setNonce] = useState(0)

  const reload = useCallback(() => setNonce((n) => n + 1), [])

  useEffect(() => {
    if (!path) { setLoading(false); return }
    let cancelled = false
    setLoading(true)
    setError(null)
    api.get(path, params)
      .then((d) => { if (!cancelled) setData(d) })
      .catch((e) => { if (!cancelled) setError(e) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, JSON.stringify(params), nonce, ...deps])

  return { data, error, loading, reload, setData }
}

/** Delay a fast-changing value (search boxes, sliders). */
export function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

/** Run a mutation with pending/error/success state. */
export function useAction() {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const alive = useRef(true)

  useEffect(() => () => { alive.current = false }, [])

  const run = useCallback(async (fn, successMessage) => {
    setPending(true); setError(null); setMessage(null)
    try {
      const result = await fn()
      if (alive.current && successMessage) setMessage(successMessage)
      return result
    } catch (e) {
      if (alive.current) setError(e)
      throw e
    } finally {
      if (alive.current) setPending(false)
    }
  }, [])

  return { run, pending, error, message, setError, setMessage }
}
