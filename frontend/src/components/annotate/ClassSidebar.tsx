import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { addClass, deleteClass } from '../../lib/api'
import type { ClassDef, BoundingBox } from '../../lib/types'
import { Button } from '../ui/Button'

interface Props {
  classes: ClassDef[]
  boxes: BoundingBox[]
  selectedClass: number
  projectPath: string
  onSelectClass: (i: number) => void
}

export function ClassSidebar({ classes, boxes, selectedClass, projectPath, onSelectClass }: Props) {
  const qc = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [newName, setNewName] = useState('')

  const addMut = useMutation({
    mutationFn: () => addClass(projectPath, newName.trim()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project', projectPath] })
      setNewName('')
      setAdding(false)
    },
  })

  const delMut = useMutation({
    mutationFn: (index: number) => deleteClass(projectPath, index),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['project', projectPath] }),
  })

  const countFor = (i: number) => boxes.filter(b => b.class_index === i).length

  return (
    <div className="flex flex-col h-full bg-[#13111c] border-l border-slate-800 min-w-[180px]">
      <div className="px-3 py-2.5 border-b border-slate-800 flex items-center justify-between">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Classes</p>
        <button
          onClick={() => setAdding(v => !v)}
          className="text-xs text-violet-400 hover:text-violet-300 cursor-pointer"
        >+</button>
      </div>

      {adding && (
        <div className="px-3 py-2 border-b border-slate-800 flex gap-2">
          <input
            autoFocus
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && newName.trim()) addMut.mutate() }}
            placeholder="class name"
            className="flex-1 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-100 focus:outline-none focus:border-violet-500"
          />
          <Button size="sm" variant="primary" onClick={() => addMut.mutate()} disabled={!newName.trim()}>OK</Button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto py-1">
        {classes.map((cls, i) => (
          <button
            key={i}
            onClick={() => onSelectClass(i)}
            className={`w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors group cursor-pointer
              ${i === selectedClass ? 'bg-slate-800' : 'hover:bg-slate-800/50'}`}
          >
            <span
              className="w-3 h-3 rounded-sm shrink-0 ring-1 ring-white/10"
              style={{ background: cls.color }}
            />
            <span className="flex-1 text-xs text-slate-300 truncate">{cls.name}</span>
            <span className="text-xs text-slate-600 group-hover:text-slate-400">{countFor(i)}</span>
            <button
              onClick={e => { e.stopPropagation(); delMut.mutate(i) }}
              className="opacity-0 group-hover:opacity-100 text-slate-600 hover:text-red-400 text-sm leading-none cursor-pointer"
            >&times;</button>
          </button>
        ))}
      </div>
    </div>
  )
}
