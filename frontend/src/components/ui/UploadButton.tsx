import { useRef, useState } from 'react'
import { uploadFile } from '../../lib/api'
import type { FsFilter } from '../../lib/api'

const FILTER_ACCEPT: Partial<Record<FsFilter, string>> = {
  model: '.pt,.pth,.onnx',
  video: '.mp4,.avi,.mov,.mkv,.webm,.m4v',
  yaml:  '.yaml,.yml',
  project: '.json,.annotatex',
}

const FILTER_DIR: Partial<Record<FsFilter, string>> = {
  model: '/villapro-data/models',
  video: '/villapro-data/videos',
  yaml:  '/villapro-data',
}

interface Props {
  filter?: FsFilter
  /** Override the default destination directory derived from filter. */
  destDir?: string
  /** Called with the server path of the uploaded file. */
  onUploaded: (path: string) => void
}

export function UploadButton({ filter = 'any', destDir, onUploaded }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState('')

  const dest = destDir || FILTER_DIR[filter] || '/villapro-data'
  const accept = FILTER_ACCEPT[filter] ?? '*'

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setError('')
    setProgress(0)
    try {
      const result = await uploadFile(file, dest, setProgress)
      onUploaded(result.path)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail
      setError(detail ?? 'Upload failed')
    } finally {
      setProgress(null)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const uploading = progress !== null

  return (
    <div className="relative flex items-stretch">
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={handleChange}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        title="Upload file from your computer"
        className={`px-2.5 py-1.5 border rounded text-sm transition-colors cursor-pointer shrink-0
          ${uploading
            ? 'bg-violet-800 border-violet-600 text-violet-200 cursor-not-allowed'
            : 'bg-slate-700 hover:bg-slate-600 border-slate-600 text-slate-300 hover:text-slate-100'
          }`}
      >
        {uploading ? (
          <span className="font-mono text-xs">{progress}%</span>
        ) : (
          '↑'
        )}
      </button>
      {error && (
        <p className="absolute top-full left-0 mt-1 text-xs text-red-400 whitespace-nowrap z-10 bg-slate-900 px-2 py-1 rounded border border-red-900">
          {error}
        </p>
      )}
    </div>
  )
}
