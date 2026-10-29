import { useState } from 'react'
import { Card, ErrorBox } from '../components/ui'
import { api } from '../lib/api'
import { useAction } from '../lib/hooks'

export default function Login({ onLogin }) {
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ username: '', email: '', password: '' })
  const action = useAction()

  async function submit(e) {
    e.preventDefault()
    const body = mode === 'login'
      ? { username: form.username, password: form.password }
      : form
    await action
      .run(() => api.post(`/auth/${mode}`, body))
      .then((d) => onLogin(d.access_token, d.user))
      .catch(() => {})
  }

  function useDemo() {
    setMode('login')
    setForm({ username: 'demo', email: '', password: 'demo1234' })
  }

  return (
    <div style={{ maxWidth: 420, margin: '8vh auto' }}>
      <Card title={mode === 'login' ? 'Sign in' : 'Create an account'}
            sub="Passwords are stored as bcrypt hashes; sessions are JWTs.">
        <form onSubmit={submit}>
          <div className="field">
            <label>{mode === 'login' ? 'Username or email' : 'Username'}</label>
            <input required autoFocus value={form.username}
                   onChange={(e) => setForm({ ...form, username: e.target.value })} />
          </div>

          {mode === 'register' && (
            <div className="field">
              <label>Email</label>
              <input required type="email" value={form.email}
                     onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </div>
          )}

          <div className="field">
            <label>Password{mode === 'register' && ' (at least 8 characters)'}</label>
            <input required type="password" value={form.password}
                   onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </div>

          <ErrorBox error={action.error} />

          <button type="submit" style={{ width: '100%' }} disabled={action.pending}>
            {action.pending ? 'Please wait…'
              : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        <div className="row" style={{ marginTop: 14, justifyContent: 'space-between' }}>
          <button className="ghost sm"
                  onClick={() => setMode(mode === 'login' ? 'register' : 'login')}>
            {mode === 'login' ? 'Need an account?' : 'Already registered?'}
          </button>
          <button className="ghost sm" onClick={useDemo}>Use the demo account</button>
        </div>
      </Card>
    </div>
  )
}
