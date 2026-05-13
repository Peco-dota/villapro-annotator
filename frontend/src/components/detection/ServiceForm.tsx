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
  rtsp_interval: 0.25,
  video_path: '',
  video_loop: true,
  conf_threshold: 0.5,
  gate_area_threshold: 0,
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

    // Editing or creating a detection service
    setForm(existing ? { ...existing } : { name: '', ...defaults })
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
    (form.input_mode !== 'video' || form.video_path.trim() !== '')

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
            <div className="flex gap-1 p-1 bg-slate-800 rounded-lg">
              {(['http', 'rtsp', 'video'] as const).map(m => (
                <button key={m}
                  onClick={() => setForm(f => ({ ...f, input_mode: m }))}
                  className={`flex-1 py-1.5 rounded text-xs font-medium cursor-pointer transition-colors
                    ${form.input_mode === m ? 'bg-violet-700 text-white' : 'text-slate-400 hover:text-slate-200'}`}
                >
                  {m === 'http' ? 'HTTP endpoint' : m === 'rtsp' ? 'RTSP camera' : 'Video file'}
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
              <>
                <div className="flex flex-col gap-2">
                  <Check label="State changes only"
                    checked={form.state_changes_only} onChange={setBool('state_changes_only')}
                    hint="Emit output only on state transitions (e.g. idle→forward)" />
                  <Check label="Strict output (known direction only)"
                    checked={form.strict_output} onChange={setBool('strict_output')} />
                </div>

                <Section label="Gate trigger" />
                <Input label="Min bounding box area (px²) — 0 = disabled"
                  type="number" step="10000" min="0"
                  value={form.gate_area_threshold} onChange={set('gate_area_threshold')} />
                <p className="text-xs text-slate-600">
                  Emit gate_open=true when a car is idle and its bbox area ≥ this value (px²).
                  Use the Debug CSV to read the 'area' column while the car is stationary.
                </p>

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
