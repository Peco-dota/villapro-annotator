import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createService, updateService } from '../../lib/api'
import type { ServiceConfig } from '../../lib/types'
import { Modal } from '../ui/Modal'
import { Input } from '../ui/Input'
import { PathInput } from '../ui/PathInput'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'

interface Props {
  open: boolean
  onClose: () => void
  existing?: ServiceConfig
}

const defaults: Omit<ServiceConfig, 'name'> = {
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

function Check({ label, checked, onChange, hint }: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string }) {
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

export function ServiceForm({ open, onClose, existing }: Props) {
  const qc = useQueryClient()
  const isEdit = !!existing
  const [form, setForm] = useState<ServiceConfig>({ name: '', ...defaults })
  const [err, setErr] = useState('')

  useEffect(() => {
    if (open) {
      setErr('')
      setForm(existing ? { ...existing } : { name: '', ...defaults })
    }
  }, [open, existing])

  const set = (k: keyof ServiceConfig) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const val = e.target.type === 'checkbox'
      ? (e.target as HTMLInputElement).checked
      : e.target.type === 'number' ? +e.target.value : e.target.value
    setForm(f => ({ ...f, [k]: val }))
  }
  const setVal = (k: keyof ServiceConfig) => (v: string) => setForm(f => ({ ...f, [k]: v }))
  const setBool = (k: keyof ServiceConfig) => (v: boolean) => setForm(f => ({ ...f, [k]: v }))

  // Computed RTSP URL preview
  const rtspUrl = form.input_mode === 'rtsp'
    ? `rtsp://${form.rtsp_user ? `${form.rtsp_user}:***@` : ''}${form.rtsp_ip || '<ip>'}:${form.rtsp_port}/${form.rtsp_channel}`
    : ''

  const mut = useMutation({
    mutationFn: () => isEdit ? updateService(existing!.name, form) : createService(form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['services'] }); onClose() },
    onError: (e: unknown) => setErr((e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error saving service.'),
  })

  const canSave = form.name.trim() &&
    form.model_path.trim() &&
    (form.input_mode !== 'rtsp' || (form.rtsp_ip.trim() && form.rtsp_user.trim())) &&
    (form.input_mode !== 'video' || form.video_path.trim())

  return (
    <Modal open={open} onClose={onClose} title={isEdit ? `Edit: ${existing!.name}` : 'New Detection Service'} width="max-w-xl">
      <div className="flex flex-col gap-3 max-h-[82vh] overflow-y-auto pr-1">

        {/* Name */}
        {!isEdit && (
          <Input label="Service name" value={form.name} onChange={set('name')}
            placeholder="e.g. gate_1_in, gate_2_out…" autoFocus />
        )}

        {/* Model */}
        <PathInput label="Model path (.pt / .onnx)" value={form.model_path}
          onChange={setVal('model_path')} filter="model"
          placeholder="yolo26n.pt" pickerTitle="Select YOLO model" />

        {/* ── Input source ── */}
        <Section label="Input source" />

        {/* Mode selector */}
        <div className="flex gap-1 p-1 bg-slate-800 rounded-lg">
          {(['http', 'rtsp', 'video'] as const).map(m => (
            <button
              key={m}
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
            {/* RTSP URL preview */}
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

        {/* ── Output ── */}
        <Section label="Output push" />
        <p className="text-xs text-slate-600">Detection results (JSON) are pushed via HTTP POST to:</p>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Output host" value={form.output_host} onChange={set('output_host')} />
          <Input label="Output port" type="number" value={form.output_port} onChange={set('output_port')} />
        </div>

        {/* ── Detection settings ── */}
        <Section label="Detection settings" />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Confidence threshold" type="number" step="0.05" min="0.01" max="1"
            value={form.conf_threshold} onChange={set('conf_threshold')} />
        </div>
        <div className="flex flex-col gap-2">
          <Check label="State changes only"
            checked={form.state_changes_only} onChange={setBool('state_changes_only')}
            hint="Emit output only on state transitions (e.g. idle→forward)" />
          <Check label="Strict output (known direction only)"
            checked={form.strict_output} onChange={setBool('strict_output')} />
        </div>

        {/* ── Gate trigger ── */}
        <Section label="Gate trigger" />
        <Input
          label="Min bounding box area (px²) — 0 = disabled"
          type="number" step="10000" min="0"
          value={form.gate_area_threshold} onChange={set('gate_area_threshold')}
        />
        <p className="text-xs text-slate-600">
          Emit gate_open=true when a car is idle and its bbox area ≥ this value (px²).
          Set to 0 to disable. Use the Debug CSV to read the 'area' column while the car is stationary.
        </p>

        {/* ── Dataset capture ── */}
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

        {/* ── Recording ── */}
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

        {/* ── TCP push ── */}
        <Section label="TCP push" />
        <Check
          label="Enable TCP push server"
          checked={form.tcp_push_enabled} onChange={setBool('tcp_push_enabled')}
          hint="Other systems (gate controllers, alarm panels…) can connect and receive detection events as JSON lines over a raw TCP socket."
        />
        {form.tcp_push_enabled && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Input label="Listen host" value={form.tcp_push_host} onChange={set('tcp_push_host')} placeholder="0.0.0.0" />
              <Input label="Port" type="number" min="1024" max="65535" value={form.tcp_push_port} onChange={set('tcp_push_port')} />
            </div>
            <p className="text-xs text-slate-600">
              TLS — optional. Leave blank for plain TCP. If set, both cert and key are required.
            </p>
            <Input label="Certificate file (.pem) — optional" value={form.tcp_push_certfile} onChange={set('tcp_push_certfile')} placeholder="/etc/certs/server.crt" />
            <Input label="Key file (.pem) — optional" value={form.tcp_push_keyfile} onChange={set('tcp_push_keyfile')} placeholder="/etc/certs/server.key" />
            <Input label="CA certs (mTLS) — optional" value={form.tcp_push_ca_certs} onChange={set('tcp_push_ca_certs')} placeholder="/etc/certs/ca.crt" />
          </>
        )}

        {/* ── Misc ── */}
        <Section label="Other" />
        <Check label="Auto-start this service when VisionQ server starts"
          checked={form.auto_start} onChange={setBool('auto_start')} />

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
