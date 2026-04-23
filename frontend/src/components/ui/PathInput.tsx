import { useState } from 'react'
import type { FsFilter } from '../../lib/api'
import { FilePicker } from './FilePicker'

interface Props {
  label?: string
  value: string
  onChange: (v: string) => void
  filter?: FsFilter
  dirOnly?: boolean
  placeholder?: string
  pickerTitle?: string
}

export function PathInput({ label, value, onChange, filter = 'any', dirOnly = false, placeholder, pickerTitle }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">{label}</label>
      )}
      <div className="flex gap-1">
        <input
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          className="flex-1 bg-slate-800 border border-slate-600 rounded px-3 py-2 text-sm text-slate-100
            placeholder:text-slate-500 focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500/40
            font-mono"
        />
        <button
          type="button"
          onClick={() => setOpen(true)}
          title="Browse server filesystem"
          className="px-2.5 py-1.5 bg-slate-700 hover:bg-slate-600 border border-slate-600 rounded text-slate-300
            hover:text-slate-100 text-sm transition-colors cursor-pointer shrink-0"
        >
          📂
        </button>
      </div>
      <FilePicker
        open={open}
        onClose={() => setOpen(false)}
        onSelect={onChange}
        filter={filter}
        dirOnly={dirOnly}
        title={pickerTitle}
        initialPath={value || ''}
      />
    </div>
  )
}
