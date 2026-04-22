import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSystemInfo, getTokens, createToken, revokeToken, getSettings, patchSettings } from '../lib/api'
import { clearToken } from '../lib/auth'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Spinner } from '../components/ui/Spinner'
import type { Token } from '../lib/types'

function TokenSection() {
  const qc = useQueryClient()
  const [label, setLabel] = useState('')
  const [newToken, setNewToken] = useState<string | null>(null)

  const { data: tokens = [], isLoading } = useQuery<Token[]>({
    queryKey: ['tokens'],
    queryFn: getTokens,
  })

  const createMut = useMutation({
    mutationFn: () => createToken(label),
    onSuccess: (data) => { setNewToken(data.token); setLabel(''); qc.invalidateQueries({ queryKey: ['tokens'] }) },
  })

  const revokeMut = useMutation({
    mutationFn: (t: string) => revokeToken(t),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tokens'] }),
  })

  return (
    <section className="bg-slate-900 border border-slate-700 rounded-xl p-5">
      <h2 className="text-sm font-semibold text-slate-100 mb-4">API Tokens</h2>

      {newToken && (
        <div className="mb-4 p-3 bg-green-900/20 border border-green-700 rounded-lg">
          <p className="text-xs text-green-400 mb-1 font-medium">Token created — copy it now, it won't be shown again:</p>
          <code className="text-xs text-green-200 break-all">{newToken}</code>
          <button onClick={() => setNewToken(null)} className="block text-xs text-slate-500 mt-2 cursor-pointer hover:text-slate-300">Dismiss</button>
        </div>
      )}

      <div className="flex gap-2 mb-4">
        <Input
          className="flex-1"
          placeholder="Token label (e.g. frontend-prod)"
          value={label}
          onChange={e => setLabel(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && label.trim()) createMut.mutate() }}
        />
        <Button variant="primary" onClick={() => createMut.mutate()} disabled={createMut.isPending || !label.trim()}>
          {createMut.isPending ? <Spinner size={12} /> : null}
          Create
        </Button>
      </div>

      {isLoading ? <Spinner /> : (
        <div className="flex flex-col gap-2">
          {tokens.length === 0 && <p className="text-xs text-slate-600">No tokens yet</p>}
          {tokens.map((t) => (
            <div key={t.token} className="flex items-center justify-between gap-3 px-3 py-2 bg-slate-800 rounded-lg">
              <div>
                <p className="text-sm text-slate-200">{t.label}</p>
                <p className="text-xs text-slate-600">{new Date(t.created_at).toLocaleString()}</p>
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
    </section>
  )
}

function ServerSettings() {
  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
  })
  const qc = useQueryClient()
  const [form, setForm] = useState<Record<string, unknown>>({})
  const [saved, setSaved] = useState(false)

  const mut = useMutation({
    mutationFn: () => patchSettings(form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['settings'] }); setSaved(true); setTimeout(() => setSaved(false), 2000) },
  })

  if (isLoading) return <Spinner />

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: e.target.type === 'number' ? +e.target.value : e.target.value }))

  return (
    <section className="bg-slate-900 border border-slate-700 rounded-xl p-5">
      <h2 className="text-sm font-semibold text-slate-100 mb-4">Server Settings</h2>
      <div className="flex flex-col gap-3">
        <Input label="Host" defaultValue={settings?.host} onChange={set('host')} />
        <Input label="Port" type="number" defaultValue={settings?.port} onChange={set('port')} />
        <Input label="SSL cert file" defaultValue={settings?.ssl_certfile ?? ''} onChange={set('ssl_certfile')} placeholder="(optional)" />
        <Input label="SSL key file" defaultValue={settings?.ssl_keyfile ?? ''} onChange={set('ssl_keyfile')} placeholder="(optional)" />
        <div className="flex justify-end gap-2 pt-1">
          {saved && <span className="text-xs text-green-400 self-center">Saved!</span>}
          <Button variant="primary" onClick={() => mut.mutate()} disabled={mut.isPending || Object.keys(form).length === 0}>
            {mut.isPending ? <Spinner size={12} /> : null}
            Save Settings
          </Button>
        </div>
      </div>
    </section>
  )
}

export function SettingsPage() {
  const nav = useNavigate()
  const { data: info } = useQuery({ queryKey: ['sysinfo'], queryFn: getSystemInfo })

  const logout = () => { clearToken(); nav('/login') }

  return (
    <div className="min-h-screen bg-[#0f0d14] p-6">
      <header className="flex items-center justify-between mb-8 max-w-2xl mx-auto">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => nav('/')}>← Back</Button>
          <h1 className="text-xl font-semibold text-slate-100">Settings</h1>
        </div>
        <div className="flex items-center gap-3">
          {info && <span className="text-xs text-slate-600">VisionQ v{info.version} · {info.platform}</span>}
          <Button variant="danger" size="sm" onClick={logout}>Log out</Button>
        </div>
      </header>

      <main className="max-w-2xl mx-auto flex flex-col gap-5">
        <TokenSection />
        <ServerSettings />
      </main>
    </div>
  )
}
