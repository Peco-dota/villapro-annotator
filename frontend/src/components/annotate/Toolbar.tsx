import { Button } from '../ui/Button'

interface Props {
  tool: 'draw' | 'select'
  onToolChange: (t: 'draw' | 'select') => void
  canUndo: boolean
  canRedo: boolean
  onUndo: () => void
  onRedo: () => void
  onSave: () => void
  onCopyPrev: () => void
  onPrev: () => void
  onNext: () => void
  onExport: () => void
  onTrain: () => void
  saving: boolean
  imageName: string | null
  imageIndex: number
  imageTotal: number
}

export function Toolbar(props: Props) {
  return (
    <div className="flex items-center gap-1.5 px-3 py-1.5 bg-[#17152a] border-b border-slate-800 flex-wrap">
      {/* Tool toggle */}
      <div className="flex rounded overflow-hidden border border-slate-700">
        <button
          onClick={() => props.onToolChange('select')}
          title="Select (V)"
          className={`px-2.5 py-1.5 text-xs transition-colors cursor-pointer ${props.tool === 'select' ? 'bg-violet-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M5 3l14 9-7 1-4 7z" />
          </svg>
        </button>
        <button
          onClick={() => props.onToolChange('draw')}
          title="Draw (D)"
          className={`px-2.5 py-1.5 text-xs transition-colors cursor-pointer ${props.tool === 'draw' ? 'bg-violet-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="18" height="18" rx="1" />
          </svg>
        </button>
      </div>

      <div className="w-px h-5 bg-slate-700" />

      <Button size="sm" variant="ghost" onClick={props.onUndo} disabled={!props.canUndo} title="Undo (Ctrl+Z)">↩</Button>
      <Button size="sm" variant="ghost" onClick={props.onRedo} disabled={!props.canRedo} title="Redo (Ctrl+Y)">↪</Button>

      <div className="w-px h-5 bg-slate-700" />

      <Button size="sm" variant="ghost" onClick={props.onPrev} title="Prev image (A)">‹ Prev</Button>
      <span className="text-xs text-slate-500">
        {props.imageIndex + 1} / {props.imageTotal}
      </span>
      <Button size="sm" variant="ghost" onClick={props.onNext} title="Next image (D)">Next ›</Button>

      <div className="w-px h-5 bg-slate-700" />

      <Button size="sm" variant="ghost" onClick={props.onCopyPrev} title="Copy boxes from previous image (C)">Copy prev</Button>

      <div className="flex-1" />

      <Button size="sm" variant="ghost" onClick={props.onExport}>Export</Button>
      <Button size="sm" variant="ghost" onClick={props.onTrain}>Train</Button>
      <Button size="sm" variant="primary" onClick={props.onSave} disabled={props.saving}>
        {props.saving ? 'Saving…' : 'Save'}
      </Button>
    </div>
  )
}
