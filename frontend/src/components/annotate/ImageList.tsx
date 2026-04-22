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
    <div className="flex flex-col h-full bg-[#13111c] border-r border-slate-800">
      <div className="px-3 py-2.5 border-b border-slate-800">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
          Images ({images.length})
        </p>
      </div>
      <div className="flex-1 overflow-y-auto">
        {images.map((img, i) => {
          const active = img.filename === current
          return (
            <button
              key={img.filename}
              onClick={() => onSelect(img.filename)}
              className={`w-full flex items-center gap-2.5 px-2 py-2 text-left transition-colors cursor-pointer
                border-b border-slate-800/50
                ${active
                  ? 'bg-violet-700/20 border-l-2 border-l-violet-500'
                  : 'hover:bg-slate-800/60 border-l-2 border-l-transparent'
                }`}
            >
              <span className="text-xs text-slate-600 w-5 text-right shrink-0">{i + 1}</span>
              <div className="w-10 h-10 rounded bg-slate-800 overflow-hidden shrink-0">
                <img
                  src={getImageFile(projectPath, img.filename)}
                  alt={img.filename}
                  className="w-full h-full object-cover"
                  loading="lazy"
                />
              </div>
              <div className="min-w-0 flex-1">
                <p className={`text-xs truncate ${active ? 'text-violet-200' : 'text-slate-300'}`}>
                  {img.filename}
                </p>
                {img.box_count > 0 && (
                  <span className="text-xs text-violet-400">{img.box_count} boxes</span>
                )}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
