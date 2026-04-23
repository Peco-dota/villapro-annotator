import { useState, useEffect, useRef, useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  startService, stopService, restartService, deleteService,
  getServiceLog, getServiceStatus,
  startRecording, stopRecording,
  startDebug, stopDebug,
  startDataset, stopDataset,
  startPreview, stopPreview,
  getPreviewFrameUrl, getVideoState,
  videoPause, videoSpeed, videoSeek, videoStep,
  sseUrl, api,
} from '../../lib/api'
import type { ServiceConfig, ServiceStatus } from '../../lib/types'
import { Spinner } from '../ui/Spinner'
import { Button } from '../ui/Button'

interface Props {
  service: ServiceConfig
  onEdit: () => void
  onDuplicate: () => void
}

// ── Spinner animation ─────────────────────────────────────────────────────────

const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

function useSpinner() {
  const [frame, setFrame] = useState(0)
  useState(() => {
    const id = setInterval(() => setFrame(f => (f + 1) % SPINNER_FRAMES.length), 80)
    return () => clearInterval(id)
  })
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

function useServiceResults(name: string, enabled: boolean): ServiceResults {
  const [data, setData] = useState<ServiceResults>({ results: [], lastSeen: 0, totalReports: 0, carCount: 0, rearCount: 0 })
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!enabled) return

    // Load buffered results
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

    return () => { es.close(); esRef.current = null }
  }, [name, enabled])

  return data
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

function InlinePreview({ service, onStop }: { service: ServiceConfig; onStop: () => void }) {
  const [polledUrl, setPolledUrl] = useState('')
  const [displayedUrl, setDisplayedUrl] = useState('')
  const [fps, setFps] = useState(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const frameCountRef = useRef(0)
  const fpsTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const isVideo = service.input_mode === 'video'

  const refreshFrame = useCallback(() => {
    setPolledUrl(`${getPreviewFrameUrl(service.name)}&_t=${Date.now()}`)
  }, [service.name])

  useEffect(() => {
    refreshFrame()
    intervalRef.current = setInterval(refreshFrame, 100)
    fpsTimerRef.current = setInterval(() => {
      setFps(frameCountRef.current)
      frameCountRef.current = 0
    }, 1000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      if (fpsTimerRef.current) clearInterval(fpsTimerRef.current)
    }
  }, [refreshFrame])

  const { data: videoState, refetch: refetchVideo } = useQuery({
    queryKey: ['video-state', service.name],
    queryFn: () => getVideoState(service.name),
    enabled: isVideo,
    refetchInterval: isVideo ? 500 : false,
  })

  const pauseMut = useMutation({ mutationFn: () => videoPause(service.name), onSuccess: () => refetchVideo() })
  const speedMut = useMutation({ mutationFn: (s: number) => videoSpeed(service.name, s), onSuccess: () => refetchVideo() })
  const seekMut  = useMutation({ mutationFn: (d: number) => videoSeek(service.name, d),  onSuccess: () => refetchVideo() })
  const stepMut  = useMutation({ mutationFn: () => videoStep(service.name) })

  const fmtTime = (ms: number) => {
    const s = Math.floor(ms / 1000)
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
  }

  const pos = videoState?.pos_ms ?? 0
  const dur = videoState?.duration_ms ?? 0
  const paused = videoState?.paused ?? false
  const currentSpeed = videoState?.speed ?? 1

  const receiverData = useServiceResults(service.name, true)
  const isLive = Date.now() - receiverData.lastSeen < 5000
  const lastDir = receiverData.results[0]?.car?.direction

  return (
    <div className="border-t border-[#1e293b] bg-[#0a0f1e]">
      <div className="flex" style={{ minHeight: 300 }}>

        {/* ── Left: video feed ── */}
        <div className="flex flex-col border-r border-[#1e293b]" style={{ width: '55%' }}>
          {/* Feed header */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-[#1e293b]">
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
              <span className="text-xs text-slate-400 font-medium">Live Preview</span>
              <span className="text-xs text-slate-600">{fps} fps</span>
            </div>
            <button onClick={onStop} className="text-xs text-slate-600 hover:text-red-400 cursor-pointer transition-colors">
              ✕ Close preview
            </button>
          </div>

          {/* Frame */}
          <div className="flex-1 bg-black flex items-center justify-center">
            {polledUrl && (
              <img key={polledUrl} src={polledUrl} alt="" className="hidden"
                onLoad={() => { setDisplayedUrl(polledUrl); frameCountRef.current += 1 }} />
            )}
            {displayedUrl
              ? <img src={displayedUrl} alt="preview" className="max-w-full max-h-full object-contain" />
              : <p className="text-xs text-slate-600">Waiting for frames…</p>
            }
          </div>

          {/* Video controls */}
          {isVideo && (
            <div className="px-3 py-2 border-t border-[#1e293b] flex flex-col gap-2">
              {dur > 0 && (
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <span className="w-10 text-right shrink-0">{fmtTime(pos)}</span>
                  <div className="flex-1 h-1.5 bg-slate-700 rounded-full cursor-pointer"
                    onClick={e => {
                      const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect()
                      seekMut.mutate((e.clientX - rect.left) / rect.width * dur - pos)
                    }}
                  >
                    <div className="h-full bg-violet-500 rounded-full" style={{ width: `${dur > 0 ? (pos / dur) * 100 : 0}%` }} />
                  </div>
                  <span className="w-10 shrink-0">{fmtTime(dur)}</span>
                </div>
              )}
              <div className="flex items-center gap-1.5 flex-wrap">
                <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(-pos)} title="Go to start">⏮</Button>
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

        {/* ── Right: receiver results ── */}
        <div className="flex flex-col" style={{ width: '45%' }}>
          {/* Results header */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-[#1e293b]">
            <div className="flex items-center gap-2">
              <div className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-green-400 animate-pulse' : 'bg-slate-600'}`} />
              <span className="text-xs text-slate-400 font-medium">Detection Results</span>
            </div>
            <span className="text-xs text-slate-600">{isLive ? new Date(receiverData.lastSeen).toLocaleTimeString() : 'waiting…'}</span>
          </div>

          {/* Stats */}
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

          {/* Results table */}
          <div className="flex-1 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-[#0a0f1e]">
                <tr className="border-b border-[#1e293b]">
                  {['TIME', 'GATE', 'CAR', 'DIR', 'REAR', 'DIR'].map(h => (
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
      </div>
    </div>
  )
}

// ── Main ServiceCard ──────────────────────────────────────────────────────────

export function ServiceCard({ service, onEdit, onDuplicate }: Props) {
  const qc = useQueryClient()
  const [showLog, setShowLog] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const [showPanel, setShowPanel] = useState(false)
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

  const startMut   = useMutation({ mutationFn: () => startService(service.name),   onSuccess: inv })
  const stopMut    = useMutation({ mutationFn: () => stopService(service.name),    onSuccess: inv })
  const restartMut = useMutation({ mutationFn: () => restartService(service.name), onSuccess: inv })
  const delMut     = useMutation({ mutationFn: () => deleteService(service.name),  onSuccess: invAll })

  const recStartMut = useMutation({ mutationFn: () => startRecording(service.name), onSuccess: inv })
  const recStopMut  = useMutation({ mutationFn: () => stopRecording(service.name),  onSuccess: inv })
  const dbgStartMut = useMutation({ mutationFn: () => startDebug(service.name),     onSuccess: inv })
  const dbgStopMut  = useMutation({ mutationFn: () => stopDebug(service.name),      onSuccess: inv })
  const dsStartMut  = useMutation({ mutationFn: () => startDataset(service.name),   onSuccess: inv })
  const dsStopMut   = useMutation({ mutationFn: () => stopDataset(service.name),    onSuccess: inv })

  const prvStartMut = useMutation({
    mutationFn: () => startPreview(service.name),
    onSuccess: () => { inv(); setShowPanel(true) },
  })
  const prvStopMut = useMutation({
    mutationFn: () => stopPreview(service.name),
    onSuccess: () => { inv(); setShowPanel(false) },
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
    <div className="bg-[#16213e] border border-[#1e293b] rounded-xl overflow-hidden">

      {/* ── Main row ── */}
      <div className="flex items-center gap-3 px-4 py-3">

        <DotState state={state} />

        <span className="text-sm font-bold text-slate-100 w-40 shrink-0 truncate">{service.name}</span>

        <div className="flex-1 min-w-0 flex items-center gap-1 text-xs text-slate-500 truncate font-mono">
          <span className="truncate">{sourceLabel(service)}</span>
          <span className="text-slate-600 shrink-0">→</span>
          <span className="shrink-0">{service.output_host}:{service.output_port}</span>
          <span className="text-slate-600 shrink-0 ml-1">[{service.model_path?.split('/').pop()}]</span>
          {service.auto_start && <span className="text-slate-600 shrink-0" title="Auto-start">⟳</span>}
          {isRec && <span className="text-red-400 shrink-0" title="Recording">🎥</span>}
        </div>

        {(running || loading) && car && (
          <div className="flex items-center gap-2 text-xs shrink-0">
            <span className={DIR_STYLE[car.direction] ?? 'text-slate-400'}>
              car: {car.direction} {car.detected ? `${(car.confidence * 100).toFixed(0)}%` : ''}
            </span>
            {carRear?.detected && (
              <span className={DIR_STYLE[carRear.direction] ?? 'text-slate-400'}>
                rear: {carRear.direction} {(carRear.confidence * 100).toFixed(0)}%
              </span>
            )}
            {gateOpen && <span className="text-green-400 font-bold">▲ GATE OPEN</span>}
          </div>
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

        {running && isRtspOrVideo && (
          <>
            <Btn
              color={isRec ? 'bg-red-900 border border-red-700 text-red-300 hover:bg-red-800' : 'bg-[#1e293b] text-slate-300 hover:bg-slate-700'}
              onClick={() => isRec ? recStopMut.mutate() : recStartMut.mutate()}
              disabled={isRec ? recStopMut.isPending : recStartMut.isPending}
              title="Toggle input stream recording"
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
            disabled={isDs ? dsStopMut.isPending : dsStartMut.isPending}
            title="Capture frames to dataset folder"
          >
            {isDs ? '■  Dataset' : '⏺  Dataset'}
          </Btn>
        )}

        <Btn color="bg-[#1e293b] text-slate-400 hover:text-slate-200"
          onClick={() => setShowLog(v => !v)}>
          {showLog ? '▼ Log' : '▶ Log'}
        </Btn>

        <div className="relative">
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

      {/* ── Error message ── */}
      {hasError && status?.error && (
        <div className="px-4 pb-2 text-xs text-red-400 font-mono">{status.error}</div>
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
      {showPanel && isPrev && (
        <InlinePreview service={service} onStop={handlePanelClose} />
      )}
    </div>
  )
}
