import { useEffect, useRef, useState } from 'react'
import { sseUrl } from '../../lib/api'
import type { DetectionResult, ServiceConfig } from '../../lib/types'
import { Badge } from '../ui/Badge'

interface Props { service: ServiceConfig }

export function LiveDashboard({ service }: Props) {
  const [results, setResults] = useState<DetectionResult[]>([])
  const [connected, setConnected] = useState(false)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    const url = sseUrl(`/api/detection/services/${service.name}/stream`)
    const es = new EventSource(url)
    esRef.current = es
    es.onopen = () => setConnected(true)
    es.onerror = () => setConnected(false)
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as DetectionResult
        setResults(prev => [data, ...prev].slice(0, 100))
      } catch { /* ignore */ }
    }
    return () => { es.close(); esRef.current = null; setConnected(false) }
  }, [service.name])

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800">
        <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400 animate-pulse' : 'bg-slate-600'}`} />
        <span className="text-sm font-medium text-slate-200">Live: {service.name}</span>
        <span className="text-xs text-slate-500 ml-auto">{results.length} events</span>
      </div>

      <div className="max-h-72 overflow-y-auto">
        {results.length === 0 ? (
          <div className="px-4 py-6 text-center text-xs text-slate-600">
            {connected ? 'Waiting for detections…' : 'Connecting…'}
          </div>
        ) : results.map((r, i) => (
          <div key={i} className="flex items-start gap-3 px-4 py-2.5 border-b border-slate-800/50 text-xs">
            <span className="text-slate-600 w-20 shrink-0">
              {new Date(r.timestamp * 1000).toLocaleTimeString()}
            </span>
            <div className="flex flex-wrap gap-1 flex-1">
              {r.boxes.map((b, j) => (
                <Badge key={j} className="bg-violet-900/40 text-violet-300">
                  {b.class_name} {(b.confidence * 100).toFixed(0)}%
                </Badge>
              ))}
              {r.boxes.length === 0 && <span className="text-slate-600">no detections</span>}
            </div>
            <div className="flex gap-2 shrink-0">
              <span className="text-slate-500">{r.direction}</span>
              {r.gate_open && <Badge className="bg-green-900/40 text-green-300">GATE</Badge>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
