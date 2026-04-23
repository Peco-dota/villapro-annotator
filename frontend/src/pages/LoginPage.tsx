import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { setToken, setUser } from '../lib/auth'
import { login } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Spinner } from '../components/ui/Spinner'

export function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await login(username.trim(), password)
      setToken(data.access_token)
      setUser({ username: data.username, role: data.role })
      navigate('/')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(msg ?? 'Server unreachable. Make sure the VisionQ server is running.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0f0d14] flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-violet-600/20 border border-violet-500/30 mb-4">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="1.5">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-slate-100">VisionQ</h1>
          <p className="text-sm text-slate-500 mt-1">YOLO annotation & detection server</p>
        </div>

        <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 shadow-2xl">
          <form onSubmit={submit} className="flex flex-col gap-4">
            <Input
              label="Username"
              type="text"
              placeholder="admin"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoFocus
            />
            <Input
              label="Password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
            />
            {error && <p className="text-xs text-red-400 -mt-1">{error}</p>}
            <Button
              type="submit"
              variant="primary"
              size="lg"
              disabled={loading || !username.trim() || !password}
            >
              {loading ? <Spinner size={14} /> : null}
              Sign in
            </Button>
          </form>

          <p className="text-xs text-slate-600 text-center mt-4">
            Default credentials: admin / admin123 · customer / customer123
          </p>
        </div>
      </div>
    </div>
  )
}
