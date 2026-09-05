import { useState, useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createService, updateService, createCounter, deleteCounter, getCounter, getServices } from '../../lib/api'
import type { ServiceConfig, CountingConfig } from '../../lib/types'
import { Modal } from '../ui/Modal'
import { Input } from '../ui/Input'
import { PathInput } from '../ui/PathInput'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'

type ServiceType = 'detection' | 'both' | 'counter'

interface Props {
  open: boolean
  onClose: () => void
  existing?: ServiceConfig         // editing a detection service
  existingCounter?: CountingConfig // editing a standalone counter
}

const defaults: Omit<ServiceConfig, 'name'> = {
  kind: 'detection',
  model_path: '',
  input_mode: 'rtsp',
  input_host: '0.0.0.0',
  input_port: 5050,
  output_host: '127.0.0.1',
  output_port: 6060,
  rtsp_user: 'admin',
  rtsp_password: '',
  rtsp_ip: '192.168.1.1',
  rtsp_port: 554,
  rtsp_channel: 'Streaming/Channels/102',
  rtsp_low_latency: false,
  rtsp_interval: 0.25,
  video_path: '',
  video_loop: true,
  conf_threshold: 0.5,
  gate_trigger_mode: 'off',
  gate_area_threshold: 0,
  gate_line: [],
  gate_line_side: [],
  strict_output: false,
  state_changes_only: false,
  auto_start: false,
  record_stream: false,
  record_dir: '',
  dataset_capture: false,
  dataset_interval: 10,
  dataset_dir: '',
  tcp_push_enabled: false,
  tcp_push_host: '0.0.0.0',
  tcp_push_port: 9001,
  tcp_push_certfile: '',
  tcp_push_keyfile: '',
  tcp_push_ca_certs: '',
  enhance_gamma: 1.0,
  enhance_clahe: false,
  enhance_clahe_clip: 2.0,
  result_car_count: 1,
  udp_port: 5500,
  cache_enabled: false,
  cache_max_seconds: 10,
  cache_max_frames: 30,
  cache_max_bytes: 20_000_000,
  dir_buf_size: 8,
  dir_min_frames: 4,
  dir_miss_tolerance: 2,
  dir_idle_hold: 5,
  dir_signal_threshold: 0.005,
}

// ── Direction sensitivity presets ─────────────────────────────────────────────

const DIR_PRESETS = [
  {
    id: 'stable',
    label: 'Stable',
    desc: 'Slow vehicles, needs reliable output. Less jitter, slower to react.',
    values: { dir_signal_threshold: 0.003, dir_buf_size: 12, dir_min_frames: 6, dir_miss_tolerance: 3, dir_idle_hold: 8 },
  },
  {
    id: 'balanced',
    label: 'Balanced',
    desc: 'Default. Works well for most parking lot cameras.',
    values: { dir_signal_threshold: 0.005, dir_buf_size: 8, dir_min_frames: 4, dir_miss_tolerance: 2, dir_idle_hold: 5 },
  },
  {
    id: 'responsive',
    label: 'Responsive',
    desc: 'Fast vehicles or high frame rate. Reacts quickly, may have more jitter.',
    values: { dir_signal_threshold: 0.008, dir_buf_size: 5, dir_min_frames: 3, dir_miss_tolerance: 1, dir_idle_hold: 3 },
  },
] as const

type DirPresetId = typeof DIR_PRESETS[number]['id']

function getActivePreset(form: ServiceConfig): DirPresetId | 'custom' {
  for (const p of DIR_PRESETS) {
    const v = p.values
    if (
      form.dir_signal_threshold === v.dir_signal_threshold &&
      form.dir_buf_size === v.dir_buf_size &&
      form.dir_min_frames === v.dir_min_frames &&
      form.dir_miss_tolerance === v.dir_miss_tolerance &&
      form.dir_idle_hold === v.dir_idle_hold
    ) return p.id
  }
  return 'custom'
}

function DirSensitivitySection({
  form, setForm, set,
}: {
  form: ServiceConfig
  setForm: React.Dispatch<React.SetStateAction<ServiceConfig>>
  set: (k: keyof ServiceConfig) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => void
}) {
  const [showAdvanced, setShowAdvanced] = useState(false)
  const active = getActivePreset(form)

  const applyPreset = (id: DirPresetId) => {
    const preset = DIR_PRESETS.find(p => p.id === id)!
    setForm(f => ({ ...f, ...preset.values }))
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        {DIR_PRESETS.map(p => (
          <button
            key={p.id}
            type="button"
            onClick={() => applyPreset(p.id)}
            className={`flex-1 px-3 py-2 rounded-lg border text-xs font-medium cursor-pointer transition-colors text-left
              ${active === p.id
                ? 'bg-violet-700/40 border-violet-500/60 text-violet-200'
                : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-600'}`}
          >
            <div className="font-semibold mb-0.5">{p.label}</div>
            <div className={`text-[10px] leading-tight ${active === p.id ? 'text-violet-300/70' : 'text-slate-600'}`}>{p.desc}</div>
          </button>
        ))}
      </div>

      {/* Advanced toggle row */}
      <button
        type="button"
        onClick={() => setShowAdvanced(v => !v)}
        className="flex items-center justify-between w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 hover:border-slate-500 cursor-pointer transition-colors group"
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-slate-300 group-hover:text-slate-100 transition-colors">Advanced settings</span>
          {active === 'custom' && (
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-900/40 border border-amber-700/50 text-amber-400">custom</span>
          )}
        </div>
        <span className="text-slate-500 text-xs transition-transform duration-200" style={{ display: 'inline-block', transform: showAdvanced ? 'rotate(180deg)' : 'rotate(0deg)' }}>▼</span>
      </button>

      {showAdvanced && (
        <div className="flex flex-col gap-4 px-3 pt-1 pb-3 rounded-lg bg-slate-900/60 border border-slate-800">
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-slate-400">Signal threshold</label>
              <span className="text-xs font-mono text-violet-300">{form.dir_signal_threshold.toFixed(4)}</span>
            </div>
            <input
              type="range" min="0.001" max="0.02" step="0.001"
              value={form.dir_signal_threshold}
              onChange={e => setForm(f => ({ ...f, dir_signal_threshold: +e.target.value }))}
              className="w-full accent-violet-500 h-1.5"
            />
            <div className="flex justify-between text-[10px] text-slate-600">
              <span>0.001 — catches slow cars</span>
              <span>0.02 — fast movement only</span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-4">
            <div className="flex flex-col gap-1">
              <Input label="Buffer window" type="number" min="3" max="30" step="1"
                value={form.dir_buf_size} onChange={set('dir_buf_size')} />
              <p className="text-[10px] text-slate-600">Frames kept in history for regression.<br/>More = smoother but slower to react.</p>
            </div>
            <div className="flex flex-col gap-1">
              <Input label="Min frames" type="number" min="2" max="15" step="1"
                value={form.dir_min_frames} onChange={set('dir_min_frames')} />
              <p className="text-[10px] text-slate-600">Frames needed before a direction is reported.<br/>Higher = fewer false reports early on.</p>
            </div>
            <div className="flex flex-col gap-1">
              <Input label="Miss tolerance" type="number" min="1" max="10" step="1"
                value={form.dir_miss_tolerance} onChange={set('dir_miss_tolerance')} />
              <p className="text-[10px] text-slate-600">Consecutive missed detections before history clears.<br/>Higher = survives brief occlusions (poles, trees).</p>
            </div>
            <div className="flex flex-col gap-1">
              <Input label="Idle hold frames" type="number" min="1" max="15" step="1"
                value={form.dir_idle_hold} onChange={set('dir_idle_hold')} />
              <p className="text-[10px] text-slate-600">Idle votes needed to stop reporting a direction.<br/>Higher = less jitter when a car briefly slows down.</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Section({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 pt-2">
      <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest shrink-0">{label}</p>
      <div className="flex-1 h-px bg-slate-800" />
    </div>
  )
}

function Check({ label, checked, onChange, hint }: {
  label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string
}) {
  return (
    <label className="flex items-start gap-2 cursor-pointer select-none">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} className="accent-violet-500 mt-0.5" />
      <div>
        <span className="text-sm text-slate-300">{label}</span>
        {hint && <p className="text-xs text-slate-600 mt-0.5">{hint}</p>}
      </div>
    </label>
  )
}

export function ServiceForm({ open, onClose, existing, existingCounter }: Props) {
  const qc = useQueryClient()
  const isEditDetection = !!existing
  const isEditCounter   = !!existingCounter
  const isEdit          = isEditDetection || isEditCounter

  const [form, setForm]               = useState<ServiceConfig>({ name: '', ...defaults })
  const [serviceType, setServiceType] = useState<ServiceType>('detection')
  const [counterSource, setCounterSource] = useState('')
  const [counterAutoStart, setCounterAutoStart] = useState(false)
  const [initialCount, setInitialCount] = useState(0)
  const [counterOutputHost, setCounterOutputHost] = useState('')
  const [counterOutputPort, setCounterOutputPort] = useState(0)
  const [err, setErr]                 = useState('')
  const wasOpenRef = useRef(false)

  // Detection services available as sources for counter-only mode
  const { data: allServices = [] } = useQuery<ServiceConfig[]>({
    queryKey: ['services'],
    queryFn: getServices,
    enabled: open,
  })

  useEffect(() => {
    const justOpened = open && !wasOpenRef.current
    wasOpenRef.current = open
    if (!justOpened) return   // only initialize when modal first opens, not on every re-render
    setErr('')

    if (existingCounter) {
      // Editing a standalone counter
      setServiceType('counter')
      setCounterSource(existingCounter.source_service)
      setCounterAutoStart(existingCounter.auto_start)
      setCounterOutputHost(existingCounter.output_host ?? '')
      setCounterOutputPort(existingCounter.output_port ?? 0)
      setForm(f => ({ ...f, name: existingCounter.name, auto_start: existingCounter.auto_start }))
      return
    }

    // Editing or creating a detection service — spread defaults first so any
    // fields added after the service was created fall back gracefully.
    setForm(existing ? { ...defaults, ...existing } : { name: '', ...defaults })
    setCounterSource('')
    setInitialCount(0)
    setCounterOutputHost('')
    setCounterOutputPort(0)
    if (existing) {
      if (existing.kind === 'counter') {
        setServiceType('counter')
        getCounter(`${existing.name}_counter`)
          .then((c: CountingConfig) => {
            setInitialCount(c.initial_count ?? 0)
            setCounterOutputHost(c.output_host ?? '')
            setCounterOutputPort(c.output_port ?? 0)
          })
          .catch(() => {})
      } else {
        setServiceType('detection')
        getCounter(`${existing.name}_counter`)
          .then((c: CountingConfig) => {
            setServiceType('both')
            setInitialCount(c.initial_count ?? 0)
            setCounterOutputHost(c.output_host ?? '')
            setCounterOutputPort(c.output_port ?? 0)
          })
          .catch(() => {})
      }
    } else {
      setServiceType('detection')
    }
  }, [open, existing, existingCounter])

  const set    = (k: keyof ServiceConfig) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const val = e.target.type === 'checkbox'
      ? (e.target as HTMLInputElement).checked
      : e.target.type === 'number' ? +e.target.value : e.target.value
    setForm(f => ({ ...f, [k]: val }))
  }
  const setVal  = (k: keyof ServiceConfig) => (v: string) => setForm(f => ({ ...f, [k]: v }))
  const setBool = (k: keyof ServiceConfig) => (v: boolean) => setForm(f => ({ ...f, [k]: v }))

  const rtspUrl = form.input_mode === 'rtsp'
    ? `rtsp://${form.rtsp_user ? `${form.rtsp_user}:***@` : ''}${form.rtsp_ip || '<ip>'}:${form.rtsp_port}/${form.rtsp_channel}`
    : ''

  const mut = useMutation({
    mutationFn: async () => {
      if (serviceType === 'counter') {
        if (isEditCounter) {
          // Editing a standalone external counter (source-based)
          await createCounter({
            name: existingCounter!.name,
            source_service: counterSource,
            auto_start: counterAutoStart,
            output_host: counterOutputHost,
            output_port: counterOutputPort,
          })
          return
        }
        // Counter with own stream: detection service (kind='counter') + auto-created counter
        const svcData = { ...form, kind: 'counter' as const }
        const result = isEditDetection
          ? await updateService(existing!.name, svcData)
          : await createService(svcData)
        const counterName = `${form.name}_counter`
        await createCounter({ name: counterName, source_service: form.name, auto_start: form.auto_start, initial_count: initialCount, output_host: counterOutputHost, output_port: counterOutputPort })
        return result
      }

      // Detection only or Detection + Counter
      const svcData = { ...form, kind: 'detection' as const }
      const result = isEditDetection
        ? await updateService(existing!.name, svcData)
        : await createService(svcData)
      const counterName = `${form.name}_counter`
      if (serviceType === 'both') {
        await createCounter({ name: counterName, source_service: form.name, auto_start: form.auto_start, initial_count: initialCount, output_host: counterOutputHost, output_port: counterOutputPort })
      } else if (isEditDetection) {
        try { await deleteCounter(counterName) } catch { /* not found → ok */ }
      }
      return result
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['services'] })
      qc.invalidateQueries({ queryKey: ['counters'] })
      qc.invalidateQueries({ queryKey: ['counter-status'] })
      onClose()
    },
    onError: (e: unknown) =>
      setErr((e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error saving.'),
  })

  const detectionValid = form.name.trim() !== '' &&
    form.model_path.trim() !== '' &&
    (form.input_mode !== 'rtsp' || (form.rtsp_ip.trim() !== '' && form.rtsp_user.trim() !== '')) &&
    (form.input_mode !== 'video' || form.video_path.trim() !== '') &&
    (!['udp_stream', 'udp_packet'].includes(form.input_mode) || form.udp_port > 0)

  const canSave = isEditCounter
    ? counterSource.trim() !== ''
    : detectionValid

  const modalTitle = isEditCounter
    ? `Edit counter: ${existingCounter!.name}`
    : isEditDetection
      ? `Edit: ${existing!.name}`
      : 'New Service'

  return (
    <Modal open={open} onClose={onClose} title={modalTitle} width="max-w-xl">
      <div className="flex flex-col gap-3 max-h-[82vh] overflow-y-auto pr-1">

        {/* ── Service type selector ── */}
        {/* Show for new services and when editing a detection service; not for standalone counter editing */}
        {!isEditCounter && (
          <>
            <Section label="Service type" />
            <div className="flex gap-1 p-1 bg-slate-800 rounded-lg">
              {([
                { key: 'detection', label: '🔍 Detection only' },
                { key: 'both',      label: '🔍 Detection + 🅿 Counter' },
                { key: 'counter',   label: '🅿 Counter only' },
              ] as const).map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setServiceType(key)}
                  className={`flex-1 py-1.5 rounded text-xs font-medium cursor-pointer transition-colors
                    ${serviceType === key ? 'bg-violet-700 text-white' : 'text-slate-400 hover:text-slate-200'}`}
                >
                  {label}
                </button>
              ))}
            </div>
          </>
        )}

        {/* ── STANDALONE COUNTER form (editing an external-source counter) ── */}
        {isEditCounter && (
          <>
            <div className="flex items-start gap-2 px-3 py-2 bg-teal-900/20 border border-teal-700/30 rounded-lg text-xs text-teal-300">
              <span className="mt-0.5 shrink-0">🅿</span>
              <span>
                Subscribes to an existing detection service and tracks parking occupancy.
                <strong> car forward = +1</strong>, <strong>car_rear forward = −1</strong>, reversals = 0.
              </span>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-slate-400">Source detection service</label>
              {allServices.length > 0 ? (
                <select
                  value={counterSource}
                  onChange={e => setCounterSource(e.target.value)}
                  className="w-full bg-[#1e293b] border border-[#334155] rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-violet-500"
                >
                  <option value="">— select a detection service —</option>
                  {allServices.map(s => (
                    <option key={s.name} value={s.name}>{s.name}</option>
                  ))}
                </select>
              ) : (
                <div className="px-3 py-2 bg-[#1e293b] border border-[#334155] rounded-lg text-xs text-slate-500">
                  No detection services found.
                </div>
              )}
            </div>

            <Section label="Counter output push" />
            <p className="text-xs text-slate-600">Counting events (JSON) are POSTed to /result on each car pass:</p>
            <div className="grid grid-cols-2 gap-3">
              <Input label="Output host" value={counterOutputHost} onChange={e => setCounterOutputHost(e.target.value)} placeholder="127.0.0.1 or leave blank" />
              <Input label="Output port" type="number" value={counterOutputPort} onChange={e => setCounterOutputPort(+e.target.value)} />
            </div>

            <Section label="Other" />
            <Check label="Auto-start when VisionQ server starts"
              checked={counterAutoStart} onChange={setCounterAutoStart} />
          </>
        )}

        {/* ── DETECTION / BOTH / COUNTER-WITH-OWN-STREAM form ── */}
        {!isEditCounter && (
          <>
            {serviceType === 'counter' && (
              <div className="flex items-start gap-2 px-3 py-2 bg-teal-900/20 border border-teal-700/30 rounded-lg text-xs text-teal-300">
                <span className="mt-0.5 shrink-0">🅿</span>
                <span>
                  A counting service with its own stream. Runs YOLO and tracks parking occupancy.
                  A counter named <span className="font-mono text-teal-200">{(form.name || 'service_name') + '_counter'}</span> will be created automatically.
                </span>
              </div>
            )}
            {serviceType === 'both' && (
              <div className="flex items-start gap-2 px-3 py-2 bg-teal-900/20 border border-teal-700/30 rounded-lg text-xs text-teal-300">
                <span className="mt-0.5 shrink-0">🅿</span>
                <span>
                  A parking counter named{' '}
                  <span className="font-mono text-teal-200">{(form.name || 'service_name') + '_counter'}</span>{' '}
                  will be created automatically.
                </span>
              </div>
            )}

            {!isEditDetection && (
              <Input label="Service name" value={form.name} onChange={set('name')}
                placeholder="e.g. gate_1_in, gate_2_out…" autoFocus />
            )}

            <PathInput label="Model path (.pt / .onnx)" value={form.model_path}
              onChange={setVal('model_path')} filter="model"
              placeholder="yolo26n.pt" pickerTitle="Select YOLO model" />

            <Section label="Input source" />
            <div className="flex flex-col gap-1">
              {([
                ['rtsp',       'RTSP camera'],
                ['http',       'HTTP POST'],
                ['video',      'Video file'],
                ['udp_stream', 'UDP stream'],
                ['udp_packet', 'UDP packet'],
              ] as const).map(([m, label]) => (
                <button key={m}
                  type="button"
                  onClick={() => setForm(f => ({ ...f, input_mode: m }))}
                  className={`flex items-center justify-between px-3 py-2.5 rounded-lg border text-left cursor-pointer transition-colors
                    ${form.input_mode === m
                      ? 'bg-violet-700/25 border-violet-500/50 text-violet-100'
                      : 'bg-slate-800/60 border-slate-700/60 text-slate-400 hover:border-slate-600 hover:text-slate-200'}`}
                >
                  <span className="text-xs font-semibold">{label}</span>
                  {form.input_mode === m && (
                    <span className="w-1.5 h-1.5 rounded-full bg-violet-400 shrink-0" />
                  )}
                </button>
              ))}
            </div>

            {form.input_mode === 'rtsp' && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <Input label="Username" value={form.rtsp_user} onChange={set('rtsp_user')} placeholder="admin" />
                  <Input label="Password" type="password" value={form.rtsp_password} onChange={set('rtsp_password')} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Input label="Camera IP" value={form.rtsp_ip} onChange={set('rtsp_ip')} placeholder="192.168.1.1" />
                  <Input label="RTSP port" type="number" value={form.rtsp_port} onChange={set('rtsp_port')} />
                </div>
                <Input label="Channel path" value={form.rtsp_channel} onChange={set('rtsp_channel')}
                  placeholder="Streaming/Channels/102" />
                <Check label="Low latency mode (reduces buffering delay; keep off if stream is unstable)"
                  checked={form.rtsp_low_latency} onChange={setBool('rtsp_low_latency')} />
                <Input label="Frame interval (s)" type="number" step="0.05" min="0.05" max="10"
                  value={form.rtsp_interval} onChange={set('rtsp_interval')} />
                <div className="bg-[#0f172a] border border-[#1e293b] rounded px-3 py-2">
                  <p className="text-[10px] text-slate-600 mb-1">Stream URL preview</p>
                  <p className="text-xs text-slate-400 font-mono break-all">{rtspUrl}</p>
                </div>
              </>
            )}

            {form.input_mode === 'video' && (
              <>
                <PathInput label="Video file" value={form.video_path} onChange={setVal('video_path')}
                  filter="video" placeholder="/data/video.mp4" pickerTitle="Select video file" />
                <Input label="Frame interval (s)" type="number" step="0.05" min="0.05" max="10"
                  value={form.rtsp_interval} onChange={set('rtsp_interval')} />
                <Check label="Loop video" checked={form.video_loop} onChange={setBool('video_loop')} />
              </>
            )}

            {form.input_mode === 'http' && (
              <div className="grid grid-cols-2 gap-3">
                <Input label="Listen host" value={form.input_host} onChange={set('input_host')} placeholder="0.0.0.0" />
                <Input label="Listen port" type="number" value={form.input_port} onChange={set('input_port')} />
              </div>
            )}

            {form.input_mode === 'udp_stream' && (
              <>
                <Input label="UDP listen port" type="number" value={form.udp_port} onChange={set('udp_port')} />
                <Input label="Frame interval (s)" type="number" step="0.05" min="0.05" max="10"
                  value={form.rtsp_interval} onChange={set('rtsp_interval')} />
                <div className="bg-[#0f172a] border border-[#1e293b] rounded px-3 py-2">
                  <p className="text-[10px] text-slate-600 mb-1">Sender command (ffmpeg example)</p>
                  <p className="text-xs text-slate-400 font-mono break-all">
                    {`ffmpeg -i input.mp4 -c:v libx264 -tune zerolatency -f mpegts udp://server-ip:${form.udp_port}`}
                  </p>
                  <p className="text-[10px] text-slate-500 mt-1">Start the service before sending</p>
                </div>
              </>
            )}

            {form.input_mode === 'udp_packet' && (
              <>
                <Input label="UDP listen port" type="number" value={form.udp_port} onChange={set('udp_port')} />
                <div className="bg-[#0f172a] border border-[#1e293b] rounded px-3 py-2 text-xs text-slate-500">
                  Sender sends one JPEG-encoded frame per UDP datagram. Max frame size: 65507 bytes.
                  Use for embedded devices or custom senders at low resolution (e.g. 640×480).
                </div>

                <Check label="Frame cache (backtracking)"
                  checked={form.cache_enabled} onChange={setBool('cache_enabled')}
                  hint="Keep a short rolling buffer of recent frames so clients can fetch what led up to a detection. Adds unauthenticated, token-in-URL frame links to each result." />
                {form.cache_enabled && (
                  <div className="flex flex-col gap-2 pl-6">
                    <div className="grid grid-cols-3 gap-3">
                      <Input label="Max seconds" type="number" min="1" max="60" step="1"
                        value={form.cache_max_seconds} onChange={set('cache_max_seconds')} />
                      <Input label="Max frames" type="number" min="1" max="200" step="1"
                        value={form.cache_max_frames} onChange={set('cache_max_frames')} />
                      <Input label="Max size (bytes)" type="number" min="100000" step="100000"
                        value={form.cache_max_bytes} onChange={set('cache_max_bytes')} />
                    </div>
                    {form.cache_token && (
                      <div className="bg-[#0f172a] border border-[#1e293b] rounded px-3 py-2">
                        <p className="text-[10px] text-slate-600 mb-1">Latest-frame URL (no auth required)</p>
                        <p className="text-xs text-slate-400 font-mono break-all">
                          {`/api/detection/services/${form.name}/cache/latest?token=${form.cache_token}`}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}

            {serviceType !== 'counter' && (
              <>
                <Section label="Output push" />
                <p className="text-xs text-slate-600">Detection results (JSON) are pushed via HTTP POST to:</p>
                <div className="grid grid-cols-2 gap-3">
                  <Input label="Output host" value={form.output_host} onChange={set('output_host')} />
                  <Input label="Output port" type="number" value={form.output_port} onChange={set('output_port')} />
                </div>
              </>
            )}

            <Section label="Settings" />
            <div className="grid grid-cols-2 gap-3">
              <Input label="Confidence threshold" type="number" step="0.05" min="0.01" max="1"
                value={form.conf_threshold} onChange={set('conf_threshold')} />
              {serviceType !== 'detection' && (
                <Input label="Initial count" type="number" min="0" step="1"
                  value={initialCount} onChange={e => setInitialCount(+e.target.value)} />
              )}
            </div>
            {serviceType !== 'counter' && (
              <div className="flex flex-col gap-1">
                <Input label="Cars to report (ranked by size)" type="number" min="1" max="10" step="1"
                  value={form.result_car_count} onChange={set('result_car_count')} />
                <p className="text-xs text-slate-600">
                  How many cars to include in the <span className="font-mono text-slate-400">cars</span> array of each result payload.
                  Rank 1 = closest (largest bbox), rank 2 = second closest, etc.
                </p>
              </div>
            )}

            {serviceType !== 'counter' && (
              <>
                <div className="flex flex-col gap-2">
                  <Check label="State changes only"
                    checked={form.state_changes_only} onChange={setBool('state_changes_only')}
                    hint="Emit output only on state transitions (e.g. idle→forward)" />
                  <Check label="Strict output (known direction only)"
                    checked={form.strict_output} onChange={setBool('strict_output')} />
                </div>

                <Section label="Gate trigger" />
                <div>
                  <p className="text-[10px] font-semibold text-slate-400 mb-1.5">Trigger method</p>
                  <div className="flex gap-2 flex-wrap">
                    {(['off', 'area', 'line'] as const).map(m => (
                      <button key={m} type="button"
                        onClick={() => setForm(f => ({ ...f, gate_trigger_mode: m }))}
                        className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                          form.gate_trigger_mode === m
                            ? 'bg-violet-600 text-white'
                            : 'bg-[#1e293b] text-slate-400 hover:bg-[#334155]'
                        }`}>
                        {m === 'off' ? 'Off' : m === 'area' ? 'Bounding box' : 'Gate line'}
                      </button>
                    ))}
                  </div>
                </div>

                {form.gate_trigger_mode === 'area' && (
                  <>
                    <Input label="Min bounding box area (px²)"
                      type="number" step="10000" min="0"
                      value={form.gate_area_threshold} onChange={set('gate_area_threshold')} />
                    <p className="text-xs text-slate-600">
                      Gate opens when car is idle and bbox area ≥ this value.
                      Use the Debug CSV to read the 'area' column while the car is stationary.
                    </p>
                  </>
                )}

                {form.gate_trigger_mode === 'line' && (
                  <p className="text-xs text-slate-500 bg-[#0f172a] border border-[#1e293b] rounded px-3 py-2">
                    Draw the gate line in the <span className="text-violet-400">Preview</span> panel after starting the service.
                    {form.gate_line?.length === 4
                      ? ' ✓ Line already configured.'
                      : ' No line drawn yet.'}
                  </p>
                )}

                <Section label="TCP push" />
                <Check label="Enable TCP push server"
                  checked={form.tcp_push_enabled} onChange={setBool('tcp_push_enabled')}
                  hint="External systems can connect and receive detection events as newline-delimited JSON over TCP." />
                {form.tcp_push_enabled && (
                  <>
                    <div className="grid grid-cols-2 gap-3">
                      <Input label="Listen host" value={form.tcp_push_host} onChange={set('tcp_push_host')} placeholder="0.0.0.0" />
                      <Input label="Port" type="number" min="1024" max="65535" value={form.tcp_push_port} onChange={set('tcp_push_port')} />
                    </div>
                    <p className="text-xs text-slate-600">TLS — optional. Leave blank for plain TCP.</p>
                    <Input label="Certificate file (.pem) — optional" value={form.tcp_push_certfile} onChange={set('tcp_push_certfile')} placeholder="/etc/certs/server.crt" />
                    <Input label="Key file (.pem) — optional" value={form.tcp_push_keyfile} onChange={set('tcp_push_keyfile')} placeholder="/etc/certs/server.key" />
                    <Input label="CA certs (mTLS) — optional" value={form.tcp_push_ca_certs} onChange={set('tcp_push_ca_certs')} placeholder="/etc/certs/ca.crt" />
                  </>
                )}
              </>
            )}

            <Section label="Direction sensitivity" />
            <DirSensitivitySection form={form} setForm={setForm} set={set} />

            <Section label="Image enhancement" />
            <p className="text-xs text-slate-600">Applied to every frame before YOLO inference. Useful for dark or low-contrast footage.</p>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-slate-400">
                  Gamma: <span className="text-violet-300 font-bold">{form.enhance_gamma.toFixed(2)}</span>
                  <span className="text-slate-600 ml-2">— 1.0 = off · &gt;1.0 = brighter · try 1.5–2.5 for dark footage</span>
                </label>
                <input
                  type="range" min="0.1" max="2.0" step="0.05"
                  value={form.enhance_gamma}
                  onChange={e => setForm(f => ({ ...f, enhance_gamma: +e.target.value }))}
                  className="w-full accent-violet-500 h-1.5"
                />
                <div className="flex justify-between text-[10px] text-slate-600">
                  <span>0.1 — very dark</span>
                  <span>1.0 — off</span>
                  <span>2.0 — very bright</span>
                </div>
              </div>
              <Check
                label="CLAHE — adaptive local contrast"
                checked={form.enhance_clahe}
                onChange={setBool('enhance_clahe')}
                hint="Best for mixed/uneven lighting (e.g. one lamp illuminating part of the lot). Can combine with gamma."
              />
              {form.enhance_clahe && (
                <div className="flex flex-col gap-1.5 pl-5">
                  <label className="text-xs font-medium text-slate-400">
                    Clip limit: <span className="text-violet-300 font-bold">{form.enhance_clahe_clip.toFixed(1)}</span>
                    <span className="text-slate-600 ml-2">— higher = more aggressive (2–8 typical)</span>
                  </label>
                  <input
                    type="range" min="0.5" max="10" step="0.5"
                    value={form.enhance_clahe_clip}
                    onChange={e => setForm(f => ({ ...f, enhance_clahe_clip: +e.target.value }))}
                    className="w-full accent-violet-500 h-1.5"
                  />
                </div>
              )}
            </div>

            <Section label="Dataset capture" />
            <Check label="Save raw frames to dataset folder"
              checked={form.dataset_capture} onChange={setBool('dataset_capture')} />
            {form.dataset_capture && (
              <>
                <Input label="Capture every N frames" type="number" min="1" max="1000"
                  value={form.dataset_interval} onChange={set('dataset_interval')} />
                <PathInput label="Output folder (blank = auto)"
                  value={form.dataset_dir} onChange={setVal('dataset_dir')}
                  filter="dir" dirOnly={true} placeholder="Leave blank for default"
                  pickerTitle="Select dataset folder" />
              </>
            )}

            <Section label="Input recording" />
            <Check label="Auto-start recording when service starts (RTSP/video only)"
              checked={form.record_stream} onChange={setBool('record_stream')}
              hint="Recording FPS is set automatically from the frame interval above." />
            {form.record_stream && (
              <PathInput label="Recording folder (blank = ~/VisionQ_recordings/)"
                value={form.record_dir} onChange={setVal('record_dir')}
                filter="dir" dirOnly={true} placeholder="Leave blank for default"
                pickerTitle="Select recording folder" />
            )}

            {serviceType !== 'detection' && (
              <>
                <Section label="Counter output push" />
                <p className="text-xs text-slate-600">Counting events (JSON) are POSTed to /result on each car pass:</p>
                <div className="grid grid-cols-2 gap-3">
                  <Input label="Output host" value={counterOutputHost} onChange={e => setCounterOutputHost(e.target.value)} placeholder="127.0.0.1 or leave blank" />
                  <Input label="Output port" type="number" value={counterOutputPort} onChange={e => setCounterOutputPort(+e.target.value)} />
                </div>
              </>
            )}

            <Section label="Other" />
            <Check label="Auto-start this service when VisionQ server starts"
              checked={form.auto_start} onChange={setBool('auto_start')} />
          </>
        )}

        {err && <p className="text-xs text-red-400">{err}</p>}
      </div>

      <div className="flex gap-2 justify-end pt-4 border-t border-slate-700 mt-3">
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={() => mut.mutate()} disabled={mut.isPending || !canSave}>
          {mut.isPending ? <Spinner size={12} /> : null}
          {isEdit ? 'Save' : '▶  Save & Start'}
        </Button>
      </div>
    </Modal>
  )
}
