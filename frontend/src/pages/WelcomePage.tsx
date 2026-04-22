import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getRecentProjects, openProject, createProject, getSystemInfo } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Modal } from '../components/ui/Modal'
import { Input } from '../components/ui/Input'
import { Spinner } from '../components/ui/Spinner'

interface RecentProject {
  name: string
  path: string
  modified_at: string
  image_count: number
  annotated_count: number
}

function CreateProjectModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const nav = useNavigate()
  const [form, setForm] = useState({ name: '', path: '', images_dir: '' })
  const [err, setErr] = useState('')

  const mut = useMutation({
    mutationFn: () => createProject(form),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['recent'] })
      onClose()
      nav(`/annotate?project=${encodeURIComponent(data.path)}`)
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Failed to create project.'
      setErr(msg)
    },
  })

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <Modal open={open} onClose={onClose} title="Create New Project">
      <div className="flex flex-col gap-4">
        <Input label="Project name" value={form.name} onChange={set('name')} placeholder="MyDataset" />
        <Input label="Project file path (.json)" value={form.path} onChange={set('path')} placeholder="/data/projects/my_project.json" />
        <Input label="Images directory" value={form.images_dir} onChange={set('images_dir')} placeholder="/data/images/" />
        {err && <p className="text-xs text-red-400">{err}</p>}
        <div className="flex gap-2 justify-end pt-1">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            disabled={mut.isPending || !form.name || !form.path || !form.images_dir}
            onClick={() => { setErr(''); mut.mutate() }}
          >
            {mut.isPending ? <Spinner size={12} /> : null}
            Create
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export function WelcomePage() {
  const nav = useNavigate()
  const [createOpen, setCreateOpen] = useState(false)
  const [openErr, setOpenErr] = useState('')

  const { data: info } = useQuery({ queryKey: ['sysinfo'], queryFn: getSystemInfo, retry: false })
  const { data: recent = [], isLoading } = useQuery<RecentProject[]>({
    queryKey: ['recent'],
    queryFn: getRecentProjects,
  })

  const openMut = useMutation({
    mutationFn: (path: string) => openProject(path),
    onSuccess: (_data, path) => nav(`/annotate?project=${encodeURIComponent(path)}`),
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Failed to open project.'
      setOpenErr(msg)
    },
  })

  return (
    <div className="min-h-screen bg-[#0f0d14] p-6">
      <CreateProjectModal open={createOpen} onClose={() => setCreateOpen(false)} />

      <header className="flex items-center justify-between mb-8 max-w-4xl mx-auto">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-violet-600/20 border border-violet-500/30 flex items-center justify-center">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="1.5">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          </div>
          <span className="text-lg font-semibold text-slate-100">VisionQ</span>
          {info && <span className="text-xs text-slate-500">v{info.version}</span>}
        </div>
        <nav className="flex gap-1">
          <Button variant="ghost" size="sm" onClick={() => nav('/detection')}>Detection</Button>
          <Button variant="ghost" size="sm" onClick={() => nav('/settings')}>Settings</Button>
        </nav>
      </header>

      <main className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-semibold text-slate-100">Projects</h1>
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            <span className="text-lg leading-none">+</span>
            New Project
          </Button>
        </div>

        {openErr && (
          <div className="mb-4 px-4 py-3 bg-red-900/30 border border-red-700 rounded-lg text-sm text-red-300">
            {openErr}
          </div>
        )}

        {isLoading ? (
          <div className="flex justify-center py-16"><Spinner size={28} /></div>
        ) : recent.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-16 h-16 rounded-2xl bg-slate-800 border border-slate-700 flex items-center justify-center mb-4">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#6b6375" strokeWidth="1.5">
                <path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
                <path d="M16 3v4M8 3v4M3 11h18" />
              </svg>
            </div>
            <p className="text-slate-400 text-sm">No recent projects</p>
            <p className="text-slate-600 text-xs mt-1">Create a project to get started</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {recent.map((p) => (
              <button
                key={p.path}
                onClick={() => openMut.mutate(p.path)}
                disabled={openMut.isPending}
                className="w-full text-left bg-slate-900 hover:bg-slate-800 border border-slate-700 hover:border-violet-500/50
                  rounded-xl px-5 py-4 transition-all group cursor-pointer disabled:opacity-60"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="font-medium text-slate-100 group-hover:text-violet-300 transition-colors truncate">
                      {p.name}
                    </p>
                    <p className="text-xs text-slate-500 mt-0.5 truncate">{p.path}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <div className="flex gap-3 text-xs">
                      <span className="text-slate-400">{p.image_count} images</span>
                      <span className="text-violet-400">{p.annotated_count} annotated</span>
                    </div>
                    <span className="text-xs text-slate-600">
                      {new Date(p.modified_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
