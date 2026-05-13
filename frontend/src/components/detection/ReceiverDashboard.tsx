import { useEffect, useRef, useState } from 'react'
import { sseUrl, api, clearAllResults, getServices, counterSseUrl } from '../../lib/api'
import type { CountingResult } from '../../lib/types'

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

interface CounterPanelData {
  name: string
  counterName: string
  events: CountingResult[]
  currentCount: number
  totalIn: number
  totalOut: number
  lastSeen: number
}

interface DetCounterInfo {
  currentCount: number
  totalIn: number
  totalOut: number
  lastSeen: number
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

// ── Detection service panel ───────────────────────────────────────────────────

function ServicePanel({ data, isRunning, exists, counterInfo }: { data: ServiceResults; isRunning: boolean; exists: boolean; counterInfo?: DetCounterInfo }) {
  const lastDir = data.results[0]?.car?.direction
  const hasResults = data.results.length > 0

  return (
    <div className={`bg-[#16213e] border rounded-xl overflow-hidden flex flex-col
      ${!exists ? 'border-slate-700/50 opacity-75' : 'border-[#1e293b]'}`}
      style={{ minWidth: 480 }}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e293b]">
        <div className="flex items-center gap-2">
          <span className={`text-sm font-bold ${exists ? 'text-violet-300' : 'text-slate-500'}`}>{data.name}</span>
          {counterInfo && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-teal-900/60 border border-teal-700/50 text-teal-300">Detection + Counter</span>
          )}
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

      {/* Parking counter strip (when service has an associated counter) */}
      {counterInfo && (
        <div className="flex items-center gap-5 px-4 py-2 border-b border-[#1e293b] bg-teal-900/10">
          <div className="flex items-center gap-1.5">
            <div className={`w-1.5 h-1.5 rounded-full ${Date.now() - counterInfo.lastSeen < 10000 ? 'bg-teal-400 animate-pulse' : 'bg-slate-600'}`} />
            <span className="text-[10px] text-slate-500 font-medium">🅿 Parking</span>
          </div>
          <span className="text-2xl font-bold text-teal-300 leading-tight">{counterInfo.currentCount}</span>
          <span className="text-sm font-bold text-green-400">+{counterInfo.totalIn} in</span>
          <span className="text-sm font-bold text-orange-400">−{counterInfo.totalOut} out</span>
        </div>
      )}

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
                    {gateOpen ? <span className="text-green-400 font-bold">▲ OPEN</span> : <span className="text-slate-700">—</span>}
                  </td>
                  <td className="px-3 py-1.5">
                    {carDet ? <span className="text-green-400">● CAR</span> : <span className="text-slate-700">○ —</span>}
                  </td>
                  <td className="px-3 py-1.5">{dirLabel(r.car?.direction, r.car?.confidence, carDet)}</td>
                  <td className="px-3 py-1.5">
                    {rearDet ? <span className="text-green-400">● REAR</span> : <span className="text-slate-700">○ —</span>}
                  </td>
                  <td className="px-3 py-1.5">{dirLabel(r.car_rear?.direction, r.car_rear?.confidence, rearDet)}</td>
                </tr>
              )
            })}
            {data.results.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-slate-600">No results yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Counter service panel ─────────────────────────────────────────────────────

function CounterServicePanel({ data, isRunning, exists }: { data: CounterPanelData; isRunning: boolean; exists: boolean }) {
  const hasEvents = data.events.length > 0

  return (
    <div className={`bg-[#16213e] border rounded-xl overflow-hidden flex flex-col
      ${!exists ? 'border-slate-700/50 opacity-75' : 'border-teal-800/40'}`}
      style={{ minWidth: 480 }}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e293b]">
        <div className="flex items-center gap-2">
          <span className={`text-sm font-bold ${exists ? 'text-teal-200' : 'text-slate-500'}`}>{data.name}</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-teal-900/60 border border-teal-700/50 text-teal-300">Counter</span>
          {!exists && (
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-600 bg-slate-800 px-1.5 py-0.5 rounded">removed</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge isRunning={isRunning} exists={exists} />
          {hasEvents && (
            <span className="text-xs text-slate-600">{new Date(data.lastSeen).toLocaleTimeString()}</span>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="flex items-center gap-8 px-4 py-3 border-b border-[#1e293b] bg-[#0f172a]/40">
        <div className="flex flex-col items-center">
          <span className="text-2xl font-bold text-teal-300 leading-tight">{data.currentCount}</span>
          <span className="text-[10px] text-slate-500 mt-0.5">🅿 Current</span>
        </div>
        <div className="w-px h-8 bg-slate-800" />
        <div className="flex flex-col items-center">
          <span className="text-xl font-bold text-green-400 leading-tight">+{data.totalIn}</span>
          <span className="text-[10px] text-slate-600 mt-0.5">Entered</span>
        </div>
        <div className="flex flex-col items-center">
          <span className="text-xl font-bold text-orange-400 leading-tight">−{data.totalOut}</span>
          <span className="text-[10px] text-slate-600 mt-0.5">Exited</span>
        </div>
      </div>

      {/* Event log */}
      <div className="overflow-y-auto" style={{ maxHeight: 240 }}>
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[#1e293b]">
              {['TIME', 'EVENT', 'CLASS', 'CHANGE', 'COUNT'].map(h => (
                <th key={h} className="px-3 py-1.5 text-left text-[10px] font-bold text-slate-600 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.events.slice(0, 50).map((e, i) => (
              <tr key={i} className={`border-b border-[#1e293b]/50 ${e.change > 0 ? 'bg-green-900/10' : 'bg-orange-900/10'}`}>
                <td className="px-3 py-1.5 text-slate-600 font-mono">
                  {e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : '—'}
                </td>
                <td className="px-3 py-1.5">
                  {e.change > 0
                    ? <span className="text-green-400 font-bold">↑ IN</span>
                    : <span className="text-orange-400 font-bold">↓ OUT</span>}
                </td>
                <td className="px-3 py-1.5 text-slate-400 font-mono">{e.trigger_class}</td>
                <td className="px-3 py-1.5">
                  <span className={e.change > 0 ? 'text-green-400 font-bold' : 'text-orange-400 font-bold'}>
                    {e.change > 0 ? `+${e.change}` : e.change}
                  </span>
                </td>
                <td className="px-3 py-1.5 text-teal-300 font-bold font-mono">{e.count}</td>
              </tr>
            ))}
            {data.events.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-6 text-center text-slate-600">No counting events yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Main dashboard ────────────────────────────────────────────────────────────

export function ReceiverDashboard() {
  const [panels, setPanels] = useState<Record<string, ServiceResults>>({})
  const [counterPanels, setCounterPanels] = useState<Record<string, CounterPanelData>>({})
  const [detCounterData, setDetCounterData] = useState<Record<string, DetCounterInfo>>({})
  const [runningSet, setRunningSet] = useState<Set<string>>(new Set())
  const [existingSet, setExistingSet] = useState<Set<string>>(new Set())
  const [counterKindSet, setCounterKindSet] = useState<Set<string>>(new Set())
  const esRefs = useRef<Map<string, EventSource>>(new Map())
  const counterEsRefs = useRef<Map<string, EventSource>>(new Map())
  const detCounterEsRefs = useRef<Map<string, EventSource>>(new Map())
  // Refs for use in intervals to avoid stale closures
  const panelsRef = useRef(panels)
  const counterKindSetRef = useRef(counterKindSet)
  useEffect(() => { panelsRef.current = panels }, [panels])
  useEffect(() => { counterKindSetRef.current = counterKindSet }, [counterKindSet])

  useEffect(() => {
    api.get('/api/detection/results/all').then(r => {
      const buf = r.data as Record<string, DetectionPayload[]>
      setPanels(prev => {
        const next = { ...prev }
        for (const [name, results] of Object.entries(buf)) {
          const existing = next[name]
          next[name] = {
            name, results,
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

  const subscribeToService = (name: string) => {
    if (esRefs.current.has(name)) return
    const es = new EventSource(sseUrl(`/api/detection/services/${name}/stream`))
    esRefs.current.set(name, es)
    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data) as DetectionPayload
        setPanels(prev => {
          const existing = prev[name] ?? { name, results: [], lastSeen: 0, totalReports: 0, carCount: 0, rearCount: 0 }
          return {
            ...prev,
            [name]: {
              name,
              results: [payload, ...existing.results].slice(0, 100),
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

  const subscribeToCounter = (serviceName: string, counterName: string) => {
    if (counterEsRefs.current.has(counterName)) return
    const es = new EventSource(counterSseUrl(counterName))
    counterEsRefs.current.set(counterName, es)
    es.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data) as CountingResult
        if (evt.event !== 'car_passed') return
        setCounterPanels(prev => {
          const existing = prev[serviceName] ?? { name: serviceName, counterName, events: [], currentCount: 0, totalIn: 0, totalOut: 0, lastSeen: 0 }
          return {
            ...prev,
            [serviceName]: {
              ...existing,
              events: [evt, ...existing.events].slice(0, 100),
              currentCount: evt.count,
              totalIn:  existing.totalIn  + (evt.change > 0 ? 1 : 0),
              totalOut: existing.totalOut + (evt.change < 0 ? 1 : 0),
              lastSeen: Date.now(),
            },
          }
        })
      } catch { /* ignore */ }
    }
  }

  const subscribeToDetCounter = (serviceName: string, counterName: string) => {
    if (detCounterEsRefs.current.has(counterName)) return
    const es = new EventSource(counterSseUrl(counterName))
    detCounterEsRefs.current.set(counterName, es)
    es.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data) as CountingResult
        if (evt.event !== 'car_passed') return
        setDetCounterData(prev => ({
          ...prev,
          [serviceName]: {
            currentCount: evt.count,
            totalIn:  (prev[serviceName]?.totalIn  ?? 0) + (evt.change > 0 ? 1 : 0),
            totalOut: (prev[serviceName]?.totalOut ?? 0) + (evt.change < 0 ? 1 : 0),
            lastSeen: Date.now(),
          },
        }))
      } catch { /* ignore */ }
    }
  }

  // Poll service list — running state + kind detection
  useEffect(() => {
    const update = () => {
      getServices().then((svcs: { name: string; state: string; kind?: string }[]) => {
        setRunningSet(new Set(svcs.filter(s => s.state === 'running').map(s => s.name)))
        setExistingSet(new Set(svcs.map(s => s.name)))
        setCounterKindSet(new Set(svcs.filter(s => s.kind === 'counter').map(s => s.name)))
      }).catch(() => {})
    }
    update()
    const id = setInterval(update, 3000)
    return () => clearInterval(id)
  }, [])

  // Poll detection results every 2s
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
            const bufNewer = !existing || results.length > existing.results.length ||
              (results[0]?.timestamp && results[0].timestamp !== existing.results[0]?.timestamp)
            if (bufNewer) {
              next[name] = {
                name, results,
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

  // Poll counting results every 2s for counter-kind services
  useEffect(() => {
    if (counterKindSet.size === 0) return
    const id = setInterval(() => {
      api.get('/api/counting/results/all').then(r => {
        const buf = r.data as Record<string, CountingResult[]>
        for (const serviceName of counterKindSet) {
          const counterName = `${serviceName}_counter`
          subscribeToCounter(serviceName, counterName)
          const evts = (buf[counterName] ?? []).filter(e => e.event === 'car_passed')
          if (!evts.length) continue
          setCounterPanels(prev => {
            const existing = prev[serviceName]
            if (existing && existing.events.length >= evts.length) return prev
            return {
              ...prev,
              [serviceName]: {
                name: serviceName,
                counterName,
                events: evts,
                currentCount: evts[0]?.count ?? 0,
                totalIn:  evts.filter(e => e.change > 0).length,
                totalOut: evts.filter(e => e.change < 0).length,
                lastSeen: Date.now(),
              },
            }
          })
        }
      }).catch(() => {})
    }, 2000)
    return () => clearInterval(id)
  }, [counterKindSet])

  // Poll counting results for detection+counter services (runs once, uses refs)
  useEffect(() => {
    const id = setInterval(() => {
      const pnls = panelsRef.current
      const ckSet = counterKindSetRef.current
      const detNames = Object.keys(pnls).filter(n => !ckSet.has(n))
      if (!detNames.length) return
      api.get('/api/counting/results/all').then(r => {
        const buf = r.data as Record<string, CountingResult[]>
        for (const serviceName of detNames) {
          const counterName = `${serviceName}_counter`
          const evts = (buf[counterName] ?? []).filter(e => e.event === 'car_passed')
          if (!evts.length) continue
          subscribeToDetCounter(serviceName, counterName)
          setDetCounterData(prev => {
            const existing = prev[serviceName]
            if (existing && evts[0]?.count === existing.currentCount && evts.length <= (existing.totalIn + existing.totalOut)) return prev
            return {
              ...prev,
              [serviceName]: {
                currentCount: evts[0]?.count ?? 0,
                totalIn:  evts.filter(e => e.change > 0).length,
                totalOut: evts.filter(e => e.change < 0).length,
                lastSeen: existing?.lastSeen ?? Date.now(),
              },
            }
          })
        }
      }).catch(() => {})
    }, 2000)
    return () => clearInterval(id)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    for (const name of Object.keys(panels)) subscribeToService(name)
  })

  useEffect(() => {
    return () => {
      for (const es of esRefs.current.values()) es.close()
      for (const es of counterEsRefs.current.values()) es.close()
      for (const es of detCounterEsRefs.current.values()) es.close()
    }
  }, [])

  const detectionPanels = Object.values(panels).filter(p => !counterKindSet.has(p.name))
  const counterServicePanels = Object.values(panels)
    .filter(p => counterKindSet.has(p.name))
    .map(p => counterPanels[p.name] ?? { name: p.name, counterName: `${p.name}_counter`, events: [], currentCount: 0, totalIn: 0, totalOut: 0, lastSeen: 0 })

  const totalPanels = detectionPanels.length + counterServicePanels.length

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-100">📡 Results Receiver</h2>
          <p className="text-xs text-slate-600 mt-0.5">
            Live detection and counting results across all running services.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${totalPanels > 0 && runningSet.size > 0 ? 'bg-green-400 animate-pulse' : 'bg-slate-600'}`} />
          <span className="text-xs text-slate-500">{totalPanels} service{totalPanels !== 1 ? 's' : ''}</span>
          {totalPanels > 0 && (
            <button
              onClick={() => {
                clearAllResults().catch(() => {})
                setPanels({})
                setCounterPanels({})
                setDetCounterData({})
                for (const es of esRefs.current.values()) es.close()
                for (const es of counterEsRefs.current.values()) es.close()
                for (const es of detCounterEsRefs.current.values()) es.close()
                esRefs.current.clear()
                counterEsRefs.current.clear()
                detCounterEsRefs.current.clear()
              }}
              className="text-xs text-slate-600 hover:text-red-400 cursor-pointer ml-2"
            >Clear all</button>
          )}
        </div>
      </div>

      {totalPanels === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center gap-3">
          <div className="text-4xl opacity-20">📡</div>
          <p className="text-slate-500 text-sm">No services have reported yet</p>
          <p className="text-slate-600 text-xs">Start a service and results will appear here automatically.</p>
        </div>
      ) : (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(480px, 1fr))' }}>
          {detectionPanels.map(data => (
            <ServicePanel key={data.name} data={data} isRunning={runningSet.has(data.name)} exists={existingSet.has(data.name)} counterInfo={detCounterData[data.name]} />
          ))}
          {counterServicePanels.map(data => (
            <CounterServicePanel key={data.name} data={data} isRunning={runningSet.has(data.name)} exists={existingSet.has(data.name)} />
          ))}
        </div>
      )}
    </div>
  )
}
