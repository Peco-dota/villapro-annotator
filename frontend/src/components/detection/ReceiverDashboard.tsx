import { useEffect, useRef, useState } from 'react'
import { sseUrl, api, clearAllResults, getServices } from '../../lib/api'

interface DetectionPayload {
  service_name: string
  car?: { detected: boolean; direction: string; confidence: number }
  car_rear?: { detected: boolean; direction: string; confidence: number }
  gate?: { open: boolean }
  frames_analyzed?: number
  timestamp?: string
}

interface ServiceResults {
  name: string
  results: DetectionPayload[]
  lastSeen: number
  totalReports: number
  carCount: number
  rearCount: number
}

const DIR_COLOR: Record<string, string> = {
  forward:  'text-blue-400',
  backward: 'text-orange-400',
  idle:     'text-yellow-400',
  no_car:   'text-slate-500',
  building: 'text-slate-500',
}

function dirLabel(d: string | undefined, conf: number | undefined, detected: boolean | undefined) {
  if (!d) return <span className="text-slate-700">—</span>
  if (d === 'no_car' || !detected) return <span className="text-slate-600">no_car</span>
  return (
    <span className={DIR_COLOR[d] ?? 'text-slate-400'}>
      {d}{conf ? ` ${(conf * 100).toFixed(0)}%` : ''}
    </span>
  )
}

function StatusBadge({ isRunning, exists }: { isRunning: boolean; exists: boolean }) {
  if (isRunning) return (
    <span className="flex items-center gap-1.5 text-xs font-medium text-green-400">
      <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse shrink-0" />
      Live
    </span>
  )
  if (!exists) return (
    <span className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
      <span className="w-1.5 h-1.5 rounded-full bg-slate-600 shrink-0" />
      Deleted
    </span>
  )
  return (
    <span className="flex items-center gap-1.5 text-xs font-medium text-amber-500">
      <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" />
      Stopped
    </span>
  )
}

function ServicePanel({ data, isRunning, exists }: { data: ServiceResults; isRunning: boolean; exists: boolean }) {
  const lastDir = data.results[0]?.car?.direction
  const hasResults = data.results.length > 0

  return (
    <div className={`bg-[#16213e] border rounded-xl overflow-hidden flex flex-col
      ${!exists ? 'border-slate-700/50 opacity-75' : 'border-[#1e293b]'}`}
      style={{ minWidth: 480 }}>
      {/* Panel header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e293b]">
        <div className="flex items-center gap-2">
          <span className={`text-sm font-bold ${exists ? 'text-violet-300' : 'text-slate-500'}`}>{data.name}</span>
          {!exists && (
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-600 bg-slate-800 px-1.5 py-0.5 rounded">removed</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge isRunning={isRunning} exists={exists} />
          {hasResults && (
            <span className="text-xs text-slate-600">
              {isRunning ? new Date(data.lastSeen).toLocaleTimeString() : `Last: ${new Date(data.lastSeen).toLocaleTimeString()}`}
            </span>
          )}
        </div>
      </div>

      {/* Stats row */}
      <div className="flex gap-6 px-4 py-2 border-b border-[#1e293b] bg-[#0f172a]/40">
        {[
          { label: 'Total Reports', value: data.totalReports },
          { label: 'Car', value: data.carCount },
          { label: 'Car rear', value: data.rearCount },
        ].map(({ label, value }) => (
          <div key={label} className="flex flex-col">
            <span className="text-lg font-bold text-violet-400 leading-tight">{value}</span>
            <span className="text-[10px] text-slate-600">{label}</span>
          </div>
        ))}
        {lastDir && (
          <div className="flex flex-col">
            <span className={`text-lg font-bold leading-tight ${DIR_COLOR[lastDir] ?? 'text-slate-400'}`}>{lastDir}</span>
            <span className="text-[10px] text-slate-600">Last dir</span>
          </div>
        )}
      </div>

      {/* Results table */}
      <div className="overflow-y-auto" style={{ maxHeight: 240 }}>
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[#1e293b]">
              {['TIME', 'GATE', 'CAR', 'CAR DIR', 'REAR', 'REAR DIR'].map(h => (
                <th key={h} className="px-3 py-1.5 text-left text-[10px] font-bold text-slate-600 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.results.slice(0, 50).map((r, i) => {
              const gateOpen = r.gate?.open
              const carDet = r.car?.detected
              const rearDet = r.car_rear?.detected
              return (
                <tr key={i} className={`border-b border-[#1e293b]/50 ${gateOpen ? 'bg-green-900/10' : ''}`}>
                  <td className="px-3 py-1.5 text-slate-600 font-mono">{r.timestamp ?? '—'}</td>
                  <td className="px-3 py-1.5">
                    {gateOpen
                      ? <span className="text-green-400 font-bold">▲ OPEN</span>
                      : <span className="text-slate-700">—</span>}
                  </td>
                  <td className="px-3 py-1.5">
                    {carDet
                      ? <span className="text-green-400">● CAR</span>
                      : <span className="text-slate-700">○ —</span>}
                  </td>
                  <td className="px-3 py-1.5">{dirLabel(r.car?.direction, r.car?.confidence, carDet)}</td>
                  <td className="px-3 py-1.5">
                    {rearDet
                      ? <span className="text-green-400">● REAR</span>
                      : <span className="text-slate-700">○ —</span>}
                  </td>
                  <td className="px-3 py-1.5">{dirLabel(r.car_rear?.direction, r.car_rear?.confidence, rearDet)}</td>
                </tr>
              )
            })}
            {data.results.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-slate-600">No results yet</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ReceiverDashboard() {
  const [panels, setPanels] = useState<Record<string, ServiceResults>>({})
  const [runningSet, setRunningSet] = useState<Set<string>>(new Set())
  const [existingSet, setExistingSet] = useState<Set<string>>(new Set())
  const esRefs = useRef<Map<string, EventSource>>(new Map())

  // Subscribe to all services via SSE + poll buffered results on mount
  useEffect(() => {
    // Poll the buffer for historical results
    api.get('/api/detection/results/all').then(r => {
      const buf = r.data as Record<string, DetectionPayload[]>
      setPanels(prev => {
        const next = { ...prev }
        for (const [name, results] of Object.entries(buf)) {
          const existing = next[name]
          next[name] = {
            name,
            results: results,
            lastSeen: existing?.lastSeen ?? (results.length ? Date.now() : 0),
            totalReports: results.length,
            carCount: results.filter(r => r.car?.detected).length,
            rearCount: results.filter(r => r.car_rear?.detected).length,
          }
        }
        return next
      })
    }).catch(() => {})
  }, [])

  // Subscribe to live SSE per service as panels appear
  const subscribeToService = (name: string) => {
    if (esRefs.current.has(name)) return
    const url = sseUrl(`/api/detection/services/${name}/stream`)
    const es = new EventSource(url)
    esRefs.current.set(name, es)
    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data) as DetectionPayload
        setPanels(prev => {
          const existing = prev[name] ?? { name, results: [], lastSeen: 0, totalReports: 0, carCount: 0, rearCount: 0 }
          const newResults = [payload, ...existing.results].slice(0, 100)
          return {
            ...prev,
            [name]: {
              name,
              results: newResults,
              lastSeen: Date.now(),
              totalReports: existing.totalReports + 1,
              carCount: existing.carCount + (payload.car?.detected ? 1 : 0),
              rearCount: existing.rearCount + (payload.car_rear?.detected ? 1 : 0),
            },
          }
        })
      } catch { /* ignore */ }
    }
  }

  // Poll running service status — drives the live indicator
  useEffect(() => {
    const update = () => {
      getServices().then((svcs: { name: string; state: string }[]) => {
        setRunningSet(new Set(svcs.filter(s => s.state === 'running').map(s => s.name)))
        setExistingSet(new Set(svcs.map(s => s.name)))
      }).catch(() => {})
    }
    update()
    const id = setInterval(update, 3000)
    return () => clearInterval(id)
  }, [])

  // Poll /results/all every 2s — discovers new services AND refreshes panel data
  useEffect(() => {
    const id = setInterval(() => {
      api.get('/api/detection/results/all').then(r => {
        const buf = r.data as Record<string, DetectionPayload[]>
        setPanels(prev => {
          const next = { ...prev }
          for (const [name, results] of Object.entries(buf)) {
            if (!results.length) continue
            subscribeToService(name)
            const existing = next[name]
            // Only update if the buffer has more/newer results than what SSE gave us
            const bufNewer = !existing || results.length > existing.results.length ||
              (results[0]?.timestamp && results[0].timestamp !== existing.results[0]?.timestamp)
            if (bufNewer) {
              next[name] = {
                name,
                results,
                lastSeen: existing?.lastSeen ?? 0,
                totalReports: Math.max(existing?.totalReports ?? 0, results.length),
                carCount: results.filter(r => r.car?.detected).length,
                rearCount: results.filter(r => r.car_rear?.detected).length,
              }
            }
          }
          return next
        })
      }).catch(() => {})
    }, 2000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    return () => {
      for (const es of esRefs.current.values()) es.close()
    }
  }, [])

  // Subscribe to any panel that appears — inside an effect to avoid side effects during render
  useEffect(() => {
    for (const name of Object.keys(panels)) subscribeToService(name)
  })

  const panelList = Object.values(panels)

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-100">📡 Detection Results Receiver</h2>
          <p className="text-xs text-slate-600 mt-0.5">
            Services POST results to <span className="font-mono text-slate-500">/api/detection/results</span>.
            Results appear here in real-time.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${panelList.some(p => runningSet.has(p.name)) ? 'bg-green-400 animate-pulse' : 'bg-slate-600'}`} />
          <span className="text-xs text-slate-500">{panelList.length} service{panelList.length !== 1 ? 's' : ''}</span>
          {panelList.length > 0 && (
            <button
              onClick={() => {
                clearAllResults().catch(() => {})
                setPanels({})
                for (const es of esRefs.current.values()) es.close()
                esRefs.current.clear()
              }}
              className="text-xs text-slate-600 hover:text-red-400 cursor-pointer ml-2"
            >Clear all</button>
          )}
        </div>
      </div>

      {panelList.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center gap-3">
          <div className="text-4xl opacity-20">📡</div>
          <p className="text-slate-500 text-sm">No services have reported yet</p>
          <p className="text-slate-600 text-xs">Start a detection service and results will appear here automatically.</p>
        </div>
      ) : (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(480px, 1fr))' }}>
          {panelList.map(data => (
            <ServicePanel key={data.name} data={data} isRunning={runningSet.has(data.name)} exists={existingSet.has(data.name)} />
          ))}
        </div>
      )}
    </div>
  )
}
