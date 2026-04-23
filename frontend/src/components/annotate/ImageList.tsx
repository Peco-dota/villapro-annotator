import type { ImageEntry } from '../../lib/types'
import { getImageFile } from '../../lib/api'

interface Props {
  images: ImageEntry[]
  current: string | null
  projectPath: string
  onSelect: (filename: string) => void
}

export function ImageList({ images, current, projectPath, onSelect }: Props) {
  return (
    <div className="flex flex-col h-full bg-[#16213e] border-r border-[#1e293b]" style={{ width: 200, minWidth: 200 }}>
      <div
        className="px-3 flex items-center shrink-0"
        style={{ height: 36, background: '#0f172a', borderBottom: '1px solid #1e293b' }}
      >
        <span className="text-[10px] font-bold text-[#64748b] uppercase tracking-widest">
          Images ({images.length})
        </span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {images.map((img, i) => {
          const active = img.filename === current
          return (
            <button
              key={img.filename}
              onClick={() => onSelect(img.filename)}
              style={{ height: 100 }}
              className={`w-full flex items-center gap-2 px-1.5 py-1 text-left transition-colors cursor-pointer
                border-b border-[#0f172a]
                ${active ? 'bg-[#1e1b4b] border border-violet-700/50' : 'hover:bg-[#1a2744] border border-transparent'}`}
            >
              {/* Status bar */}
              <div
                className="w-1 self-stretch rounded-sm shrink-0"
                style={{ background: img.box_count > 0 ? '#22c55e' : '#475569' }}
              />

              {/* Thumbnail */}
              <div className="w-20 h-20 rounded shrink-0 overflow-hidden bg-[#1e293b] border border-[#334155]">
                <img
                  src={getImageFile(projectPath, img.filename)}
                  alt={img.filename}
                  className="w-full h-full object-cover"
                  loading="lazy"
                />
              </div>

              {/* Info */}
              <div className="min-w-0 flex flex-col gap-0.5">
                <span className={`text-[11px] truncate leading-tight ${active ? 'text-slate-100' : 'text-slate-300'}`}>
                  {img.filename.length > 20 ? '…' + img.filename.slice(-17) : img.filename}
                </span>
                <span className="text-[10px] text-[#64748b]">#{i + 1}</span>
                <span
                  className="text-[10px] px-1.5 py-px rounded-full inline-block w-fit"
                  style={img.box_count > 0
                    ? { color: '#22c55e', background: '#052e16' }
                    : { color: '#94a3b8', background: '#1e293b' }
                  }
                >
                  {img.box_count} box{img.box_count !== 1 ? 'es' : ''}
                </span>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
