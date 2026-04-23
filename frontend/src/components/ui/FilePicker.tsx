import { useState, useEffect } from 'react'
import { browsePath, getFsHome, fsMkdir } from '../../lib/api'
import type { FsFilter, FsBrowseResult } from '../../lib/api'
import { Modal } from './Modal'
import { Spinner } from './Spinner'
import { Button } from './Button'

interface Props {
  open: boolean
  onClose: () => void
  onSelect: (path: string) => void
  filter?: FsFilter
  /** If true the user picks a directory, not a file */
  dirOnly?: boolean
  title?: string
  initialPath?: string
}

const fileIcon = (name: string) => {
  const ext = name.split('.').pop()?.toLowerCase() ?? ''
  if (['pt', 'pth', 'onnx'].includes(ext)) return '🤖'
  if (['yaml', 'yml'].includes(ext)) return '📋'
  if (['json', 'annotatex'].includes(ext)) return '📦'
  if (['mp4', 'avi', 'mov', 'mkv', 'webm'].includes(ext)) return '🎥'
  return '📄'
}

export function FilePicker({ open, onClose, onSelect, filter = 'any', dirOnly = false, title, initialPath = '/' }: Props) {
  const [data, setData] = useState<FsBrowseResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [manualPath, setManualPath] = useState('')
  const [newFolderMode, setNewFolderMode] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [newFolderErr, setNewFolderErr] = useState('')
  const [newFolderLoading, setNewFolderLoading] = useState(false)

  const load = async (path: string) => {
    setLoading(true)
    setError('')
    try {
      const result = await browsePath(path, filter)
      setData(result)
      setManualPath(result.cwd)
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      const status = (e as { response?: { status?: number } }).response?.status
      if (!status) {
        setError('Cannot reach server. Make sure the VisionQ server is running.')
      } else {
        setError(detail ?? `Server error (${status})`)
      }
      // On failure, keep the path in the input so the user can correct it
      setManualPath(path)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!open) return
    if (initialPath && initialPath !== '/') {
      // If we have a real starting path, use it directly
      setManualPath(initialPath)
      load(initialPath)
    } else {
      // Ask the server for its home directory
      getFsHome()
        .then(({ home }) => { setManualPath(home); load(home) })
        .catch(() => { setManualPath('/'); load('/') })
    }
  }, [open])

  const navigate = (dir: string) => {
    if (!data) return
    load(data.cwd + '/' + dir)
  }

  const selectFile = (filename: string) => {
    if (!data) return
    onSelect(data.cwd + '/' + filename)
    onClose()
  }

  const selectCurrentDir = () => {
    if (!data) return
    onSelect(data.cwd)
    onClose()
  }

  const submitManual = () => {
    if (manualPath.trim()) load(manualPath.trim())
  }

  const createFolder = async () => {
    if (!data || !newFolderName.trim()) return
    setNewFolderLoading(true)
    setNewFolderErr('')
    try {
      const { path } = await fsMkdir(data.cwd, newFolderName.trim())
      setNewFolderMode(false)
      setNewFolderName('')
      await load(path) // navigate into the newly created folder
    } catch (e: unknown) {
      setNewFolderErr((e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Failed to create folder.')
    } finally {
      setNewFolderLoading(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={title ?? (dirOnly ? 'Select Folder' : 'Select File')} width="max-w-xl">
      <div className="flex flex-col gap-3">
        {/* Manual path input */}
        <div className="flex gap-2">
          <input
            value={manualPath}
            onChange={e => setManualPath(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') submitManual() }}
            className="flex-1 bg-[#0f172a] border border-[#334155] rounded px-3 py-1.5 text-sm text-slate-100
              placeholder:text-slate-600 focus:outline-none focus:border-violet-500 font-mono"
            placeholder="/path/to/folder"
          />
          <Button size="sm" variant="secondary" onClick={submitManual}>Go</Button>
        </div>

        {/* Breadcrumb */}
        {data && (
          <div className="flex items-center gap-0.5 text-xs flex-wrap font-mono">
            {data.cwd.split('/').filter((_, i, arr) => i < arr.length).map((segment, i, arr) => {
              const fullPath = arr.slice(0, i + 1).join('/') || '/'
              const isLast = i === arr.length - 1
              return (
                <span key={i} className="flex items-center gap-0.5">
                  {i > 0 && <span className="text-slate-600">/</span>}
                  {isLast ? (
                    <span className="text-slate-300">{segment || '/'}</span>
                  ) : (
                    <button
                      onClick={() => load(fullPath)}
                      className="text-violet-400 hover:text-violet-300 cursor-pointer hover:underline"
                    >
                      {segment || '/'}
                    </button>
                  )}
                </span>
              )
            })}
          </div>
        )}

        {/* New folder input */}
        {newFolderMode && data && (
          <div className="flex flex-col gap-1">
            <div className="flex gap-2">
              <input
                autoFocus
                value={newFolderName}
                onChange={e => { setNewFolderName(e.target.value); setNewFolderErr('') }}
                onKeyDown={e => { if (e.key === 'Enter') createFolder(); if (e.key === 'Escape') { setNewFolderMode(false); setNewFolderName('') } }}
                placeholder="New folder name"
                className="flex-1 bg-[#0f172a] border border-violet-600 rounded px-3 py-1.5 text-sm text-slate-100
                  placeholder:text-slate-600 focus:outline-none font-mono"
              />
              <Button size="sm" variant="primary" onClick={createFolder} disabled={!newFolderName.trim() || newFolderLoading}>
                {newFolderLoading ? <Spinner size={12} /> : 'Create'}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => { setNewFolderMode(false); setNewFolderName(''); setNewFolderErr('') }}>
                Cancel
              </Button>
            </div>
            {newFolderErr && <p className="text-xs text-red-400">{newFolderErr}</p>}
          </div>
        )}

        {/* File listing */}
        <div
          className="border border-[#1e293b] rounded-lg overflow-y-auto bg-[#0f172a]"
          style={{ minHeight: 240, maxHeight: 360 }}
        >
          {loading && (
            <div className="flex items-center justify-center h-40">
              <Spinner size={24} />
            </div>
          )}
          {error && (
            <div className="flex items-center justify-center h-40 text-sm text-red-400 px-4 text-center">
              {error}
            </div>
          )}
          {!loading && !error && data && (
            <>
              {data.dirs.length === 0 && data.files.length === 0 && (
                <div className="flex items-center justify-center h-40 text-sm text-slate-600">
                  Empty directory
                </div>
              )}

              {/* Dirs */}
              {data.dirs.map(dir => (
                <button
                  key={dir}
                  onClick={() => navigate(dir)}
                  className="w-full flex items-center gap-3 px-4 py-2 text-left hover:bg-[#1e293b] transition-colors cursor-pointer group"
                >
                  <span className="text-base shrink-0">📁</span>
                  <span className="flex-1 text-sm text-slate-200 truncate">{dir}</span>
                  {dirOnly && (
                    <button
                      onClick={e => { e.stopPropagation(); onSelect(data.cwd + '/' + dir); onClose() }}
                      className="opacity-0 group-hover:opacity-100 text-xs text-violet-400 hover:text-violet-300 shrink-0 cursor-pointer"
                    >
                      Select ›
                    </button>
                  )}
                </button>
              ))}

              {/* Files */}
              {!dirOnly && data.files.map(file => (
                <button
                  key={file}
                  onClick={() => selectFile(file)}
                  className="w-full flex items-center gap-3 px-4 py-2 text-left hover:bg-[#1e293b] transition-colors cursor-pointer"
                >
                  <span className="text-base shrink-0">{fileIcon(file)}</span>
                  <span className="flex-1 text-sm text-slate-300 truncate">{file}</span>
                  <span className="text-xs text-slate-600 shrink-0">
                    {file.split('.').pop()?.toUpperCase()}
                  </span>
                </button>
              ))}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between pt-1">
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-600">
              {data ? `${data.dirs.length} folders, ${data.files.length} files` : ''}
            </span>
            {data && !newFolderMode && (
              <button
                onClick={() => { setNewFolderMode(true); setNewFolderName('') }}
                className="text-xs text-violet-400 hover:text-violet-300 cursor-pointer flex items-center gap-1"
              >
                + New folder
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
            {dirOnly && data && (
              <Button variant="primary" size="sm" onClick={selectCurrentDir}>
                Select "{data.cwd.split('/').pop() || '/'}"
              </Button>
            )}
          </div>
        </div>
      </div>
    </Modal>
  )
}
