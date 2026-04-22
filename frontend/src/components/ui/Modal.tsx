import { type ReactNode, useEffect } from 'react'

interface Props {
  open: boolean
  onClose: () => void
  title?: string
  children: ReactNode
  width?: string
}

export function Modal({ open, onClose, title, children, width = 'max-w-md' }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    if (open) document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className={`relative z-10 w-full ${width} mx-4 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl`}>
        {title && (
          <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700">
            <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
            <button onClick={onClose} className="text-slate-500 hover:text-slate-200 text-lg leading-none">&times;</button>
          </div>
        )}
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}
