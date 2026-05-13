import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  startCounter, stopCounter, getCounterStatus, resetCounter, deleteCounter,
} from '../../lib/api'
import type { CountingConfig, CountingStatus } from '../../lib/types'
import { Spinner } from '../ui/Spinner'

interface Props {
  counter: CountingConfig
  onEdit: () => void
}

function DotState({ state }: { state: string }) {
  const colors: Record<string, string> = {
    running: 'bg-green-400',
    loading: 'bg-yellow-400 animate-pulse',
    error:   'bg-red-500',
    stopped: 'bg-slate-600',
  }
  return <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${colors[state] ?? colors.stopped}`} />
}

function Btn({ children, onClick, disabled, color, title }: {
  children: React.ReactNode; onClick: () => void; disabled?: boolean; color: string; title?: string
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`px-3 py-1 rounded text-xs font-medium cursor-pointer transition-colors disabled:opacity-40 disabled:cursor-not-allowed shrink-0 ${color}`}
    >
      {children}
    </button>
  )
}

function MenuItem({ icon, label, onClick, disabled, danger }: {
  icon: string; label: string; onClick: () => void; disabled?: boolean; danger?: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`w-full flex items-center gap-2.5 px-3 py-1.5 text-xs cursor-pointer transition-colors disabled:opacity-30 disabled:cursor-not-allowed
        ${danger ? 'text-red-400 hover:bg-red-900/20' : 'text-slate-300 hover:bg-slate-700/50'}`}
    >
      <span className="w-4 text-center">{icon}</span>
      {label}
    </button>
  )
}

export function CounterOnlyCard({ counter, onEdit }: Props) {
  const qc = useQueryClient()
  const [moreOpen, setMoreOpen] = useState(false)

  const { data: status } = useQuery<CountingStatus>({
    queryKey: ['counter-status', counter.name],
    queryFn: () => getCounterStatus(counter.name),
    refetchInterval: 2000,
  })

  const inv    = () => qc.invalidateQueries({ queryKey: ['counter-status', counter.name] })
  const invAll = () => {
    qc.invalidateQueries({ queryKey: ['counters'] })
    qc.invalidateQueries({ queryKey: ['counter-status', counter.name] })
  }

  const startMut = useMutation({ mutationFn: () => startCounter(counter.name), onSuccess: inv })
  const stopMut  = useMutation({ mutationFn: () => stopCounter(counter.name),  onSuccess: inv })
  const resetMut = useMutation({ mutationFn: () => resetCounter(counter.name), onSuccess: inv })
  const delMut   = useMutation({ mutationFn: () => deleteCounter(counter.name), onSuccess: invAll })

  const state   = status?.state ?? 'stopped'
  const running = state === 'running'
  const loading = state === 'loading'
  const stopped = state === 'stopped'
  const hasError = state === 'error'

  const statusText  = loading ? 'Loading' : running ? 'Running' : hasError ? 'Error' : 'Stopped'
  const statusColor = running ? 'text-green-400' : loading ? 'text-yellow-400' : hasError ? 'text-red-400' : 'text-slate-500'

  return (
    <div className="bg-[#16213e] border border-[#1e293b] rounded-xl">
      <div className="flex items-center gap-3 px-4 py-3">

        <DotState state={state} />

        <div className="flex items-center gap-2 shrink-0">
          <span className="text-sm font-bold text-slate-100 w-40 truncate">{counter.name}</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-teal-900/60 border border-teal-700/50 text-teal-300 shrink-0">
            Counter
          </span>
        </div>

        <div className="flex-1 min-w-0 flex items-center gap-1 text-xs text-slate-500 font-mono truncate">
          <span className="text-slate-600 shrink-0">source:</span>
          <span className="truncate">{counter.source_service}</span>
          {counter.auto_start && <span className="text-slate-600 shrink-0 ml-1" title="Auto-start">⟳</span>}
        </div>

        {running && (
          <span className="text-teal-300 font-bold font-mono shrink-0" title="Parking occupancy">
            🅿 {status?.count ?? 0}
          </span>
        )}

        <span className={`text-xs font-medium w-20 text-right shrink-0 ${statusColor}`}>{statusText}</span>

        {(stopped || hasError) && (
          <Btn color="bg-violet-700 hover:bg-violet-600 text-white"
            onClick={() => startMut.mutate()} disabled={startMut.isPending}>
            {startMut.isPending ? <Spinner size={11} /> : '▶  Start'}
          </Btn>
        )}
        {(running || loading) && (
          <Btn color="bg-red-700 hover:bg-red-600 text-white"
            onClick={() => stopMut.mutate()} disabled={stopMut.isPending}>
            {stopMut.isPending ? <Spinner size={11} /> : '■  Stop'}
          </Btn>
        )}

        {running && (
          <Btn
            color="bg-teal-900/60 border border-teal-700/50 text-teal-300 hover:bg-teal-800/60"
            onClick={() => resetMut.mutate()}
            disabled={resetMut.isPending}
            title="Reset parking counter to zero"
          >
            🅿 Reset
          </Btn>
        )}

        <div className="relative">
          <button
            onClick={() => setMoreOpen(v => !v)}
            className="w-8 h-8 flex items-center justify-center rounded text-slate-500 hover:text-slate-200 hover:bg-slate-700 cursor-pointer text-lg"
          >⋯</button>
          {moreOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setMoreOpen(false)} />
              <div className="absolute right-0 top-9 z-20 bg-[#1e293b] border border-[#334155] rounded-lg shadow-xl py-1 w-44">
                <MenuItem icon="✎" label="Edit config" disabled={running || loading}
                  onClick={() => { onEdit(); setMoreOpen(false) }} />
                <div className="h-px bg-[#334155] my-1" />
                <MenuItem icon="✕" label="Remove" danger
                  onClick={() => {
                    if (confirm(`Remove counter "${counter.name}"?`)) delMut.mutate()
                    setMoreOpen(false)
                  }} />
              </div>
            </>
          )}
        </div>
      </div>

      {hasError && (
        <div className="px-4 pb-2 text-xs text-red-400 font-mono">Service error — check server logs.</div>
      )}
    </div>
  )
}
