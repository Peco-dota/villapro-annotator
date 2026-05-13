import { useState, useEffect, useRef, useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  startService, stopService, restartService, deleteService,
  getServiceLog, getServiceStatus,
  startRecording, stopRecording,
  startDebug, stopDebug,
  startDataset, stopDataset,
  startPreview, stopPreview,
  startTcpPush, stopTcpPush,
  getMjpegStreamUrl, getVideoState,
  videoPause, videoSpeed, videoSeek, videoSeekTo, videoStep,
  sseUrl, api,
  startCounter, stopCounter, getCounterStatus, resetCounter,
  counterSseUrl,
} from '../../lib/api'
import type { ServiceConfig, ServiceStatus, CountingStatus, CountingResult } from '../../lib/types'
import { Spinner } from '../ui/Spinner'
import { Button } from '../ui/Button'

interface Props {
  service: ServiceConfig
  onEdit: () => void
  onDuplicate: () => void
  onPreview?: () => void
}

// ── Spinner animation ─────────────────────────────────────────────────────────

const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

function useSpinner() {
  const [frame, setFrame] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setFrame(f => (f + 1) % SPINNER_FRAMES.length), 80)
    return () => clearInterval(id)
  }, [])
  return SPINNER_FRAMES[frame]
}

// ── Small UI helpers ──────────────────────────────────────────────────────────

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

const DIR_STYLE: Record<string, string> = {
  forward:  'text-blue-400',
  backward: 'text-orange-400',
  idle:     'text-yellow-400',
  no_car:   'text-slate-500',
  building: 'text-slate-500',
}

const DIR_COLOR: Record<string, string> = {
  forward:  'text-blue-400',
  backward: 'text-orange-400',
  idle:     'text-yellow-400',
  no_car:   'text-slate-500',
  building: 'text-slate-500',
}

function sourceLabel(s: ServiceConfig): string {
  if (s.input_mode === 'rtsp') {
    const user = s.rtsp_user ? `${s.rtsp_user}:***@` : ''
    return `📷 rtsp://${user}${s.rtsp_ip}:${s.rtsp_port}/${s.rtsp_channel}`
  }
  if (s.input_mode === 'video') return `🎬 ${s.video_path?.split('/').pop() ?? s.video_path}${s.video_loop ? ' ↻' : ''}`
  return `:${s.input_port}`
}

// ── Live receiver results hook ────────────────────────────────────────────────

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

function useServiceResults(name: string, enabled: boolean, runKey: string): ServiceResults {
  const [data, setData] = useState<ServiceResults>({ results: [], lastSeen: 0, totalReports: 0, carCount: 0, rearCount: 0 })
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    // Reset on every new run (runKey changes when service restarts)
    setData({ results: [], lastSeen: 0, totalReports: 0, carCount: 0, rearCount: 0 })
    if (!enabled) return

    // Load buffered results for this run (server clears buffer on start, so this is fresh)
    api.get('/api/detection/results/all').then(r => {
      const buf = r.data as Record<string, DetectionPayload[]>
      const results = buf[name] ?? []
      if (results.length) {
        setData({
          results,
          lastSeen: Date.now(),
          totalReports: results.length,
          carCount: results.filter(r => r.car?.detected).length,
          rearCount: results.filter(r => r.car_rear?.detected).length,
        })
      }
    }).catch(() => {})

    // Subscribe to live SSE
    const url = sseUrl(`/api/detection/services/${name}/stream`)
    const es = new EventSource(url)
    esRef.current = es
    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data) as DetectionPayload
        setData(prev => {
          const newResults = [payload, ...prev.results].slice(0, 100)
          return {
            results: newResults,
            lastSeen: Date.now(),
            totalReports: prev.totalReports + 1,
            carCount: prev.carCount + (payload.car?.detected ? 1 : 0),
            rearCount: prev.rearCount + (payload.car_rear?.detected ? 1 : 0),
          }
        })
      } catch { /* ignore */ }
    }

    // Polling fallback — catches any SSE gaps
    const pollId = setInterval(() => {
      api.get('/api/detection/results/all').then(r => {
        const buf = r.data as Record<string, DetectionPayload[]>
        const results = buf[name] ?? []
        if (!results.length) return
        setData(prev => {
          // Only update if buffer has results newer than what we have
          if (results[0]?.timestamp === prev.results[0]?.timestamp) return prev
          return {
            results,
            lastSeen: Date.now(),
            totalReports: Math.max(prev.totalReports, results.length),
            carCount: results.filter(r => r.car?.detected).length,
            rearCount: results.filter(r => r.car_rear?.detected).length,
          }
        })
      }).catch(() => {})
    }, 2000)

    return () => { es.close(); esRef.current = null; clearInterval(pollId) }
  }, [name, enabled, runKey])

  return data
}

// ── Counting events hook ──────────────────────────────────────────────────────

interface CounterState {
  events: CountingResult[]
  currentCount: number
  totalIn: number
  totalOut: number
  lastSeen: number
}

function useCounterEvents(counterName: string, enabled: boolean): CounterState {
  const [data, setData] = useState<CounterState>({ events: [], currentCount: 0, totalIn: 0, totalOut: 0, lastSeen: 0 })
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    setData({ events: [], currentCount: 0, totalIn: 0, totalOut: 0, lastSeen: 0 })
    if (!enabled) return

    // Load buffered results
    api.get('/api/counting/results/all').then(r => {
      const buf = r.data as Record<string, CountingResult[]>
      const evts = (buf[counterName] ?? []).filter(e => e.event === 'car_passed')
      if (evts.length) {
        const last = evts[0]
        setData({
          events: evts,
          currentCount: last.count,
          totalIn:  evts.filter(e => e.change > 0).length,
          totalOut: evts.filter(e => e.change < 0).length,
          lastSeen: Date.now(),
        })
      }
    }).catch(() => {})

    const url = counterSseUrl(counterName)
    const es = new EventSource(url)
    esRef.current = es
    es.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data) as CountingResult
        if (evt.event !== 'car_passed') return
        setData(prev => ({
          events: [evt, ...prev.events].slice(0, 100),
          currentCount: evt.count,
          totalIn:  prev.totalIn  + (evt.change > 0 ? 1 : 0),
          totalOut: prev.totalOut + (evt.change < 0 ? 1 : 0),
          lastSeen: Date.now(),
        }))
      } catch { /* ignore */ }
    }

    return () => { es.close(); esRef.current = null }
  }, [counterName, enabled])

  return data
}

// ── Counting panel (right side of preview for counter services) ───────────────

function CountingPanel({ counterName }: { counterName: string }) {
  const data = useCounterEvents(counterName, true)
  const isLive = Date.now() - data.lastSeen < 10000

  return (
    <div className="flex flex-col min-h-0" style={{ width: '45%' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#1e293b] shrink-0">
        <div className="flex items-center gap-2">
          <div className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-teal-400 animate-pulse' : 'bg-slate-600'}`} />
          <span className="text-xs text-slate-400 font-medium">Counting</span>
        </div>
        <span className="text-xs text-slate-600">{isLive ? new Date(data.lastSeen).toLocaleTimeString() : 'waiting…'}</span>
      </div>

      {/* Stats */}
      <div className="flex items-center gap-6 px-4 py-3 border-b border-[#1e293b] bg-[#0f172a]/40 shrink-0">
        <div className="flex flex-col items-center">
          <span className="text-3xl font-bold text-teal-300 leading-none">{data.currentCount}</span>
          <span className="text-[10px] text-slate-500 mt-1">🅿 Current</span>
        </div>
        <div className="w-px h-10 bg-slate-800" />
        <div className="flex flex-col items-center">
          <span className="text-xl font-bold text-green-400 leading-none">+{data.totalIn}</span>
          <span className="text-[10px] text-slate-500 mt-1">Entered</span>
        </div>
        <div className="flex flex-col items-center">
          <span className="text-xl font-bold text-orange-400 leading-none">−{data.totalOut}</span>
          <span className="text-[10px] text-slate-500 mt-1">Exited</span>
        </div>
      </div>

      {/* Event log */}
      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-[#0a0f1e]">
            <tr className="border-b border-[#1e293b]">
              {['TIME', 'EVENT', 'CLASS', 'CHANGE', 'TOTAL'].map(h => (
                <th key={h} className="px-2 py-1.5 text-left text-[10px] font-bold text-slate-600 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.events.map((e, i) => (
              <tr key={i} className={`border-b border-[#1e293b]/40 ${e.change > 0 ? 'bg-green-900/10' : 'bg-orange-900/10'}`}>
                <td className="px-2 py-1 text-slate-600 font-mono text-[10px] whitespace-nowrap">
                  {e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : '—'}
                </td>
                <td className="px-2 py-1">
                  {e.change > 0
                    ? <span className="text-green-400 font-bold">↑ IN</span>
                    : <span className="text-orange-400 font-bold">↓ OUT</span>}
                </td>
                <td className="px-2 py-1 text-slate-400 font-mono">{e.trigger_class}</td>
                <td className="px-2 py-1">
                  <span className={e.change > 0 ? 'text-green-400 font-bold' : 'text-orange-400 font-bold'}>
                    {e.change > 0 ? `+${e.change}` : e.change}
                  </span>
                </td>
                <td className="px-2 py-1 text-teal-300 font-bold font-mono">{e.count}</td>
              </tr>
            ))}
            {data.events.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-slate-600">No events yet</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Combined panel (Detection + Counter) ─────────────────────────────────────

function CombinedPanel({ serviceName, detectionData, isDetLive }: {
  serviceName: string
  detectionData: ServiceResults
  isDetLive: boolean
}) {
  const counterData = useCounterEvents(`${serviceName}_counter`, true)
  const isCntLive = Date.now() - counterData.lastSeen < 10000
  const lastDir = detectionData.results[0]?.car?.direction

  return (
    <div className="flex flex-col min-h-0" style={{ width: '45%' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#1e293b] shrink-0">
        <div className="flex items-center gap-2">
          <div className={`w-1.5 h-1.5 rounded-full ${isDetLive ? 'bg-green-400 animate-pulse' : 'bg-slate-600'}`} />
          <span className="text-xs text-slate-400 font-medium">Detection + Counter</span>
        </div>
        <span className="text-xs text-slate-600">{isDetLive ? new Date(detectionData.lastSeen).toLocaleTimeString() : 'waiting…'}</span>
      </div>

      {/* Compact counting strip */}
      <div className="flex items-center gap-4 px-3 py-2 border-b border-[#1e293b] bg-teal-900/10 shrink-0">
        <div className="flex items-center gap-1.5">
          <div className={`w-1.5 h-1.5 rounded-full ${isCntLive ? 'bg-teal-400 animate-pulse' : 'bg-slate-600'}`} />
          <span className="text-[10px] text-slate-500">Parking</span>
        </div>
        <div className="flex flex-col items-center">
          <span className="text-lg font-bold text-teal-300 leading-none">{counterData.currentCount}</span>
          <span className="text-[10px] text-slate-500">🅿</span>
        </div>
        <div className="w-px h-5 bg-slate-800" />
        <div className="flex flex-col items-center">
          <span className="text-sm font-bold text-green-400 leading-none">+{counterData.totalIn}</span>
          <span className="text-[10px] text-slate-600">In</span>
        </div>
        <div className="flex flex-col items-center">
          <span className="text-sm font-bold text-orange-400 leading-none">−{counterData.totalOut}</span>
          <span className="text-[10px] text-slate-600">Out</span>
        </div>
      </div>

      {/* Detection mini-stats */}
      <div className="flex gap-4 px-3 py-2 border-b border-[#1e293b] bg-[#0f172a]/40 shrink-0">
        {[
          { label: 'Reports', value: detectionData.totalReports },
          { label: 'Car', value: detectionData.carCount },
          { label: 'Rear', value: detectionData.rearCount },
        ].map(({ label, value }) => (
          <div key={label} className="flex flex-col">
            <span className="text-base font-bold text-violet-400 leading-tight">{value}</span>
            <span className="text-[10px] text-slate-600">{label}</span>
          </div>
        ))}
        {lastDir && (
          <div className="flex flex-col">
            <span className={`text-base font-bold leading-tight ${DIR_COLOR[lastDir] ?? 'text-slate-400'}`}>{lastDir}</span>
            <span className="text-[10px] text-slate-600">Last dir</span>
          </div>
        )}
      </div>

      {/* Detection table */}
      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-[#0a0f1e]">
            <tr className="border-b border-[#1e293b]">
              {['TIME', 'GATE', 'CAR', 'CAR DIR', 'REAR', 'REAR DIR'].map(h => (
                <th key={h} className="px-2 py-1.5 text-left text-[10px] font-bold text-slate-600 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {detectionData.results.slice(0, 100).map((r, i) => {
              const gateOpen = r.gate?.open
              const carDet = r.car?.detected
              const rearDet = r.car_rear?.detected
              return (
                <tr key={i} className={`border-b border-[#1e293b]/40 ${gateOpen ? 'bg-green-900/15' : ''}`}>
                  <td className="px-2 py-1 text-slate-600 font-mono text-[10px] whitespace-nowrap">{r.timestamp ?? '—'}</td>
                  <td className="px-2 py-1">
                    {gateOpen ? <span className="text-green-400 font-bold">▲ OPEN</span> : <span className="text-slate-700">—</span>}
                  </td>
                  <td className="px-2 py-1">
                    {carDet ? <span className="text-green-400 font-bold">●</span> : <span className="text-slate-700">○</span>}
                  </td>
                  <td className="px-2 py-1">{dirLabel(r.car?.direction, r.car?.confidence, carDet)}</td>
                  <td className="px-2 py-1">
                    {rearDet ? <span className="text-green-400 font-bold">●</span> : <span className="text-slate-700">○</span>}
                  </td>
                  <td className="px-2 py-1">{dirLabel(r.car_rear?.direction, r.car_rear?.confidence, rearDet)}</td>
                </tr>
              )
            })}
            {detectionData.results.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-slate-600">No results yet</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Inline preview + receiver panel ──────────────────────────────────────────

const SPEEDS = [0.5, 1, 2, 4]

function dirLabel(d: string | undefined, conf: number | undefined, detected: boolean | undefined) {
  if (!d) return <span className="text-slate-700">—</span>
  if (d === 'no_car' || !detected) return <span className="text-slate-600">no_car</span>
  return (
    <span className={DIR_COLOR[d] ?? 'text-slate-400'}>
      {d}{conf ? ` ${(conf * 100).toFixed(0)}%` : ''}
    </span>
  )
}

function InlinePreview({ service, onStop, runKey, counterExists }: { service: ServiceConfig; onStop: () => void; runKey: string; counterExists: boolean }) {
  const isCounter = service.kind === 'counter'
  const mjpegUrl = useMemo(() => getMjpegStreamUrl(service.name), [service.name])
  const isVideo = service.input_mode === 'video'

  const { data: videoState, refetch: refetchVideo } = useQuery({
    queryKey: ['video-state', service.name],
    queryFn: () => getVideoState(service.name),
    enabled: isVideo,
    refetchInterval: isVideo ? 500 : false,
  })

  const pauseMut  = useMutation({ mutationFn: () => videoPause(service.name), onSuccess: () => refetchVideo() })
  const speedMut  = useMutation({ mutationFn: (s: number) => videoSpeed(service.name, s), onSuccess: () => refetchVideo() })
  const seekMut   = useMutation({ mutationFn: (d: number) => videoSeek(service.name, d),  onSuccess: () => refetchVideo() })
  const seekToMut = useMutation({ mutationFn: (ms: number) => videoSeekTo(service.name, ms), onSuccess: () => refetchVideo() })
  const stepMut   = useMutation({ mutationFn: () => videoStep(service.name) })

  const [hoverPct, setHoverPct] = useState<number | null>(null)
  const getPct = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    return Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
  }

  const fmtTime = (ms: number) => {
    const s = Math.floor(ms / 1000)
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
  }

  const pos = videoState?.pos_ms ?? 0
  const dur = videoState?.duration_ms ?? 0
  const paused = videoState?.paused ?? false
  const currentSpeed = videoState?.speed ?? 1

  const receiverData = useServiceResults(service.name, !isCounter, runKey)
  const [, forceUpdate] = useState(0)
  useEffect(() => {
    if (!receiverData.lastSeen) return
    const remaining = 5000 - (Date.now() - receiverData.lastSeen)
    if (remaining <= 0) return
    const id = setTimeout(() => forceUpdate(n => n + 1), remaining + 50)
    return () => clearTimeout(id)
  }, [receiverData.lastSeen])
  const isLive = Date.now() - receiverData.lastSeen < 5000
  const lastDir = receiverData.results[0]?.car?.direction

  return (
    <div className="border-t border-[#1e293b] bg-[#0a0f1e] rounded-b-xl">
      <div className="flex overflow-hidden" style={{ height: 420 }}>

        {/* ── Left: video feed ── */}
        <div className="flex flex-col min-h-0 border-r border-[#1e293b]" style={{ width: '55%' }}>
          {/* Feed header */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-[#1e293b]">
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
              <span className="text-xs text-slate-400 font-medium">Live Preview</span>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => window.open(`/preview?service=${encodeURIComponent(service.name)}&mode=${service.input_mode}&kind=${service.kind ?? 'detection'}${!isCounter && counterExists ? '&counter=true' : ''}`, '_blank')}
                className="text-xs text-slate-600 hover:text-violet-400 cursor-pointer transition-colors flex items-center gap-1"
                title="Open in new tab"
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                  <polyline points="15 3 21 3 21 9"/>
                  <line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
                New tab
              </button>
              <button onClick={onStop} className="text-xs text-slate-600 hover:text-red-400 cursor-pointer transition-colors">
                ✕ Close
              </button>
            </div>
          </div>

          {/* Frame — MJPEG stream */}
          <div className="flex-1 min-h-0 bg-black flex items-center justify-center overflow-hidden">
            <img src={mjpegUrl} alt="preview" className="max-w-full max-h-full object-contain" />
          </div>

          {/* Video controls */}
          {isVideo && (
            <div className="px-3 py-2 border-t border-[#1e293b] flex flex-col gap-2">
              {dur > 0 && (
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <span className="w-10 text-right shrink-0">{fmtTime(pos)}</span>
                  <div
                    className="flex-1 py-2 -my-2 relative cursor-pointer"
                    onClick={e => seekToMut.mutate(getPct(e) * dur)}
                    onMouseMove={e => setHoverPct(getPct(e))}
                    onMouseLeave={() => setHoverPct(null)}
                  >
                    <div className="w-full h-1.5 bg-slate-700 rounded-full relative">
                      <div className="h-full bg-violet-500 rounded-full" style={{ width: `${(pos / dur) * 100}%` }} />
                      {hoverPct !== null && (
                        <>
                          <div
                            className="absolute top-0 bottom-0 w-0.5 bg-white/60 rounded-full pointer-events-none"
                            style={{ left: `${hoverPct * 100}%`, transform: 'translateX(-50%)' }}
                          />
                          <div
                            className="absolute -top-7 bg-slate-800 border border-slate-600 text-white text-[10px] font-mono px-1.5 py-0.5 rounded pointer-events-none whitespace-nowrap z-50"
                            style={{
                              left: `${hoverPct * 100}%`,
                              transform: `translateX(${hoverPct < 0.1 ? '0%' : hoverPct > 0.9 ? '-100%' : '-50%'})`,
                            }}
                          >
                            {fmtTime(hoverPct * dur)}
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                  <span className="w-10 shrink-0">{fmtTime(dur)}</span>
                </div>
              )}
              <div className="flex items-center gap-1.5 flex-wrap">
                <Button size="sm" variant="ghost" onClick={() => seekToMut.mutate(0)} title="Go to start">⏮</Button>
                <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(-15000)}>-15s</Button>
                <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(-5000)}>-5s</Button>
                <Button size="sm" variant="ghost" onClick={() => pauseMut.mutate()} disabled={pauseMut.isPending}>
                  {paused ? '▶' : '⏸'}
                </Button>
                {paused && <Button size="sm" variant="ghost" onClick={() => stepMut.mutate()}>⏭</Button>}
                <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(5000)}>+5s</Button>
                <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(15000)}>+15s</Button>
                <div className="flex items-center gap-1 ml-1">
                  {SPEEDS.map(s => (
                    <button key={s} onClick={() => speedMut.mutate(s)}
                      className={`text-xs px-2 py-0.5 rounded cursor-pointer transition-colors
                        ${currentSpeed === s ? 'bg-violet-600 text-white' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'}`}>
                      {s}×
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ── Right: counting panel, combined panel, or detection results ── */}
        {isCounter
          ? <CountingPanel counterName={`${service.name}_counter`} />
          : counterExists
            ? <CombinedPanel serviceName={service.name} detectionData={receiverData} isDetLive={isLive} />
            : (
              <div className="flex flex-col min-h-0" style={{ width: '45%' }}>
                <div className="flex items-center justify-between px-3 py-2 border-b border-[#1e293b]">
                  <div className="flex items-center gap-2">
                    <div className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-green-400 animate-pulse' : 'bg-slate-600'}`} />
                    <span className="text-xs text-slate-400 font-medium">Detection Results</span>
                  </div>
                  <span className="text-xs text-slate-600">{isLive ? new Date(receiverData.lastSeen).toLocaleTimeString() : 'waiting…'}</span>
                </div>

                <div className="flex gap-4 px-3 py-2 border-b border-[#1e293b] bg-[#0f172a]/40">
                  {[
                    { label: 'Reports', value: receiverData.totalReports },
                    { label: 'Car', value: receiverData.carCount },
                    { label: 'Rear', value: receiverData.rearCount },
                  ].map(({ label, value }) => (
                    <div key={label} className="flex flex-col">
                      <span className="text-base font-bold text-violet-400 leading-tight">{value}</span>
                      <span className="text-[10px] text-slate-600">{label}</span>
                    </div>
                  ))}
                  {lastDir && (
                    <div className="flex flex-col">
                      <span className={`text-base font-bold leading-tight ${DIR_COLOR[lastDir] ?? 'text-slate-400'}`}>{lastDir}</span>
                      <span className="text-[10px] text-slate-600">Last dir</span>
                    </div>
                  )}
                </div>

                <div className="flex-1 overflow-y-auto">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-[#0a0f1e]">
                      <tr className="border-b border-[#1e293b]">
                        {['TIME', 'GATE', 'CAR', 'CAR DIR', 'REAR', 'REAR DIR'].map(h => (
                          <th key={h} className="px-2 py-1.5 text-left text-[10px] font-bold text-slate-600 uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {receiverData.results.slice(0, 100).map((r, i) => {
                        const gateOpen = r.gate?.open
                        const carDet = r.car?.detected
                        const rearDet = r.car_rear?.detected
                        return (
                          <tr key={i} className={`border-b border-[#1e293b]/40 ${gateOpen ? 'bg-green-900/15' : ''}`}>
                            <td className="px-2 py-1 text-slate-600 font-mono text-[10px] whitespace-nowrap">{r.timestamp ?? '—'}</td>
                            <td className="px-2 py-1">
                              {gateOpen ? <span className="text-green-400 font-bold">▲ OPEN</span> : <span className="text-slate-700">—</span>}
                            </td>
                            <td className="px-2 py-1">
                              {carDet ? <span className="text-green-400 font-bold">●</span> : <span className="text-slate-700">○</span>}
                            </td>
                            <td className="px-2 py-1">{dirLabel(r.car?.direction, r.car?.confidence, carDet)}</td>
                            <td className="px-2 py-1">
                              {rearDet ? <span className="text-green-400 font-bold">●</span> : <span className="text-slate-700">○</span>}
                            </td>
                            <td className="px-2 py-1">{dirLabel(r.car_rear?.direction, r.car_rear?.confidence, rearDet)}</td>
                          </tr>
                        )
                      })}
                      {receiverData.results.length === 0 && (
                        <tr>
                          <td colSpan={6} className="px-3 py-8 text-center text-slate-600">No results yet</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )
        }
      </div>
    </div>
  )
}

// ── Main ServiceCard ──────────────────────────────────────────────────────────

export function ServiceCard({ service, onEdit, onDuplicate, onPreview }: Props) {
  const qc = useQueryClient()
  const [showLog, setShowLog] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const [runKey, setRunKey] = useState('init')
  const spinner = useSpinner()

  const { data: status } = useQuery<ServiceStatus>({
    queryKey: ['service-status', service.name],
    queryFn: () => getServiceStatus(service.name),
    refetchInterval: 1000,
  })

  const { data: logData } = useQuery<{ name: string; log: string[] }>({
    queryKey: ['service-log', service.name],
    queryFn: () => getServiceLog(service.name),
    enabled: showLog,
    refetchInterval: showLog ? 2000 : false,
  })

  const inv    = () => qc.invalidateQueries({ queryKey: ['service-status', service.name] })
  const invAll = () => qc.invalidateQueries({ queryKey: ['services'] })

  // ── Parking counter (auto-created as "{name}_counter") ────────────────────
  const counterName = `${service.name}_counter`
  const { data: counterStatus } = useQuery<CountingStatus>({
    queryKey: ['counter-status', counterName],
    queryFn: () => getCounterStatus(counterName),
    refetchInterval: 2000,
    retry: (_, err: unknown) => (err as { response?: { status?: number } }).response?.status !== 404,
  })
  const counterExists  = counterStatus !== undefined
  const counterRunning = counterStatus?.state === 'running'
  const invCounter = () => qc.invalidateQueries({ queryKey: ['counter-status', counterName] })

  const cntResetMut = useMutation({ mutationFn: () => resetCounter(counterName), onSuccess: invCounter })

  const startMut = useMutation({
    mutationFn: async () => {
      await startService(service.name)
      if (counterExists) try { await startCounter(counterName) } catch { /* already running or missing */ }
    },
    onSuccess: () => { inv(); invCounter(); setRunKey(Date.now().toString()) },
  })
  const stopMut = useMutation({
    mutationFn: async () => {
      await stopService(service.name)
      if (counterExists) try { await stopCounter(counterName) } catch { /* already stopped or missing */ }
    },
    onSuccess: () => { inv(); invCounter() },
  })
  const restartMut = useMutation({ mutationFn: () => restartService(service.name), onSuccess: inv })
  const delMut     = useMutation({ mutationFn: () => deleteService(service.name),  onSuccess: invAll })

  const recStartMut = useMutation({ mutationFn: () => startRecording(service.name), onSuccess: inv })
  const recStopMut  = useMutation({ mutationFn: () => stopRecording(service.name),  onSuccess: inv })
  const [dbgNotice, setDbgNotice] = useState<{ path: string; saved: boolean } | null>(null)
  const dbgStartMut = useMutation({
    mutationFn: () => startDebug(service.name),
    onSuccess: (data: { debug_path: string }) => { inv(); setDbgNotice({ path: data.debug_path, saved: false }) },
  })
  const dbgStopMut  = useMutation({
    mutationFn: () => stopDebug(service.name),
    onSuccess: (data: { debug_path: string }) => { inv(); setDbgNotice({ path: data.debug_path, saved: true }) },
  })
  const dsStartMut  = useMutation({ mutationFn: () => startDataset(service.name),   onSuccess: inv })
  const dsStopMut   = useMutation({ mutationFn: () => stopDataset(service.name),    onSuccess: inv })

  const tcpStartMut = useMutation({
    mutationFn: () => startTcpPush(service.name, {
      host: service.tcp_push_host,
      port: service.tcp_push_port,
      certfile: service.tcp_push_certfile || '',
      keyfile: service.tcp_push_keyfile || '',
      ca_certs: service.tcp_push_ca_certs || '',
    }),
    onSuccess: inv,
  })
  const tcpStopMut  = useMutation({ mutationFn: () => stopTcpPush(service.name), onSuccess: inv })

  const prvStartMut = useMutation({
    mutationFn: () => startPreview(service.name),
    onSuccess: () => { inv(); onPreview?.() },
  })
  const prvStopMut = useMutation({
    mutationFn: () => stopPreview(service.name),
    onSuccess: inv,
  })

  const state   = status?.state ?? 'stopped'
  const running = state === 'running'
  const loading = state === 'loading'
  const stopped = state === 'stopped'
  const hasError = state === 'error'

  const car      = status?.last_payload?.car
  const carRear  = status?.last_payload?.car_rear
  const gateOpen = status?.last_payload?.gate?.open ?? false

  const isRec  = status?.is_recording ?? false
  const isDbg  = status?.is_direction_debugging ?? false
  const isDs   = status?.is_dataset_capturing ?? false
  const isPrev = status?.is_previewing ?? false
  const isTcp  = status?.tcp_push_running ?? false

  const isRtspOrVideo = service.input_mode === 'rtsp' || service.input_mode === 'video'

  const statusText  = loading ? `${spinner} Loading` : running ? 'Running' : hasError ? 'Error' : 'Stopped'
  const statusColor = running ? 'text-green-400' : loading ? 'text-yellow-400' : hasError ? 'text-red-400' : 'text-slate-500'

  const handlePreviewToggle = () => {
    if (isPrev) {
      prvStopMut.mutate()
    } else {
      prvStartMut.mutate()
    }
  }

  const handlePanelClose = () => {
    prvStopMut.mutate()
  }

  return (
    <div className="bg-[#16213e] border border-[#1e293b] rounded-xl">

      {/* ── Main header ── */}
      <div className="flex flex-col px-4 pt-3 pb-2 gap-2">

        {/* Row 1: identity + live status */}
        <div className="flex items-center gap-3 min-w-0">
          <DotState state={state} />
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-sm font-bold text-slate-100 max-w-[10rem] truncate">{service.name}</span>
            {service.kind === 'counter'
              ? <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-teal-900/60 border border-teal-700/50 text-teal-300 shrink-0">Counter</span>
              : counterExists
                ? <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-teal-900/60 border border-teal-700/50 text-teal-300 shrink-0">Detection + Counter</span>
                : <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-500 shrink-0">Detection</span>
            }
          </div>
          <div className="flex-1 min-w-0 flex items-center gap-1 text-xs text-slate-500 truncate font-mono">
            <span className="truncate">{sourceLabel(service)}</span>
            {service.kind !== 'counter' && (
              <>
                <span className="text-slate-600 shrink-0">→</span>
                <span className="shrink-0">{service.output_host}:{service.output_port}</span>
              </>
            )}
            <span className="text-slate-600 shrink-0 ml-1">[{service.model_path?.split('/').pop()}]</span>
            {service.auto_start && <span className="text-slate-600 shrink-0" title="Auto-start">⟳</span>}
            {isRec && <span className="text-red-400 shrink-0" title="Recording">🎥</span>}
            {isTcp && <span className="text-orange-400 text-xs font-mono shrink-0" title={`TCP push active on port ${service.tcp_push_port}`}>TCP:{service.tcp_push_port}</span>}
          </div>
          {(running || loading) && (
            <div className="flex items-center gap-2 text-xs shrink-0">
              {car && (
                <>
                  <span className={DIR_STYLE[car.direction] ?? 'text-slate-400'}>
                    car: {car.direction} {car.detected ? `${(car.confidence * 100).toFixed(0)}%` : ''}
                  </span>
                  {carRear?.detected && (
                    <span className={DIR_STYLE[carRear.direction] ?? 'text-slate-400'}>
                      rear: {carRear.direction} {(carRear.confidence * 100).toFixed(0)}%
                    </span>
                  )}
                  {gateOpen && <span className="text-green-400 font-bold">▲ GATE OPEN</span>}
                </>
              )}
              {counterRunning && (
                <span className="text-teal-300 font-bold font-mono shrink-0" title="Parking occupancy">
                  🅿 {counterStatus?.count ?? 0}
                </span>
              )}
            </div>
          )}
          <span className={`text-xs font-medium shrink-0 ${statusColor}`}>{statusText}</span>
        </div>

        {/* Row 2: action buttons */}
        <div className="flex items-center gap-2 flex-wrap">
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
          {running && isRtspOrVideo && (
            <>
              <Btn
                color={isRec ? 'bg-red-900 border border-red-700 text-red-300 hover:bg-red-800' : 'bg-[#1e293b] text-slate-300 hover:bg-slate-700'}
                onClick={() => isRec ? recStopMut.mutate() : recStartMut.mutate()}
                disabled={(!isRec && !service.record_dir) || (isRec ? recStopMut.isPending : recStartMut.isPending)}
                title={!isRec && !service.record_dir ? 'Set a recording directory in the service config first' : 'Toggle input stream recording'}
              >
                {isRec ? '■  Rec Off' : '●  Rec'}
              </Btn>
              <Btn
                color={isPrev ? 'bg-blue-800 border border-blue-600 text-blue-200 hover:bg-blue-700' : 'bg-[#1e293b] text-slate-300 hover:bg-slate-700'}
                onClick={handlePreviewToggle}
                disabled={prvStartMut.isPending || prvStopMut.isPending}
                title="Toggle live preview + results panel"
              >
                {isPrev ? '■  Preview' : '👁  Preview'}
              </Btn>
              <Btn
                color={isDbg ? 'bg-green-900 border border-green-700 text-green-300 hover:bg-green-800' : 'bg-[#1e293b] text-slate-300 hover:bg-slate-700'}
                onClick={() => isDbg ? dbgStopMut.mutate() : dbgStartMut.mutate()}
                disabled={isDbg ? dbgStopMut.isPending : dbgStartMut.isPending}
                title="Capture direction debug CSV"
              >
                {isDbg ? '■  Debug' : '⏺  Debug'}
              </Btn>
            </>
          )}
          {running && (
            <Btn
              color={isDs ? 'bg-teal-900 border border-teal-700 text-teal-300 hover:bg-teal-800' : 'bg-[#1e293b] text-slate-300 hover:bg-slate-700'}
              onClick={() => isDs ? dsStopMut.mutate() : dsStartMut.mutate()}
              disabled={(!isDs && !service.dataset_dir) || (isDs ? dsStopMut.isPending : dsStartMut.isPending)}
              title={!isDs && !service.dataset_dir ? 'Set a dataset directory in the service config first' : 'Capture frames to dataset folder'}
            >
              {isDs ? '■  Dataset' : '⏺  Dataset'}
            </Btn>
          )}
          {service.tcp_push_enabled && (
            <Btn
              color={isTcp ? 'bg-orange-900 border border-orange-700 text-orange-300 hover:bg-orange-800' : 'bg-[#1e293b] text-slate-300 hover:bg-slate-700'}
              onClick={() => isTcp ? tcpStopMut.mutate() : tcpStartMut.mutate()}
              disabled={isTcp ? tcpStopMut.isPending : tcpStartMut.isPending}
              title={isTcp ? `TCP push running on port ${service.tcp_push_port}` : `Start TCP push on port ${service.tcp_push_port}`}
            >
              {isTcp ? `■  TCP :${service.tcp_push_port}` : `⏺  TCP :${service.tcp_push_port}`}
            </Btn>
          )}
          {counterRunning && (
            <Btn
              color="bg-teal-900/60 border border-teal-700/50 text-teal-300 hover:bg-teal-800/60"
              onClick={() => cntResetMut.mutate()}
              disabled={cntResetMut.isPending}
              title="Reset parking counter to zero"
            >
              🅿 Reset
            </Btn>
          )}
          <Btn color="bg-[#1e293b] text-slate-400 hover:text-slate-200"
            onClick={() => setShowLog(v => !v)}>
            {showLog ? '▼ Log' : '▶ Log'}
          </Btn>
          <div className="relative ml-auto">
            <button
              onClick={() => setMoreOpen(v => !v)}
              className="w-8 h-8 flex items-center justify-center rounded text-slate-500 hover:text-slate-200 hover:bg-slate-700 cursor-pointer text-lg"
            >⋯</button>
            {moreOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setMoreOpen(false)} />
                <div className="absolute right-0 top-9 z-20 bg-[#1e293b] border border-[#334155] rounded-lg shadow-xl py-1 w-44">
                  <MenuItem icon="↺" label="Relaunch" disabled={loading}
                    onClick={() => { restartMut.mutate(); setMoreOpen(false) }} />
                  <MenuItem icon="✎" label="Edit config" disabled={running || loading}
                    onClick={() => { onEdit(); setMoreOpen(false) }} />
                  <MenuItem icon="⧉" label="Duplicate"
                    onClick={() => { onDuplicate(); setMoreOpen(false) }} />
                  <div className="h-px bg-[#334155] my-1" />
                  <MenuItem icon="✕" label="Remove" danger
                    onClick={() => {
                      if (confirm(`Remove service "${service.name}"?`)) delMut.mutate()
                      setMoreOpen(false)
                    }} />
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* ── Error message ── */}
      {hasError && status?.error && (
        <div className="px-4 pb-2 text-xs text-red-400 font-mono">{status.error}</div>
      )}

      {/* ── Debug notice ── */}
      {dbgNotice && (
        <div className="mx-4 mb-2 flex items-center justify-between gap-2 px-3 py-2 bg-green-900/20 border border-green-700/40 rounded-lg text-xs text-green-300">
          <span>
            {dbgNotice.saved ? '✓ Debug log saved to: ' : '⏺ Debug log writing to: '}
            <span className="font-mono text-green-200">{dbgNotice.path}</span>
          </span>
          <button onClick={() => setDbgNotice(null)} className="text-green-600 hover:text-green-300 shrink-0 cursor-pointer">×</button>
        </div>
      )}

      {/* ── Log ── */}
      {showLog && (
        <div className="border-t border-[#1e293b]">
          <div className="bg-[#0a0f1e] px-4 py-3 max-h-32 overflow-y-auto">
            {logData?.log?.length ? (
              <div className="flex flex-col gap-0.5 font-mono text-xs text-green-400">
                {[...logData.log].reverse().map((line, i) => <div key={i}>{line}</div>)}
              </div>
            ) : (
              <p className="text-xs text-slate-600 font-mono">No log entries yet</p>
            )}
          </div>
        </div>
      )}

      {/* ── Inline preview + receiver panel ── */}
      {isPrev && (
        <InlinePreview service={service} onStop={handlePanelClose} runKey={runKey} counterExists={counterExists} />
      )}
    </div>
  )
}
