import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { startService, stopService, deleteService, getServiceLog, getServiceStatus } from '../../lib/api'
import type { ServiceConfig, ServiceStatus } from '../../lib/types'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Badge'
import { Spinner } from '../ui/Spinner'

interface Props {
  service: ServiceConfig
  onEdit: () => void
}

export function ServiceCard({ service, onEdit }: Props) {
  const qc = useQueryClient()
  const [showLog, setShowLog] = useState(false)

  const { data: status } = useQuery<ServiceStatus>({
    queryKey: ['service-status', service.name],
    queryFn: () => getServiceStatus(service.name),
    refetchInterval: 2000,
  })

  const { data: log } = useQuery<{ lines: string[] }>({
    queryKey: ['service-log', service.name],
    queryFn: () => getServiceLog(service.name),
    enabled: showLog,
    refetchInterval: showLog ? 2000 : false,
  })

  const startMut = useMutation({
    mutationFn: () => startService(service.name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['service-status', service.name] }),
  })
  const stopMut = useMutation({
    mutationFn: () => stopService(service.name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['service-status', service.name] }),
  })
  const delMut = useMutation({
    mutationFn: () => deleteService(service.name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['services'] }),
  })

  const running = status?.running ?? false
  const direction = status?.direction ?? 'idle'
  const gateOpen = status?.gate_open ?? false

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3">
        <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${running ? 'bg-green-400 animate-pulse' : 'bg-slate-600'}`} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-100">{service.name}</p>
          <p className="text-xs text-slate-500 truncate">{service.mode} · {service.source || '(no source)'}</p>
        </div>

        <div className="flex items-center gap-2">
          {running && (
            <>
              <Badge className="bg-slate-700 text-slate-300">{direction}</Badge>
              {gateOpen && <Badge className="bg-green-900/50 text-green-300">GATE OPEN</Badge>}
              {status?.fps ? <span className="text-xs text-slate-500">{status.fps.toFixed(1)} fps</span> : null}
            </>
          )}

          <Button size="sm" variant="ghost" onClick={() => setShowLog(v => !v)}>
            {showLog ? 'Hide log' : 'Log'}
          </Button>
          <Button size="sm" variant="ghost" onClick={onEdit}>Edit</Button>

          {running ? (
            <Button size="sm" variant="danger" onClick={() => stopMut.mutate()} disabled={stopMut.isPending}>
              {stopMut.isPending ? <Spinner size={11} /> : null} Stop
            </Button>
          ) : (
            <Button size="sm" variant="primary" onClick={() => startMut.mutate()} disabled={startMut.isPending}>
              {startMut.isPending ? <Spinner size={11} /> : null} Start
            </Button>
          )}

          <button
            onClick={() => { if (confirm(`Delete service "${service.name}"?`)) delMut.mutate() }}
            className="text-slate-600 hover:text-red-400 text-lg leading-none cursor-pointer px-1"
            title="Delete"
          >&times;</button>
        </div>
      </div>

      {showLog && (
        <div className="border-t border-slate-800 bg-[#0c0a14] px-4 py-3 max-h-48 overflow-y-auto">
          {log?.lines?.length ? (
            <pre className="text-xs text-slate-400 whitespace-pre-wrap font-mono">
              {log.lines.join('\n')}
            </pre>
          ) : (
            <p className="text-xs text-slate-600">No log output</p>
          )}
        </div>
      )}
    </div>
  )
}
