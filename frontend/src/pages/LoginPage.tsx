import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { setToken } from '../lib/auth'
import { api } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Spinner } from '../components/ui/Spinner'

export function LoginPage() {
  const [token, setTokenState] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      setToken(token.trim())
      await api.get('/api/system/info')
      navigate('/')
    } catch {
      setToken('')
      setError('Invalid token or server unreachable.')
    } finally {
      setLoading(false)
    }
  }

  const tryBootstrap = async () => {
    setLoading(true)
    setError('')
    try {
      setToken('__bootstrap__')
      await api.get('/api/system/info')
      navigate('/')
    } catch {
      setToken('')
      setError('Server not reachable. Make sure the VisionQ server is running.')
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
              label="API Token"
              type="password"
              placeholder="Paste your bearer token..."
              value={token}
              onChange={e => setTokenState(e.target.value)}
              autoFocus
            />
            {error && <p className="text-xs text-red-400 -mt-1">{error}</p>}
            <Button type="submit" variant="primary" size="lg" disabled={loading || !token.trim()}>
              {loading ? <Spinner size={14} /> : null}
              Connect
            </Button>
          </form>

          <div className="mt-4 pt-4 border-t border-slate-700/60 text-center">
            <p className="text-xs text-slate-500 mb-2">First time? Server in bootstrap mode?</p>
            <button
              onClick={tryBootstrap}
              disabled={loading}
              className="text-xs text-violet-400 hover:text-violet-300 underline underline-offset-2 disabled:opacity-40"
            >
              Connect without token (bootstrap mode)
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
