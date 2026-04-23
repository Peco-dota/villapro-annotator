import { ReceiverDashboard } from '../components/detection/ReceiverDashboard'

export function ReceiverPage() {
  return (
    <div className="min-h-screen bg-[#0f172a]">
      <header className="flex items-center gap-3 px-6 py-3 border-b border-[#1e293b]">
        <div className="w-7 h-7 rounded-lg bg-violet-600/20 border border-violet-500/30 flex items-center justify-center">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="1.5">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
            <circle cx="12" cy="12" r="3"/>
          </svg>
        </div>
        <span className="text-sm font-semibold text-slate-100">VisionQ</span>
        <span className="text-slate-600 text-sm">—</span>
        <span className="text-sm text-slate-400">📡 Detection Results Receiver</span>
      </header>
      <ReceiverDashboard />
    </div>
  )
}
