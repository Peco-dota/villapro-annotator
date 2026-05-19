import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getRecentProjects, openProject, createProject, getSystemInfo, removeRecentProject, getActiveTrain, getActiveMergeJob, dismissMergeJob, getActiveAugJob, getServices } from '../lib/api'
import { getUser, clearToken } from '../lib/auth'
import { Button } from '../components/ui/Button'
import { Modal } from '../components/ui/Modal'
import { Input } from '../components/ui/Input'
import { PathInput } from '../components/ui/PathInput'
import { FilePicker } from '../components/ui/FilePicker'
import { Spinner } from '../components/ui/Spinner'
import { MergeDatasets } from '../components/merge/MergeDatasets'
import { AugmentDataset } from '../components/augment/AugmentDataset'
import { TrainModel } from '../components/train/TrainModel'
import { DetectionSection } from '../components/detection/DetectionSection'
import { RecordingsSection } from '../components/recordings/RecordingsSection'
import { DebugLogsSection } from '../components/debug/DebugLogsSection'
import { FilesSection } from '../components/files/FilesSection'

interface RecentProject {
  name: string
  path: string
  image_folder: string
  total_images: number
  annotated_images: number
}

const CLASS_COLORS = [
  '#ef4444', '#f97316', '#eab308', '#22c55e', '#06b6d4',
  '#3b82f6', '#8b5cf6', '#ec4899', '#14b8a6', '#a78bfa',
]

// ── Create Project Modal ──────────────────────────────────────────────────────

function CreateProjectModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const nav = useNavigate()
  const [form, setForm] = useState({
    name: '',
    save_path: '',
    import_yolo_labels: false,
    coco_json_path: '',
  })
  const [imageFolders, setImageFolders] = useState<string[]>([''])
  const [classes, setClasses] = useState<string[]>([])
  const [newClass, setNewClass] = useState('')
  const [err, setErr] = useState('')

  const addClassEntry = () => {
    const name = newClass.trim()
    if (!name || classes.includes(name)) return
    setClasses(c => [...c, name])
    setNewClass('')
  }

  const mut = useMutation({
    mutationFn: () => createProject({
      name: form.name,
      save_path: form.save_path,
      image_folders: imageFolders.filter(f => f.trim()),
      import_yolo_labels: form.import_yolo_labels,
      coco_json_path: form.coco_json_path || undefined,
      classes,
    }),
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

  const set = (k: keyof typeof form) => (v: string | boolean) =>
    setForm(f => ({ ...f, [k]: v }))

  const filledFolders = imageFolders.filter(f => f.trim())

  return (
    <Modal open={open} onClose={onClose} title="Create New Project" width="max-w-lg">
      <div className="flex flex-col gap-4 max-h-[80vh] overflow-y-auto pr-1">
        <Input
          label="Project name"
          value={form.name}
          onChange={e => set('name')(e.target.value)}
          placeholder="MyDataset"
          autoFocus
        />
        <PathInput
          label="Save location (optional — leave blank to use default)"
          value={form.save_path}
          onChange={v => set('save_path')(v)}
          filter="dir"
          dirOnly={true}
          placeholder="(auto — /data/projects/<username>/)"
          pickerTitle="Choose save location"
        />

        {/* Image folders */}
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium text-slate-400">Image folders</p>
          {imageFolders.map((folder, i) => (
            <div key={i} className="flex items-end gap-2">
              <div className="flex-1">
                <PathInput
                  label=""
                  value={folder}
                  onChange={v => setImageFolders(fs => fs.map((f, j) => j === i ? v : f))}
                  filter="dir"
                  dirOnly={true}
                  placeholder="/data/images/"
                  pickerTitle={`Select images folder ${i + 1}`}
                />
              </div>
              {imageFolders.length > 1 && (
                <button
                  onClick={() => setImageFolders(fs => fs.filter((_, j) => j !== i))}
                  className="mb-0.5 px-2 py-1.5 text-slate-500 hover:text-red-400 hover:bg-red-400/10 rounded text-sm cursor-pointer"
                  title="Remove folder"
                >×</button>
              )}
            </div>
          ))}
          <button
            onClick={() => setImageFolders(fs => [...fs, ''])}
            className="self-start text-xs text-violet-400 hover:text-violet-300 cursor-pointer"
          >+ Add another folder</button>
        </div>

        {/* Classes */}
        <div className="flex flex-col gap-2 pt-1 border-t border-slate-700/50">
          <p className="text-xs text-slate-500 font-medium uppercase tracking-wider">Classes</p>
          <div className="flex gap-2">
            <input
              value={newClass}
              onChange={e => setNewClass(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') addClassEntry() }}
              placeholder="Class name (e.g. car)"
              className="flex-1 bg-slate-800 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-100
                placeholder:text-slate-600 focus:outline-none focus:border-violet-500"
            />
            <button
              onClick={addClassEntry}
              className="px-3 py-1.5 bg-violet-700 hover:bg-violet-600 text-white rounded text-sm cursor-pointer"
            >Add</button>
          </div>
          {classes.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {classes.map((cls, i) => (
                <span key={i} className="flex items-center gap-1.5 bg-slate-800 border border-slate-700 rounded-full px-2.5 py-0.5 text-xs text-slate-200">
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ background: CLASS_COLORS[i % CLASS_COLORS.length] }} />
                  {cls}
                  <button
                    onClick={() => setClasses(c => c.filter((_, j) => j !== i))}
                    className="text-slate-500 hover:text-red-400 cursor-pointer ml-0.5"
                  >×</button>
                </span>
              ))}
            </div>
          )}
          {classes.length === 0 && (
            <p className="text-xs text-slate-600">You can also add classes later in the annotation editor.</p>
          )}
        </div>

        <div className="flex flex-col gap-2 pt-1 border-t border-slate-700/50">
          <p className="text-xs text-slate-500 font-medium uppercase tracking-wider">Import existing labels (optional)</p>
          <label className="flex items-center gap-2 cursor-pointer text-sm text-slate-300">
            <input
              type="checkbox"
              checked={form.import_yolo_labels}
              onChange={e => set('import_yolo_labels')(e.target.checked)}
              className="accent-violet-500"
            />
            Import YOLO .txt labels from images folder
          </label>
          <PathInput
            label="COCO JSON (optional)"
            value={form.coco_json_path}
            onChange={v => set('coco_json_path')(v)}
            filter="project"
            placeholder="(leave blank to skip)"
            pickerTitle="Select COCO JSON file"
          />
        </div>

        {err && <p className="text-xs text-red-400">{err}</p>}
        <div className="flex gap-2 justify-end pt-1">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            disabled={mut.isPending || !form.name || filledFolders.length === 0}
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

// ── Section: Annotate ─────────────────────────────────────────────────────────

function AnnotateSection() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const user = getUser()
  const isAdmin = user?.role === 'admin'

  const [createOpen, setCreateOpen] = useState(false)
  const [openPickerOpen, setOpenPickerOpen] = useState(false)
  const [openErr, setOpenErr] = useState('')
  const [showAll, setShowAll] = useState(false)
  const [confirmDeletePath, setConfirmDeletePath] = useState<string | null>(null)

  const { data: recent = [], isLoading } = useQuery<RecentProject[]>({
    queryKey: ['recent', showAll],
    queryFn: () => getRecentProjects(showAll),
  })

  const openMut = useMutation({
    mutationFn: (path: string) => openProject(path),
    onSuccess: (_data, path) => nav(`/annotate?project=${encodeURIComponent(path)}`),
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Failed to open project.'
      setOpenErr(msg)
    },
  })

  const removeMut = useMutation({
    mutationFn: (path: string) => removeRecentProject(path),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recent'] }),
  })

  return (
    <>
      <CreateProjectModal open={createOpen} onClose={() => setCreateOpen(false)} />
      <FilePicker
        open={openPickerOpen}
        onClose={() => setOpenPickerOpen(false)}
        onSelect={path => openMut.mutate(path)}
        filter="project"
        title="Open Project File"
        initialPath="/"
      />

      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Recent Projects</h2>
          {isAdmin && (
            <label className="flex items-center gap-1.5 cursor-pointer text-xs text-slate-500 hover:text-slate-300 select-none">
              <input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} className="accent-violet-500" />
              All users
            </label>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => setOpenPickerOpen(true)}>Open…</Button>
          <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>+ New Project</Button>
        </div>
      </div>

      {openErr && (
        <div className="mb-3 px-4 py-2 bg-red-900/30 border border-red-700 rounded-lg text-sm text-red-300">{openErr}</div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-8"><Spinner size={24} /></div>
      ) : recent.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-10 text-center border border-dashed border-slate-700 rounded-xl">
          <p className="text-slate-500 text-sm">No recent projects</p>
          <p className="text-slate-600 text-xs mt-1">Create a new project or open an existing .annotatex file</p>
        </div>
      ) : (
        <div className="grid gap-2">
          {recent.map((p) => (
            <div key={p.path} className="relative group bg-[#16213e] border border-[#1e293b] hover:border-violet-500/40 rounded-xl transition-all overflow-hidden">
              <button
                onClick={() => openMut.mutate(p.path)}
                disabled={openMut.isPending}
                className="w-full text-left px-4 py-3 cursor-pointer disabled:opacity-60 hover:bg-[#1a2744] rounded-xl pr-10"
              >
                <div className="flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <p className="font-medium text-slate-100 group-hover:text-violet-300 transition-colors truncate text-sm">{p.name}</p>
                    <p className="text-xs text-[#475569] mt-0.5 font-mono truncate">{p.path}</p>
                  </div>
                  <div className="flex items-center gap-3 shrink-0 text-xs">
                    <span className="text-slate-400">{p.total_images} imgs</span>
                    <span className="text-green-400">{p.annotated_images} annotated</span>
                  </div>
                </div>
              </button>
              {confirmDeletePath === p.path ? (
                <div className="absolute inset-0 flex items-center justify-between px-4 bg-[#1a1a2e] border border-red-700/50 rounded-xl">
                  <span className="text-sm text-red-300">Remove from list?</span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setConfirmDeletePath(null)}
                      className="px-3 py-1 text-xs text-slate-400 hover:text-slate-200 bg-slate-700 hover:bg-slate-600 rounded cursor-pointer"
                    >Cancel</button>
                    <button
                      onClick={() => { removeMut.mutate(p.path); setConfirmDeletePath(null) }}
                      disabled={removeMut.isPending}
                      className="px-3 py-1 text-xs text-white bg-red-700 hover:bg-red-600 rounded cursor-pointer disabled:opacity-60"
                    >Remove</button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmDeletePath(p.path)}
                  title="Remove from list"
                  className="absolute top-2.5 right-2.5 w-6 h-6 flex items-center justify-center rounded
                    text-slate-600 hover:text-red-400 hover:bg-red-400/10 transition-colors cursor-pointer
                    opacity-0 group-hover:opacity-100"
                >×</button>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  )
}

// ── Nav tile ──────────────────────────────────────────────────────────────────

function NavTile({
  icon, label, description, onClick, active, badge,
}: {
  icon: React.ReactNode
  label: string
  description: React.ReactNode
  onClick: () => void
  active?: boolean
  badge?: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-4 px-5 py-4 rounded-xl border transition-all cursor-pointer text-left w-full
        ${active
          ? 'bg-violet-700/20 border-violet-500/60 text-violet-300'
          : 'bg-[#16213e] border-[#1e293b] hover:border-violet-500/40 hover:bg-[#1a2744] text-slate-300'}`}
    >
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0
        ${active ? 'bg-violet-600/30' : 'bg-slate-800'}`}>
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className={`font-semibold text-sm ${active ? 'text-violet-200' : 'text-slate-100'}`}>{label}</p>
          {badge}
        </div>
        <p className="text-xs text-slate-500 mt-0.5">{description}</p>
      </div>
    </button>
  )
}

// ── Icons ─────────────────────────────────────────────────────────────────────

const IconAnnotate = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <rect x="8" y="8" width="8" height="8" rx="0.5" strokeDasharray="2 1.5" />
  </svg>
)

const IconDetection = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <circle cx="12" cy="12" r="3" />
    <path d="M3 12h3M18 12h3M12 3v3M12 18v3" />
    <path d="M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" />
  </svg>
)

const IconTrain = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M12 2L2 7l10 5 10-5-10-5z" />
    <path d="M2 17l10 5 10-5" />
    <path d="M2 12l10 5 10-5" />
  </svg>
)

const IconAugment = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M12 3v3M12 18v3M3 12h3M18 12h3" />
    <path d="M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" />
    <circle cx="12" cy="12" r="4" />
    <path d="M12 8v4l2 2" strokeLinecap="round" />
  </svg>
)

const IconMerge = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M8 6H5a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h3" />
    <path d="M16 6h3a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-3" />
    <path d="M12 3v18" />
    <path d="M9 7l3-4 3 4" />
    <path d="M9 17l3 4 3-4" />
  </svg>
)

const IconRecordings = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <rect x="2" y="4" width="20" height="16" rx="2" />
    <circle cx="12" cy="12" r="3" />
    <path d="M17 4v16M7 4v16" />
  </svg>
)

const IconDebugLogs = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="8" y1="13" x2="16" y2="13" />
    <line x1="8" y1="17" x2="12" y2="17" />
  </svg>
)

const IconFiles = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6z" />
    <line x1="9" y1="13" x2="15" y2="13" />
    <line x1="12" y1="10" x2="12" y2="16" />
  </svg>
)

// ── Main page ─────────────────────────────────────────────────────────────────

type Section = 'annotate' | 'merge' | 'augment' | 'train' | 'detection' | 'recordings' | 'debug-logs' | 'files'

export function WelcomePage() {
  const nav = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const user = getUser()
  const activeSection = (searchParams.get('tab') as Section | null) ?? 'annotate'
  const setActiveSection = (s: Section) => setSearchParams({ tab: s }, { replace: true })

  const qc = useQueryClient()
  const { data: info } = useQuery({ queryKey: ['sysinfo'], queryFn: getSystemInfo, retry: false })
  const { data: trainActive } = useQuery({ queryKey: ['train-active'], queryFn: getActiveTrain, refetchInterval: (q) => q.state.data?.status === 'running' ? 2000 : 10000 })
  const { data: mergeActive } = useQuery({ queryKey: ['merge-active'], queryFn: getActiveMergeJob, refetchInterval: (q) => q.state.data?.status === 'running' ? 2000 : 10000 })
  const { data: augActive } = useQuery({ queryKey: ['aug-active'], queryFn: getActiveAugJob, refetchInterval: (q) => q.state.data?.status === 'running' ? 2000 : 10000 })
  const { data: allServices } = useQuery({ queryKey: ['services'], queryFn: getServices, refetchInterval: 5000 })
  const runningCount = (allServices ?? []).filter((s: { state: string }) => s.state === 'running').length

  const dismissMergeMut = useMutation({
    mutationFn: dismissMergeJob,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['merge-active'] }),
  })

  const logout = () => { clearToken(); nav('/login') }

  return (
    <div className="min-h-screen bg-[#0f172a] flex flex-col">
      {/* Top bar */}
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
          <Button variant="ghost" size="sm" onClick={() => nav('/settings')}>Settings</Button>
          <Button variant="ghost" size="sm" onClick={logout}>Sign out</Button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Left nav */}
        <aside className="w-72 border-r border-[#1e293b] p-4 flex flex-col gap-2 shrink-0 overflow-y-auto">
          <p className="text-[10px] font-bold text-slate-600 uppercase tracking-widest px-1 mb-1">Workspace</p>

          <NavTile
            icon={<IconAnnotate />}
            label="Annotate"
            description="Label images, manage projects"
            onClick={() => setActiveSection('annotate')}
            active={activeSection === 'annotate'}
          />
          <NavTile
            icon={<IconMerge />}
            label="Merge Datasets"
            description={
              mergeActive?.active && mergeActive.status === 'running' && mergeActive.total > 0
                ? `${mergeActive.progress ?? 0} / ${mergeActive.total} images`
                : 'Combine multiple projects into one'
            }
            onClick={() => setActiveSection('merge')}
            active={activeSection === 'merge'}
            badge={mergeActive?.active ? (
              mergeActive.status === 'running' ? (
                <span className="flex items-center gap-1 text-[10px] font-bold text-teal-300 bg-teal-900/40 border border-teal-500/30 px-1.5 py-0.5 rounded-full">
                  <span className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-pulse inline-block" />
                  MERGING
                </span>
              ) : mergeActive.status === 'done' ? (
                <span
                  className="flex items-center gap-1 text-[10px] font-bold text-green-300 bg-green-900/40 border border-green-500/30 px-1.5 py-0.5 rounded-full cursor-pointer hover:bg-green-900/70"
                  onClick={e => { e.stopPropagation(); dismissMergeMut.mutate() }}
                >
                  ✓ DONE ×
                </span>
              ) : mergeActive.status === 'failed' ? (
                <span
                  className="flex items-center gap-1 text-[10px] font-bold text-red-300 bg-red-900/40 border border-red-500/30 px-1.5 py-0.5 rounded-full cursor-pointer hover:bg-red-900/70"
                  onClick={e => { e.stopPropagation(); dismissMergeMut.mutate() }}
                >
                  ✗ {mergeActive.error === 'Cancelled' ? 'CANCELLED' : 'FAILED'} ×
                </span>
              ) : undefined
            ) : undefined}
          />
          <NavTile
            icon={<IconAugment />}
            label="Augment"
            description={
              augActive?.active && augActive.status === 'running' && augActive.total > 0
                ? `${augActive.progress ?? 0} / ${augActive.total} images`
                : 'Enrich an exported dataset with augmented copies'
            }
            onClick={() => setActiveSection('augment')}
            active={activeSection === 'augment'}
            badge={augActive?.active ? (
              augActive.status === 'running' ? (
                <span className="flex items-center gap-1 text-[10px] font-bold text-teal-300 bg-teal-900/40 border border-teal-500/30 px-1.5 py-0.5 rounded-full">
                  <span className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-pulse inline-block" />
                  AUGMENTING
                </span>
              ) : augActive.status === 'done' ? (
                <span className="flex items-center gap-1 text-[10px] font-bold text-green-300 bg-green-900/40 border border-green-500/30 px-1.5 py-0.5 rounded-full">
                  ✓ DONE
                </span>
              ) : augActive.status === 'failed' ? (
                <span className="flex items-center gap-1 text-[10px] font-bold text-red-300 bg-red-900/40 border border-red-500/30 px-1.5 py-0.5 rounded-full">
                  ✗ {augActive.error === 'Cancelled' ? 'CANCELLED' : 'FAILED'}
                </span>
              ) : undefined
            ) : undefined}
          />
          <NavTile
            icon={<IconTrain />}
            label="Train Model"
            description={
              trainActive?.active
                ? trainActive.status === 'running'
                  ? `Epoch ${trainActive.epoch ?? 0}/${trainActive.total_epochs ?? '?'} — ${trainActive.run_name}`
                  : trainActive.status === 'done'
                    ? `Completed — ${trainActive.run_name}`
                    : (trainActive.error?.includes('Cancelled') || trainActive.error?.includes('Force-stopped'))
                      ? `Cancelled — ${trainActive.run_name}`
                      : `Failed — ${trainActive.run_name}`
                : 'Train YOLO from an annotated dataset'
            }
            onClick={() => setActiveSection('train')}
            active={activeSection === 'train'}
            badge={trainActive?.active ? (
              trainActive.status === 'running' ? (
                <span className="flex items-center gap-1 text-[10px] font-bold text-violet-300 bg-violet-900/40 border border-violet-500/30 px-1.5 py-0.5 rounded-full">
                  <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse inline-block" />
                  TRAINING
                </span>
              ) : trainActive.status === 'done' ? (
                <span className="flex items-center gap-1 text-[10px] font-bold text-green-300 bg-green-900/40 border border-green-500/30 px-1.5 py-0.5 rounded-full">
                  ✓ DONE
                </span>
              ) : trainActive.status === 'failed' ? (
                <span className="flex items-center gap-1 text-[10px] font-bold text-red-300 bg-red-900/40 border border-red-500/30 px-1.5 py-0.5 rounded-full">
                  ✗ {(trainActive.error?.includes('Cancelled') || trainActive.error?.includes('Force-stopped')) ? 'CANCELLED' : 'FAILED'}
                </span>
              ) : undefined
            ) : undefined}
          />
          <NavTile
            icon={<IconDetection />}
            label="Detection"
            description={runningCount > 0
              ? <span className="flex items-center gap-1.5 text-teal-400 font-medium"><span className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-pulse shrink-0 inline-block" />{runningCount} service{runningCount !== 1 ? 's' : ''} running</span>
              : 'Run and monitor detection services'
            }
            onClick={() => setActiveSection('detection')}
            active={activeSection === 'detection'}
          />
          <NavTile
            icon={<IconRecordings />}
            label="Recordings"
            description="Browse, download and delete recorded streams"
            onClick={() => setActiveSection('recordings')}
            active={activeSection === 'recordings'}
          />
          <NavTile
            icon={<IconDebugLogs />}
            label="Debug Logs"
            description="Browse, download and delete direction debug CSVs"
            onClick={() => setActiveSection('debug-logs')}
            active={activeSection === 'debug-logs'}
          />
          <NavTile
            icon={<IconFiles />}
            label="Files"
            description="Browse, upload, download and delete server files"
            onClick={() => setActiveSection('files')}
            active={activeSection === 'files'}
          />
        </aside>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto p-6">

          {activeSection === 'annotate' && <AnnotateSection />}

          {activeSection === 'train' && <TrainModel />}

          {activeSection === 'merge' && <MergeDatasets />}
          {activeSection === 'augment' && <AugmentDataset />}
          {activeSection === 'detection' && <DetectionSection />}
          {activeSection === 'recordings' && <RecordingsSection />}
          {activeSection === 'debug-logs' && <DebugLogsSection />}
          {activeSection === 'files' && <FilesSection />}

        </main>
      </div>
    </div>
  )
}
