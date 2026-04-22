import { type InputHTMLAttributes } from 'react'

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}

export function Input({ label, error, className = '', ...props }: Props) {
  return (
    <div className="flex flex-col gap-1">
      {label && <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">{label}</label>}
      <input
        className={`bg-slate-800 border border-slate-600 rounded px-3 py-2 text-sm text-slate-100
          placeholder:text-slate-500 focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500/40
          disabled:opacity-40 ${className}`}
        {...props}
      />
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  )
}
