import { useMemo, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  getMjpegStreamUrl, getVideoState,
  videoPause, videoSpeed, videoSeek, videoSeekTo, videoStep,
} from '../../lib/api'
import type { ServiceConfig } from '../../lib/types'
import { Button } from '../ui/Button'

interface Props {
  service: ServiceConfig
  onClose: () => void
}

const SPEEDS = [0.5, 1, 2, 4]

export function PreviewWindow({ service, onClose }: Props) {
  const mjpegUrl = useMemo(() => getMjpegStreamUrl(service.name), [service.name])
  const isVideo = service.input_mode === 'video'

  // Video state (position, duration, speed, paused) — only for video mode
  const { data: videoState, refetch: refetchVideo } = useQuery({
    queryKey: ['video-state', service.name],
    queryFn: () => getVideoState(service.name),
    enabled: isVideo,
    refetchInterval: isVideo ? 500 : false,
  })

  const pauseMut = useMutation({
    mutationFn: () => videoPause(service.name),
    onSuccess: () => refetchVideo(),
  })
  const speedMut = useMutation({
    mutationFn: (s: number) => videoSpeed(service.name, s),
    onSuccess: () => refetchVideo(),
  })
  const seekMut = useMutation({
    mutationFn: (delta: number) => videoSeek(service.name, delta),
    onSuccess: () => refetchVideo(),
  })
  const seekToMut = useMutation({
    mutationFn: (ms: number) => videoSeekTo(service.name, ms),
    onSuccess: () => refetchVideo(),
  })
  const stepMut = useMutation({
    mutationFn: () => videoStep(service.name),
  })

  const fmtTime = (ms: number) => {
    const s = Math.floor(ms / 1000)
    const m = Math.floor(s / 60)
    return `${m}:${String(s % 60).padStart(2, '0')}`
  }

  const pos = videoState?.pos_ms ?? 0
  const dur = videoState?.duration_ms ?? 0
  const paused = videoState?.paused ?? false
  const currentSpeed = videoState?.speed ?? 1

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

      {/* Frame — MJPEG stream: browser keeps one persistent connection, server pushes frames */}
      <div className="relative bg-black flex items-center justify-center overflow-hidden" style={{ minHeight: 240 }}>
        <img
          src={mjpegUrl}
          alt="preview"
          className="max-w-full max-h-[60vh] object-contain"
        />
      </div>

      {/* Video controls — only shown in video mode */}
      {isVideo && (
        <div className="px-4 py-3 border-t border-[#1e293b] flex flex-col gap-2">
          {/* Progress bar */}
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

          {/* Controls row */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Seek buttons */}
            <Button size="sm" variant="ghost" onClick={() => seekToMut.mutate(0)} title="Go to start">⏮</Button>
            <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(-15000)} title="-15s">-15s</Button>
            <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(-5000)} title="-5s">-5s</Button>

            {/* Pause/Play */}
            <Button size="sm" variant="ghost" onClick={() => pauseMut.mutate()} disabled={pauseMut.isPending}>
              {paused ? '▶' : '⏸'}
            </Button>

            {/* Step frame (only while paused) */}
            {paused && (
              <Button size="sm" variant="ghost" onClick={() => stepMut.mutate()} title="Step one frame">⏭</Button>
            )}

            <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(5000)} title="+5s">+5s</Button>
            <Button size="sm" variant="ghost" onClick={() => seekMut.mutate(15000)} title="+15s">+15s</Button>

            {/* Speed */}
            <div className="flex items-center gap-1 ml-2">
              {SPEEDS.map(s => (
                <button
                  key={s}
                  onClick={() => speedMut.mutate(s)}
                  className={`text-xs px-2 py-1 rounded cursor-pointer transition-colors
                    ${currentSpeed === s
                      ? 'bg-violet-600 text-white'
                      : 'bg-slate-700 text-slate-400 hover:bg-slate-600 hover:text-slate-200'
                    }`}
                >
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
