import { useMemo, useState, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getMjpegStreamUrl, getVideoState, updateService,
  videoPause, videoSpeed, videoSeek, videoSeekTo, videoStep, videoReverse,
} from '../../lib/api'
import type { ServiceConfig } from '../../lib/types'
import { Button } from '../ui/Button'

interface Props {
  service: ServiceConfig
  onClose: () => void
}

const SPEEDS = [0.5, 1, 2, 4]

type DrawStep = 'off' | 'pt_a' | 'pt_b' | 'side' | 'done'

export function PreviewWindow({ service, onClose }: Props) {
  const qc = useQueryClient()
  const mjpegUrl = useMemo(() => getMjpegStreamUrl(service.name), [service.name])
  const isVideo = service.input_mode === 'video'

  // ── Gate line drawing state ───────────────────────────────────────────────
  const imgRef  = useRef<HTMLImageElement>(null)
  const svgRef  = useRef<SVGSVGElement>(null)

  const initLine = service.gate_line?.length === 4 ? service.gate_line : null
  const initSide = service.gate_line_side?.length === 2 ? service.gate_line_side : null

  const [drawStep, setDrawStep] = useState<DrawStep>(initLine ? 'done' : 'off')
  const [ptA,  setPtA]  = useState<[number,number] | null>(initLine ? [initLine[0], initLine[1]] : null)
  const [ptB,  setPtB]  = useState<[number,number] | null>(initLine ? [initLine[2], initLine[3]] : null)
  const [side, setSide] = useState<[number,number] | null>(initSide ? [initSide[0], initSide[1]] : null)
  const [saved, setSaved] = useState(false)

  // Convert normalized [0-1] coords → SVG pixel position (accounts for img letterboxing)
  const toSvgPx = useCallback((nx: number, ny: number): [number, number] => {
    const svg = svgRef.current
    const img = imgRef.current
    if (!svg || !img) return [0, 0]
    const sr = svg.getBoundingClientRect()
    const ir = img.getBoundingClientRect()
    return [ir.left - sr.left + nx * ir.width, ir.top - sr.top + ny * ir.height]
  }, [])

  // Convert click event → normalized [0-1] coords relative to the img
  const toNorm = useCallback((e: React.MouseEvent<SVGSVGElement>): [number, number] => {
    const img = imgRef.current
    if (!img) return [0, 0]
    const ir = img.getBoundingClientRect()
    return [
      Math.max(0, Math.min(1, (e.clientX - ir.left) / ir.width)),
      Math.max(0, Math.min(1, (e.clientY - ir.top)  / ir.height)),
    ]
  }, [])

  const handleSvgClick = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (drawStep === 'off' || drawStep === 'done') return
    const pt = toNorm(e)
    if (drawStep === 'pt_a') { setPtA(pt); setPtB(null); setSide(null); setDrawStep('pt_b') }
    else if (drawStep === 'pt_b') { setPtB(pt); setSide(null); setDrawStep('side') }
    else if (drawStep === 'side') { setSide(pt); setDrawStep('done') }
  }, [drawStep, toNorm])

  const saveMut = useMutation({
    mutationFn: () => updateService(service.name, {
      ...service,
      gate_line:      ptA && ptB ? [ptA[0], ptA[1], ptB[0], ptB[1]] : [],
      gate_line_side: side ? [side[0], side[1]] : [],
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['services'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  const clearLine = () => {
    setPtA(null); setPtB(null); setSide(null); setDrawStep('off')
  }

  // SVG overlay coords (recomputed on render)
  const svgA    = ptA  ? toSvgPx(ptA[0],  ptA[1])  : null
  const svgB    = ptB  ? toSvgPx(ptB[0],  ptB[1])  : null
  const svgSide = side ? toSvgPx(side[0], side[1])  : null

  const cursor =
    drawStep === 'pt_a' || drawStep === 'pt_b' || drawStep === 'side' ? 'crosshair' : 'default'

  const stepHint =
    drawStep === 'pt_a'  ? 'Click to set line start point'  :
    drawStep === 'pt_b'  ? 'Click to set line end point'    :
    drawStep === 'side'  ? 'Click on the gate side (where car should be to open gate)' :
    ''

  // ── Video state ───────────────────────────────────────────────────────────
  const { data: videoState, refetch: refetchVideo } = useQuery({
    queryKey: ['video-state', service.name],
    queryFn: () => getVideoState(service.name),
    enabled: isVideo,
    refetchInterval: isVideo ? 500 : false,
  })

  const pauseMut   = useMutation({ mutationFn: () => videoPause(service.name),              onSuccess: () => refetchVideo() })
  const speedMut   = useMutation({ mutationFn: (s: number) => videoSpeed(service.name, s),  onSuccess: () => refetchVideo() })
  const seekMut    = useMutation({ mutationFn: (d: number) => videoSeek(service.name, d),   onSuccess: () => refetchVideo() })
  const seekToMut  = useMutation({ mutationFn: (ms: number) => videoSeekTo(service.name, ms), onSuccess: () => refetchVideo() })
  const stepMut    = useMutation({ mutationFn: () => videoStep(service.name) })
  const reverseMut = useMutation({ mutationFn: () => videoReverse(service.name),            onSuccess: () => refetchVideo() })

  const fmtTime = (ms: number) => {
    const s = Math.floor(ms / 1000)
    const m = Math.floor(s / 60)
    return `${m}:${String(s % 60).padStart(2, '0')}`
  }

  const pos          = videoState?.pos_ms      ?? 0
  const dur          = videoState?.duration_ms ?? 0
  const paused       = videoState?.paused      ?? false
  const currentSpeed = videoState?.speed       ?? 1
  const reverse      = videoState?.reverse     ?? false

  const [hoverPct, setHoverPct] = useState<number | null>(null)

  return (
    <div className="bg-[#0c0a14] border border-[#1e293b] rounded-xl">
      {/* Title bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#1e293b] rounded-t-xl overflow-hidden">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-violet-400 animate-pulse" />
          <span className="text-sm font-medium text-slate-200">Preview — {service.name}</span>
        </div>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-lg cursor-pointer px-1">&times;</button>
      </div>

      {/* Frame */}
      <div className="relative bg-black flex items-center justify-center overflow-hidden" style={{ minHeight: 240 }}>
        <img
          ref={imgRef}
          src={mjpegUrl}
          alt="preview"
          className="max-w-full max-h-[60vh] object-contain"
        />

        {/* SVG overlay for gate line drawing */}
        <svg
          ref={svgRef}
          className="absolute inset-0 w-full h-full"
          style={{ cursor, pointerEvents: drawStep !== 'off' && drawStep !== 'done' ? 'auto' : 'none' }}
          onClick={handleSvgClick}
        >
          {/* Drawn line */}
          {svgA && svgB && (
            <line
              x1={svgA[0]} y1={svgA[1]} x2={svgB[0]} y2={svgB[1]}
              stroke="#facc15" strokeWidth={2} strokeDasharray="6 3"
            />
          )}
          {/* Point A */}
          {svgA && (
            <circle cx={svgA[0]} cy={svgA[1]} r={5} fill="#facc15" />
          )}
          {/* Point B */}
          {svgB && (
            <circle cx={svgB[0]} cy={svgB[1]} r={5} fill="#facc15" />
          )}
          {/* Gate side marker */}
          {svgSide && (
            <>
              <circle cx={svgSide[0]} cy={svgSide[1]} r={8} fill="#22c55e" fillOpacity={0.7} />
              <text x={svgSide[0]} y={svgSide[1] + 4} textAnchor="middle" fontSize={9} fill="white" fontWeight="bold">G</text>
            </>
          )}
        </svg>

        {/* Step hint overlay */}
        {stepHint && (
          <div className="absolute bottom-2 left-1/2 -translate-x-1/2 bg-black/70 text-yellow-300 text-xs px-3 py-1 rounded-full pointer-events-none">
            {stepHint}
          </div>
        )}
      </div>

      {/* Gate line toolbar */}
      <div className="px-4 py-2 border-t border-[#1e293b] flex items-center gap-2 flex-wrap">
        <span className="text-[10px] text-slate-500 uppercase tracking-widest mr-1">Gate line</span>

        {drawStep === 'off' && (
          <Button size="sm" variant="ghost" onClick={() => setDrawStep('pt_a')}>
            + Draw line
          </Button>
        )}

        {(drawStep === 'pt_a' || drawStep === 'pt_b' || drawStep === 'side') && (
          <Button size="sm" variant="ghost" onClick={() => { setDrawStep('off'); setPtA(null); setPtB(null); setSide(null) }}>
            Cancel
          </Button>
        )}

        {drawStep === 'done' && (
          <>
            <Button size="sm" variant="ghost" onClick={() => setDrawStep('pt_a')}>
              Redraw
            </Button>
            <Button size="sm" variant="ghost" onClick={clearLine}>
              Clear
            </Button>
            <Button
              size="sm" variant="primary"
              onClick={() => saveMut.mutate()}
              disabled={saveMut.isPending || !ptA || !ptB || !side}
            >
              {saved ? 'Saved' : 'Save line'}
            </Button>
            {!side && (
              <span className="text-[10px] text-amber-400">Click gate side to complete</span>
            )}
          </>
        )}

        {drawStep !== 'off' && drawStep !== 'done' && ptA && !ptB && (
          <span className="text-[10px] text-slate-400">Start: {ptA[0].toFixed(2)}, {ptA[1].toFixed(2)}</span>
        )}
        {drawStep !== 'off' && ptA && ptB && !side && (
          <span className="text-[10px] text-slate-400 ml-1">Line set — click the gate side</span>
        )}
        {drawStep === 'done' && ptA && ptB && side && (
          <span className="text-[10px] text-slate-500 ml-1">
            Line saved — yellow = line, green = gate side
          </span>
        )}
      </div>

      {/* Video controls */}
      {isVideo && (
        <div className="px-4 py-3 border-t border-[#1e293b] flex flex-col gap-2">
          {dur > 0 && (
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span className="w-10 text-right shrink-0">{fmtTime(pos)}</span>
              <div
                className="flex-1 py-2 -my-2 relative cursor-pointer"
                onClick={e => {
                  const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect()
                  seekToMut.mutate(Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)) * dur)
                }}
                onMouseMove={e => {
                  const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect()
                  setHoverPct(Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)))
                }}
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

          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" onClick={() => seekToMut.mutate(0)} title="Go to start">⏮</Button>
            <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(-15000)} title="-15s">-15s</Button>
            <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(-5000)} title="-5s">-5s</Button>
            <Button size="sm" variant="ghost" onClick={() => pauseMut.mutate()} disabled={pauseMut.isPending}>
              {paused ? '▶' : '⏸'}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => reverseMut.mutate()} title="Play in reverse"
              className={reverse ? '!bg-violet-600 !text-white' : ''}>⏪</Button>
            <Button size="sm" variant="ghost" onClick={() => stepMut.mutate()}
              title={reverse ? 'Step one frame back' : 'Step one frame'}
              className={paused ? '' : 'invisible'}>⏭</Button>
            <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(5000)} title="+5s">+5s</Button>
            <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(15000)} title="+15s">+15s</Button>
            <div className="flex items-center gap-1 ml-2">
              {SPEEDS.map(s => (
                <button key={s} onClick={() => speedMut.mutate(s)}
                  className={`text-xs px-2 py-1 rounded cursor-pointer transition-colors
                    ${currentSpeed === s
                      ? 'bg-violet-600 text-white'
                      : 'bg-slate-700 text-slate-400 hover:bg-slate-600 hover:text-slate-200'}`}>
                  {s}×
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
