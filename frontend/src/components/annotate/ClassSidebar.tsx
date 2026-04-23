import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { addClass } from '../../lib/api'
import type { ClassDef, BoundingBox } from '../../lib/types'

interface Props {
  classes: ClassDef[]
  boxes: BoundingBox[]
  selectedClass: number
  projectPath: string
  onSelectClass: (i: number) => void
  onSelectBox: (id: string) => void
  onDeleteBox: (id: string) => void
  selectedBoxId: string | null
}

const sectionHeader = (label: string) => (
  <div
    className="px-3 flex items-center shrink-0"
    style={{ height: 36, background: '#0f172a', borderBottom: '1px solid #1e293b' }}
  >
    <span className="text-[10px] font-bold text-[#64748b] uppercase tracking-widest">{label}</span>
  </div>
)

export function ClassSidebar({ classes, boxes, selectedClass, projectPath, onSelectClass, onSelectBox, onDeleteBox, selectedBoxId }: Props) {
  const qc = useQueryClient()
  const [newName, setNewName] = useState('')

  const addMut = useMutation({
    mutationFn: () => addClass(projectPath, newName.trim()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project', projectPath] })
      qc.invalidateQueries({ queryKey: ['classes', projectPath] })
      setNewName('')
    },
  })

  const countForCurrent = (i: number) => boxes.filter(b => b.class_index === i).length

  return (
    <div
      className="flex flex-col h-full bg-[#16213e] border-l border-[#1e293b] overflow-hidden"
      style={{ width: 220, minWidth: 220 }}
    >
      {/* ── CLASSES ── */}
      {sectionHeader('Classes')}

      {/* Add class input */}
      <div className="flex gap-1.5 px-2 py-2 border-b border-[#1e293b] shrink-0">
        <input
          value={newName}
          onChange={e => setNewName(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && newName.trim()) addMut.mutate() }}
          placeholder="New class name..."
          className="flex-1 bg-[#0f172a] border border-[#334155] rounded px-2 py-1 text-[11px] text-slate-100
            placeholder:text-slate-600 focus:outline-none focus:border-violet-600"
        />
        <button
          onClick={() => { if (newName.trim()) addMut.mutate() }}
          className="w-7 h-7 bg-violet-700 hover:bg-violet-600 text-white rounded text-base font-bold cursor-pointer flex items-center justify-center"
        >+</button>
      </div>
      <p className="text-[9px] text-[#334155] px-3 pb-1 shrink-0">Press 1–9 to select class</p>

      {/* Class list — fixed height like original */}
      <div className="overflow-y-auto shrink-0" style={{ maxHeight: 180 }}>
        {classes.map((cls, i) => {
          const active = i === selectedClass
          return (
            <button
              key={i}
              onClick={() => onSelectClass(i)}
              className={`w-full flex items-center gap-2 px-2 py-1.5 text-left cursor-pointer transition-colors
                ${active ? 'bg-[#1e1b4b]' : 'hover:bg-[#1a2744]'} rounded`}
            >
              <span
                className="w-5 h-5 rounded shrink-0 border border-[#475569]"
                style={{ background: cls.color }}
              />
              <span className="flex-1 text-[11px] text-slate-200 truncate">{cls.name}</span>
              <span className="text-[10px] text-[#64748b] min-w-4 text-right" title="Total annotations across all images">
                {cls.annotation_count ?? countForCurrent(i)}
              </span>
            </button>
          )
        })}
      </div>

      {/* Separator */}
      <div className="h-px bg-[#1e293b] shrink-0" />

      {/* ── ANNOTATIONS ── */}
      {sectionHeader('Annotations')}

      <div className="flex-1 overflow-y-auto">
        {boxes.length === 0 ? (
          <p className="text-[10px] text-[#334155] px-3 py-3">No boxes on this image</p>
        ) : (
          boxes.map((box) => {
            const cls = classes[box.class_index]
            const highlighted = box.id === selectedBoxId
            return (
              <button
                key={box.id}
                onClick={() => onSelectBox(box.id)}
                className={`w-full flex items-center gap-2 px-2 py-1.5 text-left cursor-pointer transition-colors
                  ${highlighted ? 'bg-[#1e1b4b]' : 'hover:bg-[#1a2744]'} rounded`}
              >
                <span
                  className="w-3 h-3 rounded-sm shrink-0"
                  style={{ background: cls?.color ?? '#7c3aed' }}
                />
                <span className="flex-1 text-[10px] text-slate-300 truncate">
                  {cls?.name ?? `class ${box.class_index}`}
                </span>
                <span className="text-[9px] text-[#475569] shrink-0">
                  cx:{box.cx.toFixed(2)} w:{box.w.toFixed(2)}
                </span>
                <button
                  onClick={e => { e.stopPropagation(); onDeleteBox(box.id) }}
                  className="text-[#ef4444] text-sm leading-none hover:opacity-100 opacity-60 cursor-pointer shrink-0"
                >×</button>
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}
