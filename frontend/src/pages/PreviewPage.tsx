import { useState, useEffect, useRef, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  getMjpegStreamUrl, getVideoState,
  videoPause, videoSpeed, videoSeek, videoSeekTo, videoStep,
  sseUrl, api,
} from '../lib/api'
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

// ── Main page ─────────────────────────────────────────────────────────────────

export function PreviewPage() {
  const [params] = useSearchParams()
  const name = params.get('service') ?? ''
  const isVideo = params.get('mode') === 'video'

  // ── Frame feed ──
  const mjpegUrl = useMemo(() => name ? getMjpegStreamUrl(name) : '', [name])

  // ── Results ──
  const [results, setResults] = useState<ServiceResults>({
    results: [], lastSeen: 0, totalReports: 0, carCount: 0, rearCount: 0,
  })
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!name) return

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
  }, [name])

  const isLive = Date.now() - results.lastSeen < 5000

  if (!name) {
    return (
      <div className="min-h-screen bg-[#0f172a] flex items-center justify-center">
        <p className="text-slate-500 text-sm">No service specified. Open this from the Preview button.</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0f172a] flex flex-col">
      {/* Header */}
      <header className="flex items-center gap-3 px-5 py-3 border-b border-[#1e293b] shrink-0">
        <div className="w-7 h-7 rounded-lg bg-violet-600/20 border border-violet-500/30 flex items-center justify-center">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="1.5">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
            <circle cx="12" cy="12" r="3"/>
          </svg>
        </div>
        <span className="text-sm font-semibold text-slate-100">VisionQ</span>
        <span className="text-slate-600">—</span>
        <div className="w-2 h-2 rounded-full bg-violet-400 animate-pulse" />
        <span className="text-sm text-slate-300 font-medium">{name}</span>
        <div className="ml-auto flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${isLive ? 'bg-green-400 animate-pulse' : 'bg-slate-600'}`} />
          <span className="text-xs text-slate-500">
            {isLive ? `Live · ${new Date(results.lastSeen).toLocaleTimeString()}` : 'waiting…'}
          </span>
        </div>
      </header>

      {/* Body — two columns */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Left: video feed ── */}
        <div className="flex flex-col border-r border-[#1e293b]" style={{ width: '58%' }}>
          <div className="flex-1 bg-black flex items-center justify-center overflow-hidden">
            {mjpegUrl && <img src={mjpegUrl} alt="preview" className="w-full h-full object-contain" />}
          </div>
          {isVideo && <VideoControls name={name} />}
        </div>

        {/* ── Right: results ── */}
        <div className="flex flex-col" style={{ width: '42%' }}>
          {/* Stats */}
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
          </div>

          {/* Table */}
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
      </div>
    </div>
  )
}
