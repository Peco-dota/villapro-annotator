import { useState, useEffect, useRef, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  getMjpegStreamUrl, getVideoState,
  videoPause, videoSpeed, videoSeek, videoSeekTo, videoStep,
  sseUrl, api, counterSseUrl,
} from '../lib/api'
import type { CountingResult } from '../lib/types'
import { Button } from '../components/ui/Button'

// ── Types ─────────────────────────────────────────────────────────────────────

interface DetectionPayload {
  service_name: string
  car?: { detected: boolean; direction: string; confidence: number }
  car_rear?: { detected: boolean; direction: string; confidence: number }
  gate?: { open: boolean }
  timestamp?: string
}

interface ServiceResults {
  results: DetectionPayload[]
  lastSeen: number
  totalReports: number
  carCount: number
  rearCount: number
}

interface CounterState {
  events: CountingResult[]
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

const SPEEDS = [0.5, 1, 2, 4]

function dirLabel(d: string | undefined, conf: number | undefined, detected: boolean | undefined) {
  if (!d) return <span className="text-slate-700">—</span>
  if (d === 'no_car' || !detected) return <span className="text-slate-500">no_car</span>
  return (
    <span className={DIR_COLOR[d] ?? 'text-slate-400'}>
      {d}{conf ? ` ${(conf * 100).toFixed(0)}%` : ''}
    </span>
  )
}

// ── Video controls ────────────────────────────────────────────────────────────

function VideoControls({ name }: { name: string }) {
  const { data: videoState, refetch } = useQuery({
    queryKey: ['video-state-ext', name],
    queryFn: () => getVideoState(name),
    refetchInterval: 500,
  })

  const pauseMut  = useMutation({ mutationFn: () => videoPause(name), onSuccess: () => refetch() })
  const speedMut  = useMutation({ mutationFn: (s: number) => videoSpeed(name, s), onSuccess: () => refetch() })
  const seekMut   = useMutation({ mutationFn: (d: number) => videoSeek(name, d),  onSuccess: () => refetch() })
  const seekToMut = useMutation({ mutationFn: (ms: number) => videoSeekTo(name, ms), onSuccess: () => refetch() })
  const stepMut   = useMutation({ mutationFn: () => videoStep(name) })

  const fmtTime = (ms: number) => {
    const s = Math.floor(ms / 1000)
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
  }

  const pos = videoState?.pos_ms ?? 0
  const dur = videoState?.duration_ms ?? 0
  const paused = videoState?.paused ?? false
  const speed = videoState?.speed ?? 1

  const [hoverPct, setHoverPct] = useState<number | null>(null)
  const getPct = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    return Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
  }

  return (
    <div className="px-4 py-3 border-t border-[#1e293b] flex flex-col gap-3 bg-[#0f172a]">
      {dur > 0 && (
        <div className="flex items-center gap-3 text-sm text-slate-400">
          <span className="w-12 text-right shrink-0 font-mono">{fmtTime(pos)}</span>
          <div
            className="flex-1 h-2 bg-slate-700 rounded-full relative cursor-pointer"
            onClick={e => seekToMut.mutate(getPct(e) * dur)}
            onMouseMove={e => setHoverPct(getPct(e))}
            onMouseLeave={() => setHoverPct(null)}
          >
            <div className="h-full bg-violet-500 rounded-full transition-all" style={{ width: `${(pos / dur) * 100}%` }} />
            {hoverPct !== null && (
              <>
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-white/60 rounded-full pointer-events-none"
                  style={{ left: `${hoverPct * 100}%`, transform: 'translateX(-50%)' }}
                />
                <div
                  className="absolute -top-8 bg-slate-800 border border-slate-600 text-white text-xs font-mono px-2 py-0.5 rounded pointer-events-none whitespace-nowrap"
                  style={{
                    left: `${hoverPct * 100}%`,
                    transform: `translateX(${hoverPct < 0.08 ? '0%' : hoverPct > 0.92 ? '-100%' : '-50%'})`,
                  }}
                >
                  {fmtTime(hoverPct * dur)}
                </div>
              </>
            )}
          </div>
          <span className="w-12 shrink-0 font-mono">{fmtTime(dur)}</span>
        </div>
      )}
      <div className="flex items-center gap-2 flex-wrap">
        <Button size="sm" variant="ghost" onClick={() => seekToMut.mutate(0)} title="Go to start">⏮</Button>
        <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(-15000)}>-15s</Button>
        <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(-5000)}>-5s</Button>
        <Button size="sm" variant="ghost" onClick={() => pauseMut.mutate()} disabled={pauseMut.isPending}>
          {paused ? '▶' : '⏸'}
        </Button>
        {paused && <Button size="sm" variant="ghost" onClick={() => stepMut.mutate()} title="Step one frame">⏭</Button>}
        <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(5000)}>+5s</Button>
        <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(15000)}>+15s</Button>
        <div className="flex items-center gap-1.5 ml-2">
          {SPEEDS.map(s => (
            <button key={s} onClick={() => speedMut.mutate(s)}
              className={`text-sm px-3 py-1 rounded cursor-pointer transition-colors
                ${speed === s ? 'bg-violet-600 text-white' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'}`}>
              {s}×
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Combined right panel (Detection + Counter) ────────────────────────────────

function CombinedRightPanel({ serviceName, results }: { serviceName: string; results: ServiceResults }) {
  const counterName = `${serviceName}_counter`
  const [counterData, setCounterData] = useState<CounterState>({ events: [], currentCount: 0, totalIn: 0, totalOut: 0, lastSeen: 0 })
  const cntEsRef = useRef<EventSource | null>(null)

  useEffect(() => {
    api.get('/api/counting/results/all').then(r => {
      const buf = r.data as Record<string, CountingResult[]>
      const evts = (buf[counterName] ?? []).filter(e => e.event === 'car_passed')
      if (evts.length) {
        setCounterData({
          events: evts,
          currentCount: evts[0].count,
          totalIn:  evts.filter(e => e.change > 0).length,
          totalOut: evts.filter(e => e.change < 0).length,
          lastSeen: Date.now(),
        })
      }
    }).catch(() => {})

    const es = new EventSource(counterSseUrl(counterName))
    cntEsRef.current = es
    es.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data) as CountingResult
        if (evt.event !== 'car_passed') return
        setCounterData(prev => ({
          events: [evt, ...prev.events].slice(0, 200),
          currentCount: evt.count,
          totalIn:  prev.totalIn  + (evt.change > 0 ? 1 : 0),
          totalOut: prev.totalOut + (evt.change < 0 ? 1 : 0),
          lastSeen: Date.now(),
        }))
      } catch { /* ignore */ }
    }
    return () => { es.close(); cntEsRef.current = null }
  }, [counterName])

  const isDetLive = Date.now() - results.lastSeen < 5000
  const isCntLive = Date.now() - counterData.lastSeen < 10000

  return (
    <div className="flex flex-col" style={{ width: '42%' }}>
      {/* Counting stats */}
      <div className="flex items-center gap-6 px-6 py-3 border-b border-[#1e293b] bg-teal-900/10 shrink-0">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${isCntLive ? 'bg-teal-400 animate-pulse' : 'bg-slate-600'}`} />
          <span className="text-xs text-slate-500 font-medium">Parking</span>
        </div>
        <div className="flex flex-col items-center">
          <span className="text-3xl font-bold text-teal-300 leading-none">{counterData.currentCount}</span>
          <span className="text-xs text-slate-500 mt-1">🅿 Current</span>
        </div>
        <div className="w-px h-8 bg-slate-800" />
        <div className="flex flex-col items-center">
          <span className="text-2xl font-bold text-green-400 leading-none">+{counterData.totalIn}</span>
          <span className="text-xs text-slate-600 mt-0.5">Entered</span>
        </div>
        <div className="flex flex-col items-center">
          <span className="text-2xl font-bold text-orange-400 leading-none">−{counterData.totalOut}</span>
          <span className="text-xs text-slate-600 mt-0.5">Exited</span>
        </div>
      </div>

      {/* Detection stats */}
      <div className="flex gap-6 px-6 py-3 border-b border-[#1e293b] bg-[#0f172a]/60 shrink-0">
        {[
          { label: 'Total Reports', value: results.totalReports, color: 'text-violet-400' },
          { label: 'Car detected', value: results.carCount, color: 'text-green-400' },
          { label: 'Rear detected', value: results.rearCount, color: 'text-blue-400' },
        ].map(({ label, value, color }) => (
          <div key={label} className="flex flex-col">
            <span className={`text-2xl font-bold leading-tight ${color}`}>{value}</span>
            <span className="text-xs text-slate-600 mt-0.5">{label}</span>
          </div>
        ))}
        {results.results[0]?.car?.direction && (
          <div className="flex flex-col">
            <span className={`text-2xl font-bold leading-tight ${DIR_COLOR[results.results[0].car.direction] ?? 'text-slate-400'}`}>
              {results.results[0].car.direction}
            </span>
            <span className="text-xs text-slate-600 mt-0.5">Last car dir</span>
          </div>
        )}
        <div className="ml-auto flex items-center gap-2 self-start">
          <div className={`w-2 h-2 rounded-full ${isDetLive ? 'bg-green-400 animate-pulse' : 'bg-slate-600'}`} />
          <span className="text-xs text-slate-500">
            {isDetLive ? new Date(results.lastSeen).toLocaleTimeString() : 'waiting…'}
          </span>
        </div>
      </div>

      {/* Detection table */}
      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-[#0f172a] z-10">
            <tr className="border-b border-[#1e293b]">
              {['TIME', 'GATE', 'CAR', 'CAR DIR', 'REAR', 'REAR DIR'].map(h => (
                <th key={h} className="px-4 py-2.5 text-left text-xs font-bold text-slate-600 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {results.results.slice(0, 200).map((r, i) => {
              const gateOpen = r.gate?.open
              const carDet = r.car?.detected
              const rearDet = r.car_rear?.detected
              return (
                <tr key={i} className={`border-b border-[#1e293b]/40 transition-colors ${gateOpen ? 'bg-green-900/15' : 'hover:bg-[#1e293b]/30'}`}>
                  <td className="px-4 py-2 text-slate-500 font-mono text-xs whitespace-nowrap">{r.timestamp ?? '—'}</td>
                  <td className="px-4 py-2">
                    {gateOpen
                      ? <span className="text-green-400 font-bold text-xs bg-green-900/30 px-2 py-0.5 rounded">▲ OPEN</span>
                      : <span className="text-slate-700">—</span>}
                  </td>
                  <td className="px-4 py-2">
                    {carDet ? <span className="text-green-400 font-bold">●</span> : <span className="text-slate-700">○</span>}
                  </td>
                  <td className="px-4 py-2">{dirLabel(r.car?.direction, r.car?.confidence, carDet)}</td>
                  <td className="px-4 py-2">
                    {rearDet ? <span className="text-green-400 font-bold">●</span> : <span className="text-slate-700">○</span>}
                  </td>
                  <td className="px-4 py-2">{dirLabel(r.car_rear?.direction, r.car_rear?.confidence, rearDet)}</td>
                </tr>
              )
            })}
            {results.results.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-16 text-center text-slate-600">
                  No results yet — start the service and wait for detections
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Counting right panel ──────────────────────────────────────────────────────

function CountingRightPanel({ counterName }: { counterName: string }) {
  const [data, setData] = useState<CounterState>({ events: [], currentCount: 0, totalIn: 0, totalOut: 0, lastSeen: 0 })
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    api.get('/api/counting/results/all').then(r => {
      const buf = r.data as Record<string, CountingResult[]>
      const evts = (buf[counterName] ?? []).filter(e => e.event === 'car_passed')
      if (evts.length) {
        setData({
          events: evts,
          currentCount: evts[0].count,
          totalIn:  evts.filter(e => e.change > 0).length,
          totalOut: evts.filter(e => e.change < 0).length,
          lastSeen: Date.now(),
        })
      }
    }).catch(() => {})

    const es = new EventSource(counterSseUrl(counterName))
    esRef.current = es
    es.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data) as CountingResult
        if (evt.event !== 'car_passed') return
        setData(prev => ({
          events: [evt, ...prev.events].slice(0, 200),
          currentCount: evt.count,
          totalIn:  prev.totalIn  + (evt.change > 0 ? 1 : 0),
          totalOut: prev.totalOut + (evt.change < 0 ? 1 : 0),
          lastSeen: Date.now(),
        }))
      } catch { /* ignore */ }
    }
    return () => { es.close(); esRef.current = null }
  }, [counterName])

  const isLive = Date.now() - data.lastSeen < 10000

  return (
    <div className="flex flex-col" style={{ width: '42%' }}>
      {/* Stats */}
      <div className="flex items-end gap-10 px-6 py-5 border-b border-[#1e293b] bg-[#0f172a]/60 shrink-0">
        <div className="flex flex-col items-center">
          <span className="text-5xl font-bold text-teal-300 leading-none">{data.currentCount}</span>
          <span className="text-xs text-slate-500 mt-2">🅿 On parking</span>
        </div>
        <div className="w-px h-12 bg-slate-800" />
        <div className="flex flex-col items-center">
          <span className="text-3xl font-bold text-green-400 leading-none">+{data.totalIn}</span>
          <span className="text-xs text-slate-600 mt-1">Entered</span>
        </div>
        <div className="flex flex-col items-center">
          <span className="text-3xl font-bold text-orange-400 leading-none">−{data.totalOut}</span>
          <span className="text-xs text-slate-600 mt-1">Exited</span>
        </div>
        <div className="ml-auto flex items-center gap-2 self-start">
          <div className={`w-2 h-2 rounded-full ${isLive ? 'bg-teal-400 animate-pulse' : 'bg-slate-600'}`} />
          <span className="text-xs text-slate-500">
            {isLive ? new Date(data.lastSeen).toLocaleTimeString() : 'waiting…'}
          </span>
        </div>
      </div>

      {/* Event table */}
      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-[#0f172a] z-10">
            <tr className="border-b border-[#1e293b]">
              {['TIME', 'EVENT', 'CLASS', 'CHANGE', 'COUNT'].map(h => (
                <th key={h} className="px-4 py-2.5 text-left text-xs font-bold text-slate-600 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.events.map((e, i) => (
              <tr key={i} className={`border-b border-[#1e293b]/40 transition-colors ${e.change > 0 ? 'bg-green-900/10 hover:bg-green-900/20' : 'bg-orange-900/10 hover:bg-orange-900/20'}`}>
                <td className="px-4 py-2 text-slate-500 font-mono text-xs whitespace-nowrap">
                  {e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : '—'}
                </td>
                <td className="px-4 py-2">
                  {e.change > 0
                    ? <span className="text-green-400 font-bold text-xs bg-green-900/30 px-2 py-0.5 rounded">↑ IN</span>
                    : <span className="text-orange-400 font-bold text-xs bg-orange-900/30 px-2 py-0.5 rounded">↓ OUT</span>}
                </td>
                <td className="px-4 py-2 text-slate-400 font-mono text-xs">{e.trigger_class}</td>
                <td className="px-4 py-2">
                  <span className={`font-bold ${e.change > 0 ? 'text-green-400' : 'text-orange-400'}`}>
                    {e.change > 0 ? `+${e.change}` : e.change}
                  </span>
                </td>
                <td className="px-4 py-2 text-teal-300 font-bold font-mono">{e.count}</td>
              </tr>
            ))}
            {data.events.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-16 text-center text-slate-600">
                  No counting events yet — start the service and wait
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Detection right panel ─────────────────────────────────────────────────────

function DetectionRightPanel({ results }: { results: ServiceResults }) {
  const isLive = Date.now() - results.lastSeen < 5000

  return (
    <div className="flex flex-col" style={{ width: '42%' }}>
      <div className="flex gap-8 px-6 py-4 border-b border-[#1e293b] bg-[#0f172a]/60 shrink-0">
        {[
          { label: 'Total Reports', value: results.totalReports, color: 'text-violet-400' },
          { label: 'Car detected', value: results.carCount, color: 'text-green-400' },
          { label: 'Rear detected', value: results.rearCount, color: 'text-blue-400' },
        ].map(({ label, value, color }) => (
          <div key={label} className="flex flex-col">
            <span className={`text-3xl font-bold leading-tight ${color}`}>{value}</span>
            <span className="text-xs text-slate-600 mt-0.5">{label}</span>
          </div>
        ))}
        {results.results[0]?.car?.direction && (
          <div className="flex flex-col">
            <span className={`text-3xl font-bold leading-tight ${DIR_COLOR[results.results[0].car.direction] ?? 'text-slate-400'}`}>
              {results.results[0].car.direction}
            </span>
            <span className="text-xs text-slate-600 mt-0.5">Last car dir</span>
          </div>
        )}
        <div className="ml-auto flex items-center gap-2 self-start">
          <div className={`w-2 h-2 rounded-full ${isLive ? 'bg-green-400 animate-pulse' : 'bg-slate-600'}`} />
          <span className="text-xs text-slate-500">
            {isLive ? new Date(results.lastSeen).toLocaleTimeString() : 'waiting…'}
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-[#0f172a] z-10">
            <tr className="border-b border-[#1e293b]">
              {['TIME', 'GATE', 'CAR', 'CAR DIR', 'REAR', 'REAR DIR'].map(h => (
                <th key={h} className="px-4 py-2.5 text-left text-xs font-bold text-slate-600 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {results.results.slice(0, 200).map((r, i) => {
              const gateOpen = r.gate?.open
              const carDet = r.car?.detected
              const rearDet = r.car_rear?.detected
              return (
                <tr key={i} className={`border-b border-[#1e293b]/40 transition-colors ${gateOpen ? 'bg-green-900/15' : 'hover:bg-[#1e293b]/30'}`}>
                  <td className="px-4 py-2 text-slate-500 font-mono text-xs whitespace-nowrap">{r.timestamp ?? '—'}</td>
                  <td className="px-4 py-2">
                    {gateOpen
                      ? <span className="text-green-400 font-bold text-xs bg-green-900/30 px-2 py-0.5 rounded">▲ OPEN</span>
                      : <span className="text-slate-700">—</span>}
                  </td>
                  <td className="px-4 py-2">
                    {carDet ? <span className="text-green-400 font-bold">●</span> : <span className="text-slate-700">○</span>}
                  </td>
                  <td className="px-4 py-2">{dirLabel(r.car?.direction, r.car?.confidence, carDet)}</td>
                  <td className="px-4 py-2">
                    {rearDet ? <span className="text-green-400 font-bold">●</span> : <span className="text-slate-700">○</span>}
                  </td>
                  <td className="px-4 py-2">{dirLabel(r.car_rear?.direction, r.car_rear?.confidence, rearDet)}</td>
                </tr>
              )
            })}
            {results.results.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-16 text-center text-slate-600">
                  No results yet — start the service and wait for detections
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function PreviewPage() {
  const [params] = useSearchParams()
  const name       = params.get('service') ?? ''
  const isVideo    = params.get('mode') === 'video'
  const isCounter  = params.get('kind') === 'counter'
  const hasCounter = params.get('counter') === 'true'

  const mjpegUrl = useMemo(() => name ? getMjpegStreamUrl(name) : '', [name])

  // Detection results state (only used when not counter)
  const [results, setResults] = useState<ServiceResults>({
    results: [], lastSeen: 0, totalReports: 0, carCount: 0, rearCount: 0,
  })
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!name || isCounter) return

    api.get('/api/detection/results/all').then(r => {
      const buf = r.data as Record<string, DetectionPayload[]>
      const res = buf[name] ?? []
      if (res.length) setResults({
        results: res, lastSeen: Date.now(),
        totalReports: res.length,
        carCount: res.filter(r => r.car?.detected).length,
        rearCount: res.filter(r => r.car_rear?.detected).length,
      })
    }).catch(() => {})

    const es = new EventSource(sseUrl(`/api/detection/services/${name}/stream`))
    esRef.current = es
    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data) as DetectionPayload
        setResults(prev => ({
          results: [payload, ...prev.results].slice(0, 200),
          lastSeen: Date.now(),
          totalReports: prev.totalReports + 1,
          carCount: prev.carCount + (payload.car?.detected ? 1 : 0),
          rearCount: prev.rearCount + (payload.car_rear?.detected ? 1 : 0),
        }))
      } catch { /* ignore */ }
    }

    const pollId = setInterval(() => {
      api.get('/api/detection/results/all').then(r => {
        const buf = r.data as Record<string, DetectionPayload[]>
        const res = buf[name] ?? []
        if (!res.length) return
        setResults(prev => {
          if (res[0]?.timestamp === prev.results[0]?.timestamp) return prev
          return {
            results: res, lastSeen: Date.now(),
            totalReports: Math.max(prev.totalReports, res.length),
            carCount: res.filter(r => r.car?.detected).length,
            rearCount: res.filter(r => r.car_rear?.detected).length,
          }
        })
      }).catch(() => {})
    }, 2000)

    return () => { es.close(); clearInterval(pollId) }
  }, [name, isCounter])

  if (!name) {
    return (
      <div className="min-h-screen bg-[#0f172a] flex items-center justify-center">
        <p className="text-slate-500 text-sm">No service specified. Open this from the Preview button.</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0f172a] flex flex-col">
      <header className="flex items-center gap-3 px-5 py-3 border-b border-[#1e293b] shrink-0">
        <div className="w-7 h-7 rounded-lg bg-violet-600/20 border border-violet-500/30 flex items-center justify-center">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="1.5">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
            <circle cx="12" cy="12" r="3"/>
          </svg>
        </div>
        <span className="text-sm font-semibold text-slate-100">VisionQ</span>
        <span className="text-slate-600">—</span>
        <div className={`w-2 h-2 rounded-full ${isCounter ? 'bg-teal-400' : 'bg-violet-400'} animate-pulse`} />
        <span className="text-sm text-slate-300 font-medium">{name}</span>
        {isCounter && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-teal-900/60 border border-teal-700/50 text-teal-300">Counter</span>
        )}
        {!isCounter && hasCounter && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-teal-900/60 border border-teal-700/50 text-teal-300">Detection + Counter</span>
        )}
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Left: video feed */}
        <div className="flex flex-col border-r border-[#1e293b]" style={{ width: '58%' }}>
          <div className="flex-1 bg-black flex items-center justify-center overflow-hidden">
            {mjpegUrl && <img src={mjpegUrl} alt="preview" className="w-full h-full object-contain" />}
          </div>
          {isVideo && <VideoControls name={name} />}
        </div>

        {/* Right: counting, combined, or detection panel */}
        {isCounter
          ? <CountingRightPanel counterName={`${name}_counter`} />
          : hasCounter
            ? <CombinedRightPanel serviceName={name} results={results} />
            : <DetectionRightPanel results={results} />
        }
      </div>
    </div>
  )
}
