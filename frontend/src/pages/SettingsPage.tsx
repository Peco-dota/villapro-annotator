import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getSystemInfo, getSettings, patchSettings, changePassword,
  getTokens, createToken, revokeToken, getServices,
} from '../lib/api'
import { clearToken, getUser } from '../lib/auth'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Spinner } from '../components/ui/Spinner'
import type { Token } from '../lib/types'

const ALL_PERMISSIONS = ['stream', 'results', 'control'] as const
type Permission = typeof ALL_PERMISSIONS[number]

const PERMISSION_LABELS: Record<Permission, string> = {
  stream: 'Stream (SSE / MJPEG preview)',
  results: 'Results (status, last payload, log)',
  control: 'Control (start / stop / restart)',
}

// ── Section wrapper ───────────────────────────────────────────────────────────

function Section({ title, icon, children }: { title: string; icon: string; children: React.ReactNode }) {
  return (
    <div className="bg-[#16213e] border border-[#1e293b] rounded-xl overflow-hidden">
      <div className="flex items-center gap-3 px-5 py-4 border-b border-[#1e293b]">
        <span className="text-base">{icon}</span>
        <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
      </div>
      <div className="p-5">{children}</div>
    </div>
  )
}

// ── Change password ───────────────────────────────────────────────────────────

function ChangePasswordSection() {
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [err, setErr] = useState('')
  const [ok, setOk] = useState(false)

  const mut = useMutation({
    mutationFn: () => changePassword(form.current, form.next),
    onSuccess: () => {
      setOk(true)
      setErr('')
      setForm({ current: '', next: '', confirm: '' })
      setTimeout(() => setOk(false), 3000)
    },
    onError: (e: unknown) => {
      setErr((e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Failed to change password.')
    },
  })

  const canSubmit = form.current && form.next.length >= 6 && form.next === form.confirm

  return (
    <Section title="Change Password" icon="🔑">
      <div className="flex flex-col gap-3">
        <Input
          label="Current password"
          type="password"
          value={form.current}
          onChange={e => setForm(f => ({ ...f, current: e.target.value }))}
          autoComplete="current-password"
        />
        <Input
          label="New password"
          type="password"
          value={form.next}
          onChange={e => setForm(f => ({ ...f, next: e.target.value }))}
          autoComplete="new-password"
        />
        <Input
          label="Confirm new password"
          type="password"
          value={form.confirm}
          onChange={e => setForm(f => ({ ...f, confirm: e.target.value }))}
          autoComplete="new-password"
          onKeyDown={e => { if (e.key === 'Enter' && canSubmit) mut.mutate() }}
        />
        {form.next && form.confirm && form.next !== form.confirm && (
          <p className="text-xs text-red-400">Passwords don't match</p>
        )}
        {form.next && form.next.length < 6 && (
          <p className="text-xs text-slate-500">At least 6 characters required</p>
        )}
        {err && <p className="text-xs text-red-400">{err}</p>}
        {ok && <p className="text-xs text-green-400">Password changed successfully.</p>}
        <div className="pt-1">
          <Button variant="primary" onClick={() => mut.mutate()} disabled={mut.isPending || !canSubmit}>
            {mut.isPending ? <Spinner size={12} /> : null}
            Change Password
          </Button>
        </div>
      </div>
    </Section>
  )
}

// ── Server settings ───────────────────────────────────────────────────────────

function ServerSettingsSection() {
  const { data: settings, isLoading } = useQuery({ queryKey: ['settings'], queryFn: getSettings })
  const qc = useQueryClient()
  const [form, setForm] = useState<Record<string, unknown>>({})
  const [saved, setSaved] = useState(false)

  const mut = useMutation({
    mutationFn: () => patchSettings(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    },
  })

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: e.target.type === 'number' ? +e.target.value : e.target.value }))

  if (isLoading) return <Section title="Server Settings" icon="⚙"><Spinner /></Section>

  return (
    <Section title="Server Settings" icon="⚙">
      <div className="flex flex-col gap-3">
        <Input label="Host" defaultValue={settings?.host} onChange={set('host')} />
        <Input label="Port" type="number" defaultValue={settings?.port} onChange={set('port')} />
        <Input label="SSL cert file" defaultValue={settings?.ssl_certfile ?? ''} onChange={set('ssl_certfile')} placeholder="(optional)" />
        <Input label="SSL key file" defaultValue={settings?.ssl_keyfile ?? ''} onChange={set('ssl_keyfile')} placeholder="(optional)" />
        <div className="flex items-center gap-3 pt-1">
          <Button
            variant="primary"
            onClick={() => mut.mutate()}
            disabled={mut.isPending || Object.keys(form).length === 0}
          >
            {mut.isPending ? <Spinner size={12} /> : null}
            Save Settings
          </Button>
          {saved && <span className="text-xs text-green-400">Saved!</span>}
        </div>
      </div>
    </Section>
  )
}

// ── API tokens ────────────────────────────────────────────────────────────────

function ApiTokensSection() {
  const qc = useQueryClient()
  const [label, setLabel] = useState('')
  const [selectedServices, setSelectedServices] = useState<string[]>([])
  const [selectedPerms, setSelectedPerms] = useState<Permission[]>(['stream', 'results'])
  const [newToken, setNewToken] = useState<string | null>(null)

  const { data: tokens = [], isLoading } = useQuery<Token[]>({
    queryKey: ['tokens'],
    queryFn: getTokens,
  })

  const { data: services = [] } = useQuery({
    queryKey: ['services'],
    queryFn: getServices,
  })
  const serviceNames: string[] = (services as Array<{ name: string }>).map(s => s.name)

  const createMut = useMutation({
    mutationFn: () => createToken(label, selectedServices, selectedPerms),
    onSuccess: (data) => {
      setNewToken(data.token)
      setLabel('')
      setSelectedServices([])
      setSelectedPerms(['stream', 'results'])
      qc.invalidateQueries({ queryKey: ['tokens'] })
    },
  })

  const revokeMut = useMutation({
    mutationFn: (t: string) => revokeToken(t),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tokens'] }),
  })

  const toggleService = (name: string) =>
    setSelectedServices(prev => prev.includes(name) ? prev.filter(s => s !== name) : [...prev, name])

  const togglePerm = (p: Permission) =>
    setSelectedPerms(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p])

  return (
    <Section title="API Tokens" icon="🔐">
      {newToken && (
        <div className="mb-4 px-4 py-3 bg-green-900/20 border border-green-700/50 rounded-lg">
          <p className="text-xs text-green-400 mb-1.5 font-medium">Token created — copy it now, it won't be shown again:</p>
          <code className="text-xs text-green-200 break-all font-mono">{newToken}</code>
          <button onClick={() => setNewToken(null)} className="block text-xs text-slate-500 mt-2 cursor-pointer hover:text-slate-300">Dismiss</button>
        </div>
      )}

      {/* Create form */}
      <div className="flex flex-col gap-3 mb-5 max-w-sm">
        <Input
          placeholder="Token label (e.g. gate-controller)"
          value={label}
          onChange={e => setLabel(e.target.value)}
        />

        {/* Permissions */}
        <div>
          <p className="text-xs text-slate-500 mb-1.5">Permissions</p>
          <div className="flex flex-col gap-1">
            {ALL_PERMISSIONS.map(p => (
              <label key={p} className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={selectedPerms.includes(p)}
                  onChange={() => togglePerm(p)}
                  className="accent-violet-500"
                />
                <span className="text-xs text-slate-300">{PERMISSION_LABELS[p]}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Service scope */}
        {serviceNames.length > 0 && (
          <div>
            <p className="text-xs text-slate-500 mb-1.5">
              Allowed services <span className="text-slate-600">(leave all unchecked = access all)</span>
            </p>
            <div className="flex flex-col gap-1 max-h-32 overflow-y-auto">
              {serviceNames.map(name => (
                <label key={name} className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={selectedServices.includes(name)}
                    onChange={() => toggleService(name)}
                    className="accent-violet-500"
                  />
                  <span className="text-xs text-slate-300 font-mono">{name}</span>
                </label>
              ))}
            </div>
          </div>
        )}

        <Button variant="primary" className="self-start" onClick={() => createMut.mutate()} disabled={createMut.isPending || !label.trim()}>
          {createMut.isPending ? <Spinner size={12} /> : null}
          Create Token
        </Button>
      </div>

      {/* Token list */}
      {isLoading ? <Spinner /> : tokens.length === 0 ? (
        <p className="text-xs text-slate-600">No tokens yet</p>
      ) : (
        <div className="flex flex-col gap-2">
          {tokens.map(t => (
            <div key={t.token} className="flex items-start justify-between gap-3 px-4 py-3 bg-[#0f172a] border border-[#1e293b] rounded-lg">
              <div className="min-w-0">
                <p className="text-sm text-slate-200">{t.label}</p>
                <p className="text-xs text-slate-600 mt-0.5">{new Date(t.created_at).toLocaleString()}</p>
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {(t.permissions ?? []).map(p => (
                    <span key={p} className="px-1.5 py-0.5 rounded text-[10px] bg-violet-900/40 text-violet-300 border border-violet-700/40">{p}</span>
                  ))}
                  {(t.services ?? []).length > 0
                    ? (t.services ?? []).map(s => (
                        <span key={s} className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 border border-slate-700">{s}</span>
                      ))
                    : <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-500 border border-slate-700">all services</span>
                  }
                </div>
              </div>
              <Button
                variant="danger"
                size="sm"
                onClick={() => { if (confirm('Revoke this token?')) revokeMut.mutate(t.token) }}
              >Revoke</Button>
            </div>
          ))}
        </div>
      )}
    </Section>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function SettingsPage() {
  const nav = useNavigate()
  const user = getUser()
  const { data: info } = useQuery({ queryKey: ['sysinfo'], queryFn: getSystemInfo })
  const logout = () => { clearToken(); nav('/login') }

  return (
    <div className="min-h-screen bg-[#0f172a] flex flex-col">
      {/* Top bar — matches WelcomePage */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-[#1e293b] shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-violet-600/20 border border-violet-500/30 flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="1.5">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          </div>
          <span className="text-base font-semibold text-slate-100">VisionQ</span>
          {info && <span className="text-xs text-slate-600">v{info.version}</span>}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">{user?.username}</span>
          <Button variant="ghost" size="sm" onClick={() => nav('/')}>← Back</Button>
          <Button variant="ghost" size="sm" onClick={logout}>Sign out</Button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Left nav */}
        <aside className="w-56 border-r border-[#1e293b] p-4 shrink-0">
          <p className="text-[10px] font-bold text-slate-600 uppercase tracking-widest px-1 mb-3">Settings</p>
          <nav className="flex flex-col gap-1">
            {[
              { label: 'Account', icon: '👤' },
              { label: 'Server', icon: '⚙' },
              { label: 'API Tokens', icon: '🔐' },
            ].map(item => (
              <a
                key={item.label}
                href={`#${item.label.toLowerCase().replace(' ', '-')}`}
                className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200 hover:bg-[#1e293b] transition-colors"
              >
                <span>{item.icon}</span>
                {item.label}
              </a>
            ))}
          </nav>

          {info && (
            <div className="mt-auto pt-4 border-t border-[#1e293b] mt-8">
              <p className="text-[10px] text-slate-600 px-1">VisionQ v{info.version}</p>
              <p className="text-[10px] text-slate-700 px-1">{info.platform}</p>
            </div>
          )}
        </aside>

        {/* Content */}
        <main className="flex-1 overflow-y-auto p-8">
          <div className="max-w-2xl mx-auto flex flex-col gap-6">
            <div id="account"><ChangePasswordSection /></div>
            <div id="server"><ServerSettingsSection /></div>
            <div id="api-tokens"><ApiTokensSection /></div>
          </div>
        </main>
      </div>
    </div>
  )
}
