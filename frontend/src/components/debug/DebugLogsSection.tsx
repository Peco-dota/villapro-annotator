import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listDebugLogs, deleteDebugLog, getDebugLogDownloadUrl } from '../../lib/api'
import type { DebugLog } from '../../lib/api'
import { Spinner } from '../ui/Spinner'
import { Button } from '../ui/Button'

function fmtSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function fmtDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString()
}

function totalSize(logs: DebugLog[]): string {
  return fmtSize(logs.reduce((s, l) => s + l.size_bytes, 0))
}

function DeleteButton({ log, onDeleted }: { log: DebugLog; onDeleted: () => void }) {
  const [confirm, setConfirm] = useState(false)
  const mut = useMutation({
    mutationFn: () => deleteDebugLog(log.path),
    onSuccess: onDeleted,
  })

  if (confirm) {
    return (
      <span className="flex items-center gap-1">
        <button
          onClick={() => mut.mutate()}
          disabled={mut.isPending}
          className="text-xs text-red-400 hover:text-red-300 cursor-pointer font-medium"
        >
          {mut.isPending ? '…' : 'Confirm'}
        </button>
        <span className="text-slate-700">|</span>
        <button onClick={() => setConfirm(false)} className="text-xs text-slate-500 hover:text-slate-300 cursor-pointer">
          Cancel
        </button>
      </span>
    )
  }

  return (
    <button
      onClick={() => setConfirm(true)}
      className="text-xs text-slate-600 hover:text-red-400 cursor-pointer transition-colors"
      title="Delete debug log"
    >
      Delete
    </button>
  )
}

export function DebugLogsSection() {
  const queryClient = useQueryClient()

  const { data: logs = [], isLoading, refetch } = useQuery({
    queryKey: ['debug-logs'],
    queryFn: listDebugLogs,
    refetchInterval: 15000,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['debug-logs'] })

  const grouped = logs.reduce<Record<string, DebugLog[]>>((acc, l) => {
    ;(acc[l.service] ??= []).push(l)
    return acc
  }, {})

  const services = Object.keys(grouped).sort()

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Debug Logs</h2>
          {logs.length > 0 && (
            <p className="text-xs text-slate-500 mt-0.5">
              {logs.length} file{logs.length !== 1 ? 's' : ''} · {totalSize(logs)} total
            </p>
          )}
        </div>
        <Button variant="ghost" size="sm" onClick={() => refetch()}>Refresh</Button>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-slate-500 text-sm">
          <Spinner /> Loading debug logs…
        </div>
      )}

      {!isLoading && logs.length === 0 && (
        <div className="border border-dashed border-[#1e293b] rounded-xl p-12 text-center">
          <p className="text-slate-500 text-sm">No debug logs found.</p>
          <p className="text-slate-600 text-xs mt-1">
            Click <span className="font-mono text-slate-500">Debug</span> on a running service to start capturing a direction CSV.
          </p>
        </div>
      )}

      {services.map(service => (
        <div key={service} className="border border-[#1e293b] rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 bg-[#0f172a] border-b border-[#1e293b]">
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-violet-400" />
              <span className="text-sm font-medium text-slate-200">{service}</span>
              <span className="text-xs text-slate-600">
                {grouped[service].length} file{grouped[service].length !== 1 ? 's' : ''} · {totalSize(grouped[service])}
              </span>
            </div>
          </div>

          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e293b] bg-[#0a0f1e]">
                {['Filename', 'Size', 'Created', ''].map(h => (
                  <th key={h} className="px-4 py-2 text-left text-xs font-bold text-slate-600 uppercase tracking-wider">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grouped[service].map(log => (
                <tr key={log.path} className="border-b border-[#1e293b]/50 hover:bg-[#1e293b]/20 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-slate-300">{log.filename}</td>
                  <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">{fmtSize(log.size_bytes)}</td>
                  <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">{fmtDate(log.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3 justify-end">
                      <a
                        href={getDebugLogDownloadUrl(log.path)}
                        download={log.filename}
                        className="text-xs text-violet-400 hover:text-violet-300 transition-colors"
                      >
                        Download
                      </a>
                      <DeleteButton log={log} onDeleted={invalidate} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}
