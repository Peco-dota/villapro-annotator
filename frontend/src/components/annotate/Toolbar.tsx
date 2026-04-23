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
  onDetect: () => void
  saving: boolean
  imageName: string | null
  imageIndex: number
  imageTotal: number
  onGoHome: () => void
  zoom: number
  onZoomIn: () => void
  onZoomOut: () => void
  onZoomFit: () => void
  onZoom1to1: () => void
}

const iconBtn = (active = false) =>
  `w-[34px] h-[34px] flex items-center justify-center rounded text-sm transition-colors cursor-pointer
   border border-transparent
   ${active
     ? 'bg-[#1e1b4b] text-violet-400 border-violet-700'
     : 'bg-transparent text-slate-400 hover:bg-[#1e293b] hover:text-slate-100 hover:border-slate-700'}`

const groupLabel = 'text-[10px] text-[#334155] font-bold tracking-widest uppercase select-none'

const actionBtn = (color: string) =>
  `h-[34px] px-3.5 rounded text-xs font-bold text-white cursor-pointer transition-colors ${color}`

const vSep = 'w-px h-5 bg-[#1e293b] shrink-0'

export function Toolbar(props: Props) {
  return (
    <div className="flex items-center gap-1 px-3 h-[52px] bg-[#0f172a] border-b border-[#1e293b] shrink-0 overflow-x-auto">
      {/* Back */}
      <button className={iconBtn()} onClick={props.onGoHome} title="Back to Welcome">←</button>
      <div className={vSep} />

      {/* Logo */}
      <span className="text-violet-400 font-bold text-base tracking-wide px-2 shrink-0">◈ VisionQ</span>
      <div className={vSep} />

      {/* Tools */}
      <span className={groupLabel}>Tools</span>
      <button
        className={iconBtn(props.tool === 'select')}
        onClick={() => props.onToolChange('select')}
        title="Select / Move (V)"
      >⬚</button>
      <button
        className={iconBtn(props.tool === 'draw')}
        onClick={() => props.onToolChange('draw')}
        title="Draw Rectangle (R)"
      >⬜</button>
      <div className={vSep} />

      {/* Zoom */}
      <span className={groupLabel}>Zoom</span>
      <button className={iconBtn()} onClick={props.onZoomOut} title="Zoom Out (-)">－</button>
      <button className={iconBtn()} onClick={props.onZoomIn} title="Zoom In (+)">＋</button>
      <button className={iconBtn()} onClick={props.onZoomFit} title="Fit to Window (F)">⊡</button>
      <button className={`${iconBtn()} !w-[40px]`} onClick={props.onZoom1to1} title="100% actual pixels">1:1</button>
      <div className={vSep} />

      {/* Edit */}
      <span className={groupLabel}>Edit</span>
      <button className={iconBtn()} onClick={props.onUndo} disabled={!props.canUndo} title="Undo (Ctrl+Z)" style={{opacity: props.canUndo ? 1 : 0.35}}>
        <svg width="15" height="15" viewBox="0 0 15 15" fill="none"><path d="M4 4H9.5a3.5 3.5 0 0 1 0 7H5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/><path d="M6.5 2L4 4l2.5 2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>
      </button>
      <button className={iconBtn()} onClick={props.onRedo} disabled={!props.canRedo} title="Redo (Ctrl+Y)" style={{opacity: props.canRedo ? 1 : 0.35}}>
        <svg width="15" height="15" viewBox="0 0 15 15" fill="none"><path d="M11 4H5.5a3.5 3.5 0 0 0 0 7H10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/><path d="M8.5 2L11 4l-2.5 2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>
      </button>
      <div className={vSep} />

      {/* Navigation */}
      <button className={iconBtn()} onClick={props.onPrev} title="Previous Image (A / ←)">
        <svg width="10" height="12" viewBox="0 0 10 12" fill="currentColor"><path d="M9 1L1 6l8 5V1z"/></svg>
      </button>
      <button className={iconBtn()} onClick={props.onNext} title="Next Image (D / →)">
        <svg width="10" height="12" viewBox="0 0 10 12" fill="currentColor"><path d="M1 1l8 5-8 5V1z"/></svg>
      </button>

      {/* Copy prev */}
      <button
        className={`${iconBtn()} !w-auto px-2 text-[11px] shrink-0`}
        onClick={props.onCopyPrev}
        title="Copy boxes from previous image (C)"
      >Copy prev</button>

      <div className="flex-1 shrink-0 min-w-2" />

      {/* Save */}
      <button
        className={`${iconBtn()} !w-[42px]`}
        onClick={props.onSave}
        disabled={props.saving}
        title="Save Project (Ctrl+S)"
      >{props.saving ? '…' : '💾'}</button>

      {/* Action buttons */}
      <button className={actionBtn('bg-violet-700 hover:bg-violet-600')} onClick={props.onExport} title="Export Dataset">⬆ Export</button>
      <button className={actionBtn('bg-amber-700 hover:bg-amber-600')} onClick={props.onTrain} title="Train YOLO Model">▶ Train</button>
      <button className={actionBtn('bg-cyan-700 hover:bg-cyan-600')} onClick={props.onDetect} title="Service Manager">⚡ Service Manager</button>
    </div>
  )
}
