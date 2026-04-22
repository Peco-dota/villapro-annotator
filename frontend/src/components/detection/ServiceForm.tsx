import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createService, updateService } from '../../lib/api'
import type { ServiceConfig } from '../../lib/types'
import { Modal } from '../ui/Modal'
import { Input } from '../ui/Input'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'

interface Props {
  open: boolean
  onClose: () => void
  existing?: ServiceConfig
}

const defaults: Omit<ServiceConfig, 'name'> = {
  model_path: 'yolo11n.pt',
  mode: 'rtsp',
  source: '',
  confidence: 0.5,
  iou: 0.45,
  device: '',
  imgsz: 640,
  classes: [],
  gate_area_threshold: 0.15,
  auto_start: false,
  record_video: false,
  record_dir: '',
  debug_csv: false,
  tcp_host: '0.0.0.0',
  tcp_port: 9000,
  tcp_ssl: false,
  preview: false,
}

export function ServiceForm({ open, onClose, existing }: Props) {
  const qc = useQueryClient()
  const [form, setForm] = useState<ServiceConfig>(existing ?? { name: '', ...defaults })
  const [err, setErr] = useState('')

  const set = (k: keyof ServiceConfig) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const val = e.target.type === 'checkbox'
      ? (e.target as HTMLInputElement).checked
      : e.target.type === 'number' ? +e.target.value : e.target.value
    setForm(f => ({ ...f, [k]: val }))
  }

  const mut = useMutation({
    mutationFn: () => existing
      ? updateService(existing.name, form)
      : createService(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['services'] })
      onClose()
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error'
      setErr(msg)
    },
  })

  return (
    <Modal open={open} onClose={onClose} title={existing ? `Edit: ${existing.name}` : 'New Detection Service'} width="max-w-lg">
      <div className="flex flex-col gap-3 max-h-[70vh] overflow-y-auto pr-1">
        {!existing && <Input label="Service name" value={form.name} onChange={set('name')} placeholder="camera-1" />}
        <Input label="Model path" value={form.model_path} onChange={set('model_path')} placeholder="yolo11n.pt" />

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Mode</label>
          <select
            value={form.mode}
            onChange={set('mode')}
            className="bg-slate-800 border border-slate-600 rounded px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-violet-500"
          >
            <option value="rtsp">RTSP</option>
            <option value="video">Video file</option>
            <option value="http">HTTP POST</option>
          </select>
        </div>

        {form.mode !== 'http' && (
          <Input label="Source URL / file path" value={form.source} onChange={set('source')} placeholder="rtsp://... or /path/to/video.mp4" />
        )}

        <div className="grid grid-cols-2 gap-3">
          <Input label="Confidence" type="number" step="0.05" min="0" max="1" value={form.confidence} onChange={set('confidence')} />
          <Input label="IoU" type="number" step="0.05" min="0" max="1" value={form.iou} onChange={set('iou')} />
          <Input label="Image size" type="number" value={form.imgsz} onChange={set('imgsz')} />
          <Input label="Gate area threshold" type="number" step="0.01" value={form.gate_area_threshold} onChange={set('gate_area_threshold')} />
        </div>

        <Input label="Device (cpu/cuda/mps, blank=auto)" value={form.device} onChange={set('device')} />

        <div className="grid grid-cols-2 gap-3">
          <Input label="TCP host" value={form.tcp_host} onChange={set('tcp_host')} />
          <Input label="TCP port" type="number" value={form.tcp_port} onChange={set('tcp_port')} />
        </div>

        <div className="grid grid-cols-2 gap-2 pt-1">
          {([
            ['auto_start', 'Auto-start'],
            ['record_video', 'Record video'],
            ['debug_csv', 'Debug CSV'],
            ['tcp_ssl', 'TCP SSL'],
            ['preview', 'Preview'],
          ] as [keyof ServiceConfig, string][]).map(([k, label]) => (
            <label key={k} className="flex items-center gap-2 cursor-pointer text-sm text-slate-300">
              <input type="checkbox" checked={!!form[k]} onChange={set(k)} className="accent-violet-500" />
              {label}
            </label>
          ))}
        </div>

        {form.record_video && (
          <Input label="Record output dir" value={form.record_dir} onChange={set('record_dir')} />
        )}

        {err && <p className="text-xs text-red-400">{err}</p>}
      </div>

      <div className="flex gap-2 justify-end pt-4 border-t border-slate-700 mt-3">
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={() => mut.mutate()} disabled={mut.isPending || !form.name}>
          {mut.isPending ? <Spinner size={12} /> : null}
          {existing ? 'Save' : 'Create'}
        </Button>
      </div>
    </Modal>
  )
}
