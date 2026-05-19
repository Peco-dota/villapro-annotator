import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { browsePath, fsMkdir, fsDelete, fsMove, fsDownloadUrl, uploadFile } from '../../lib/api'
import { Spinner } from '../ui/Spinner'
import { Button } from '../ui/Button'

const fmtSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

const fmtDate = (ts: number) => new Date(ts * 1000).toLocaleDateString()

const fileIcon = (name: string) => {
  const ext = name.split('.').pop()?.toLowerCase() ?? ''
  if (['pt', 'pth', 'onnx'].includes(ext)) return '🤖'
  if (['yaml', 'yml'].includes(ext)) return '📋'
  if (['json', 'annotatex'].includes(ext)) return '📦'
  if (['mp4', 'avi', 'mov', 'mkv', 'webm', 'm4v'].includes(ext)) return '🎥'
  if (['jpg', 'jpeg', 'png', 'bmp', 'tiff', 'tif', 'webp'].includes(ext)) return '🖼'
  if (['csv', 'tsv'].includes(ext)) return '📊'
  if (['txt'].includes(ext)) return '📝'
  return '📄'
}

interface UploadState {
  id: number
  name: string
  pct: number
  done: boolean
  error?: string
}

interface ConfirmState {
  path: string
  name: string
  isDir: boolean
}

interface MoveState {
  path: string
  dest: string
}

export function FilesSection() {
  const [cwd, setCwd] = useState('/villapro-data')
  const [manualPath, setManualPath] = useState('/villapro-data')
  const [newFolderMode, setNewFolderMode] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [newFolderErr, setNewFolderErr] = useState('')
  const [confirm, setConfirm] = useState<ConfirmState | null>(null)
  const [deleteErr, setDeleteErr] = useState('')
  const [moving, setMoving] = useState<MoveState | null>(null)
  const [moveErr, setMoveErr] = useState('')
  const [uploads, setUploads] = useState<UploadState[]>([])
  const uploadRef = useRef<HTMLInputElement>(null)
  const uploadId = useRef(0)

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['files-browser', cwd],
    queryFn: () => browsePath(cwd, '*'),
    retry: 1,
    refetchOnWindowFocus: false,
  })

  useEffect(() => {
    if (data?.cwd) {
      setManualPath(data.cwd)
    }
  }, [data?.cwd])

  const navigate = (path: string) => {
    setCwd(path)
    setManualPath(path)
    setConfirm(null)
    setDeleteErr('')
    setMoving(null)
    setMoveErr('')
    setNewFolderMode(false)
    setNewFolderName('')
  }

  const mkdirMut = useMutation({
    mutationFn: () => fsMkdir(data?.cwd ?? cwd, newFolderName.trim()),
    onSuccess: () => {
      refetch()
      setNewFolderMode(false)
      setNewFolderName('')
      setNewFolderErr('')
    },
    onError: (e: unknown) => {
      setNewFolderErr((e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Failed to create folder.')
    },
  })

  const deleteMut = useMutation({
    mutationFn: ({ path, recursive }: { path: string; recursive: boolean }) => fsDelete(path, recursive),
    onSuccess: () => {
      refetch()
      setConfirm(null)
      setDeleteErr('')
    },
    onError: (e: unknown) => {
      setDeleteErr((e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Delete failed.')
    },
  })

  const moveMut = useMutation({
    mutationFn: ({ src, dest }: { src: string; dest: string }) => fsMove(src, dest),
    onSuccess: (result) => {
      refetch()
      setMoving(null)
      setMoveErr('')
      // If destination is outside current dir, navigate there
      const destDir = result.dest.substring(0, result.dest.lastIndexOf('/')) || '/'
      if (destDir !== (data?.cwd ?? cwd)) navigate(destDir)
    },
    onError: (e: unknown) => {
      setMoveErr((e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Move failed.')
    },
  })

  const handleUpload = async (files: FileList | null) => {
    if (!files || !data) return
    for (const file of Array.from(files)) {
      const id = ++uploadId.current
      setUploads(u => [...u, { id, name: file.name, pct: 0, done: false }])
      try {
        await uploadFile(file, data.cwd, pct => {
          setUploads(u => u.map(x => x.id === id ? { ...x, pct } : x))
        })
        setUploads(u => u.map(x => x.id === id ? { ...x, pct: 100, done: true } : x))
        refetch()
      } catch {
        setUploads(u => u.map(x => x.id === id ? { ...x, error: 'Upload failed' } : x))
      }
    }
    if (uploadRef.current) uploadRef.current.value = ''
    setTimeout(() => setUploads(u => u.filter(x => !x.done && !x.error)), 3000)
  }

  const segments = (data?.cwd ?? cwd).split('/').filter(Boolean)

  return (
    <div className="flex flex-col gap-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Files</h2>
          {data && (
            <p className="text-xs text-slate-500 mt-0.5">
              {data.dirs.length} folder{data.dirs.length !== 1 ? 's' : ''}, {data.files.length} file{data.files.length !== 1 ? 's' : ''}
            </p>
          )}
        </div>
        <Button variant="ghost" size="sm" onClick={() => refetch()}>Refresh</Button>
      </div>

      {/* Path bar */}
      <div className="flex gap-2">
        <input
          value={manualPath}
          onChange={e => setManualPath(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && manualPath.trim()) navigate(manualPath.trim()) }}
          className="flex-1 bg-[#0f172a] border border-[#334155] rounded px-3 py-1.5 text-sm text-slate-100
            font-mono focus:outline-none focus:border-violet-500"
          placeholder="/villapro-data"
          spellCheck={false}
        />
        <Button size="sm" variant="secondary" onClick={() => manualPath.trim() && navigate(manualPath.trim())}>Go</Button>
      </div>

      {/* Breadcrumb */}
      {data && (
        <div className="flex items-center gap-0.5 text-xs font-mono flex-wrap -mt-2">
          <button onClick={() => navigate('/')} className="text-violet-400 hover:text-violet-300 cursor-pointer">/</button>
          {segments.map((seg, i) => {
            const fullPath = '/' + segments.slice(0, i + 1).join('/')
            const isLast = i === segments.length - 1
            return (
              <span key={i} className="flex items-center gap-0.5">
                {i > 0 && <span className="text-slate-700">/</span>}
                {isLast ? (
                  <span className="text-slate-300">{seg}</span>
                ) : (
                  <button
                    onClick={() => navigate(fullPath)}
                    className="text-violet-400 hover:text-violet-300 cursor-pointer hover:underline"
                  >{seg}</button>
                )}
              </span>
            )
          })}
        </div>
      )}

      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        <Button
          size="sm" variant="secondary"
          disabled={!data?.parent}
          onClick={() => data?.parent && navigate(data.parent)}
        >↑ Up</Button>
        <Button
          size="sm" variant="secondary"
          onClick={() => { setNewFolderMode(true); setNewFolderName(''); setNewFolderErr('') }}
        >+ New folder</Button>
        <input
          ref={uploadRef}
          type="file"
          multiple
          className="hidden"
          onChange={e => handleUpload(e.target.files)}
        />
        <Button size="sm" variant="secondary" onClick={() => uploadRef.current?.click()}>
          ↑ Upload file
        </Button>
      </div>

      {/* New folder input */}
      {newFolderMode && (
        <div className="flex flex-col gap-1.5">
          <div className="flex gap-2">
            <input
              autoFocus
              value={newFolderName}
              onChange={e => { setNewFolderName(e.target.value); setNewFolderErr('') }}
              onKeyDown={e => {
                if (e.key === 'Enter') mkdirMut.mutate()
                if (e.key === 'Escape') { setNewFolderMode(false); setNewFolderName('') }
              }}
              placeholder="New folder name"
              className="flex-1 bg-[#0f172a] border border-violet-600 rounded px-3 py-1.5 text-sm text-slate-100
                placeholder:text-slate-600 focus:outline-none font-mono"
            />
            <Button size="sm" variant="primary" onClick={() => mkdirMut.mutate()} disabled={!newFolderName.trim() || mkdirMut.isPending}>
              {mkdirMut.isPending ? <Spinner size={12} /> : 'Create'}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => { setNewFolderMode(false); setNewFolderName(''); setNewFolderErr('') }}>
              Cancel
            </Button>
          </div>
          {newFolderErr && <p className="text-xs text-red-400">{newFolderErr}</p>}
        </div>
      )}

      {/* Upload progress */}
      {uploads.length > 0 && (
        <div className="flex flex-col gap-1.5 px-3 py-2 bg-[#0f172a] rounded-lg border border-[#1e293b]">
          {uploads.map(u => (
            <div key={u.id} className="flex items-center gap-3 text-xs">
              <span className="text-slate-400 truncate max-w-xs font-mono">{u.name}</span>
              {u.error ? (
                <span className="text-red-400 ml-auto">{u.error}</span>
              ) : u.done ? (
                <span className="text-green-400 ml-auto">✓ Done</span>
              ) : (
                <div className="flex items-center gap-2 ml-auto">
                  <div className="w-24 h-1 bg-slate-700 rounded-full overflow-hidden">
                    <div className="h-full bg-violet-500 rounded-full transition-all" style={{ width: `${u.pct}%` }} />
                  </div>
                  <span className="text-slate-500 w-8 text-right">{u.pct}%</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Delete / move errors */}
      {deleteErr && <p className="text-xs text-red-400 px-1">{deleteErr}</p>}
      {moveErr && <p className="text-xs text-red-400 px-1">{moveErr}</p>}

      {/* File listing */}
      <div className="border border-[#1e293b] rounded-xl overflow-hidden">
        {isLoading && (
          <div className="flex items-center justify-center py-16">
            <Spinner size={24} />
          </div>
        )}
        {error && (
          <div className="flex items-center justify-center py-16 text-sm text-red-400 px-6 text-center">
            {(error as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Failed to load directory.'}
          </div>
        )}
        {!isLoading && !error && data && data.dirs.length === 0 && data.files.length === 0 && (
          <div className="flex items-center justify-center py-16 text-sm text-slate-600">
            Empty directory
          </div>
        )}
        {!isLoading && !error && data && (data.dirs.length > 0 || data.files.length > 0) && (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e293b] bg-[#0a0f1e]">
                <th className="px-4 py-2 text-left text-xs font-bold text-slate-600 uppercase tracking-wider">Name</th>
                <th className="px-4 py-2 text-right text-xs font-bold text-slate-600 uppercase tracking-wider whitespace-nowrap hidden sm:table-cell">Size</th>
                <th className="px-4 py-2 text-right text-xs font-bold text-slate-600 uppercase tracking-wider whitespace-nowrap hidden md:table-cell">Modified</th>
                <th className="px-4 py-2 text-right text-xs font-bold text-slate-600 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.dirs.map(dir => {
                const fullPath = `${data.cwd}/${dir}`
                const isConfirm = confirm?.path === fullPath
                const isMoving = moving?.path === fullPath

                if (isConfirm) {
                  return (
                    <tr key={dir} className="border-b border-[#1e293b]/50 bg-red-900/10">
                      <td colSpan={4} className="px-4 py-3">
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <p className="text-sm text-red-300 font-medium">
                              Delete "{dir}" and ALL its contents permanently?
                            </p>
                            <p className="text-xs text-red-400/70 mt-0.5">This cannot be undone.</p>
                            {deleteErr && <p className="text-xs text-red-400 mt-1">{deleteErr}</p>}
                          </div>
                          <div className="flex gap-2 shrink-0">
                            <button
                              onClick={() => { setConfirm(null); setDeleteErr('') }}
                              className="text-xs text-slate-400 hover:text-slate-200 px-2 py-1 bg-slate-700 hover:bg-slate-600 rounded cursor-pointer"
                            >Cancel</button>
                            <button
                              onClick={() => deleteMut.mutate({ path: fullPath, recursive: true })}
                              disabled={deleteMut.isPending}
                              className="text-xs text-white px-2 py-1 bg-red-700 hover:bg-red-600 rounded cursor-pointer disabled:opacity-60"
                            >
                              {deleteMut.isPending ? '…' : 'Delete all'}
                            </button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )
                }

                if (isMoving) {
                  return (
                    <tr key={dir} className="border-b border-[#1e293b]/50 bg-violet-900/10">
                      <td colSpan={4} className="px-4 py-3">
                        <div className="flex flex-col gap-2">
                          <p className="text-xs text-slate-400">Move <span className="text-slate-200 font-mono">{dir}/</span> to:</p>
                          <div className="flex gap-2">
                            <input
                              autoFocus
                              value={moving.dest}
                              onChange={e => { setMoving({ ...moving, dest: e.target.value }); setMoveErr('') }}
                              onKeyDown={e => {
                                if (e.key === 'Enter' && moving.dest.trim()) moveMut.mutate({ src: fullPath, dest: moving.dest.trim() })
                                if (e.key === 'Escape') { setMoving(null); setMoveErr('') }
                              }}
                              className="flex-1 bg-[#0f172a] border border-violet-600 rounded px-3 py-1.5 text-sm text-slate-100
                                font-mono focus:outline-none placeholder:text-slate-600"
                              placeholder="Destination path"
                            />
                            <button
                              onClick={() => moving.dest.trim() && moveMut.mutate({ src: fullPath, dest: moving.dest.trim() })}
                              disabled={moveMut.isPending || !moving.dest.trim()}
                              className="text-xs text-white px-3 py-1.5 bg-violet-700 hover:bg-violet-600 rounded cursor-pointer disabled:opacity-60"
                            >{moveMut.isPending ? '…' : 'Move'}</button>
                            <button
                              onClick={() => { setMoving(null); setMoveErr('') }}
                              className="text-xs text-slate-400 hover:text-slate-200 px-2 py-1.5 bg-slate-700 hover:bg-slate-600 rounded cursor-pointer"
                            >Cancel</button>
                          </div>
                          {moveErr && <p className="text-xs text-red-400">{moveErr}</p>}
                        </div>
                      </td>
                    </tr>
                  )
                }

                return (
                  <tr key={dir} className="border-b border-[#1e293b]/50 hover:bg-[#1e293b]/20 transition-colors group">
                    <td className="px-4 py-2.5">
                      <button
                        onClick={() => navigate(fullPath)}
                        className="flex items-center gap-2 cursor-pointer hover:text-violet-300 transition-colors text-left"
                      >
                        <span className="text-base shrink-0">📁</span>
                        <span className="font-mono text-slate-200 text-xs">{dir}/</span>
                      </button>
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs text-slate-700 hidden sm:table-cell">—</td>
                    <td className="px-4 py-2.5 text-right text-xs text-slate-700 hidden md:table-cell">—</td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="flex items-center gap-3 justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => { setMoving({ path: fullPath, dest: fullPath }); setMoveErr(''); setConfirm(null) }}
                          className="text-xs text-slate-400 hover:text-violet-400 cursor-pointer"
                        >Move</button>
                        <button
                          onClick={() => { setConfirm({ path: fullPath, name: dir, isDir: true }); setDeleteErr(''); setMoving(null) }}
                          className="text-xs text-slate-600 hover:text-red-400 cursor-pointer"
                        >Delete</button>
                      </div>
                    </td>
                  </tr>
                )
              })}

              {data.files.map(file => {
                const fullPath = `${data.cwd}/${file.name}`
                const isConfirm = confirm?.path === fullPath
                const isMoving = moving?.path === fullPath

                if (isConfirm) {
                  return (
                    <tr key={file.name} className="border-b border-[#1e293b]/50 bg-red-900/10">
                      <td colSpan={4} className="px-4 py-3">
                        <div className="flex items-center justify-between gap-4">
                          <p className="text-sm text-red-300 font-medium">Delete "{file.name}"?</p>
                          <div className="flex gap-2 shrink-0">
                            <button
                              onClick={() => { setConfirm(null); setDeleteErr('') }}
                              className="text-xs text-slate-400 hover:text-slate-200 px-2 py-1 bg-slate-700 hover:bg-slate-600 rounded cursor-pointer"
                            >Cancel</button>
                            <button
                              onClick={() => deleteMut.mutate({ path: fullPath, recursive: false })}
                              disabled={deleteMut.isPending}
                              className="text-xs text-white px-2 py-1 bg-red-700 hover:bg-red-600 rounded cursor-pointer disabled:opacity-60"
                            >
                              {deleteMut.isPending ? '…' : 'Delete'}
                            </button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )
                }

                if (isMoving) {
                  return (
                    <tr key={file.name} className="border-b border-[#1e293b]/50 bg-violet-900/10">
                      <td colSpan={4} className="px-4 py-3">
                        <div className="flex flex-col gap-2">
                          <p className="text-xs text-slate-400">Move <span className="text-slate-200 font-mono">{file.name}</span> to:</p>
                          <div className="flex gap-2">
                            <input
                              autoFocus
                              value={moving.dest}
                              onChange={e => { setMoving({ ...moving, dest: e.target.value }); setMoveErr('') }}
                              onKeyDown={e => {
                                if (e.key === 'Enter' && moving.dest.trim()) moveMut.mutate({ src: fullPath, dest: moving.dest.trim() })
                                if (e.key === 'Escape') { setMoving(null); setMoveErr('') }
                              }}
                              className="flex-1 bg-[#0f172a] border border-violet-600 rounded px-3 py-1.5 text-sm text-slate-100
                                font-mono focus:outline-none placeholder:text-slate-600"
                              placeholder="Destination path or directory"
                            />
                            <button
                              onClick={() => moving.dest.trim() && moveMut.mutate({ src: fullPath, dest: moving.dest.trim() })}
                              disabled={moveMut.isPending || !moving.dest.trim()}
                              className="text-xs text-white px-3 py-1.5 bg-violet-700 hover:bg-violet-600 rounded cursor-pointer disabled:opacity-60"
                            >{moveMut.isPending ? '…' : 'Move'}</button>
                            <button
                              onClick={() => { setMoving(null); setMoveErr('') }}
                              className="text-xs text-slate-400 hover:text-slate-200 px-2 py-1.5 bg-slate-700 hover:bg-slate-600 rounded cursor-pointer"
                            >Cancel</button>
                          </div>
                          {moveErr && <p className="text-xs text-red-400">{moveErr}</p>}
                        </div>
                      </td>
                    </tr>
                  )
                }

                return (
                  <tr key={file.name} className="border-b border-[#1e293b]/50 hover:bg-[#1e293b]/20 transition-colors group">
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <span className="text-base shrink-0">{fileIcon(file.name)}</span>
                        <span className="font-mono text-slate-300 text-xs">{file.name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs text-slate-500 whitespace-nowrap hidden sm:table-cell">{fmtSize(file.size)}</td>
                    <td className="px-4 py-2.5 text-right text-xs text-slate-500 whitespace-nowrap hidden md:table-cell">{fmtDate(file.modified)}</td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="flex items-center gap-3 justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                        <a
                          href={fsDownloadUrl(fullPath)}
                          download={file.name}
                          className="text-xs text-violet-400 hover:text-violet-300"
                        >Download</a>
                        <button
                          onClick={() => { setMoving({ path: fullPath, dest: fullPath }); setMoveErr(''); setConfirm(null) }}
                          className="text-xs text-slate-400 hover:text-violet-400 cursor-pointer"
                        >Move</button>
                        <button
                          onClick={() => { setConfirm({ path: fullPath, name: file.name, isDir: false }); setDeleteErr(''); setMoving(null) }}
                          className="text-xs text-slate-600 hover:text-red-400 cursor-pointer"
                        >Delete</button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
