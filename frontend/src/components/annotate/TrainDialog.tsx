import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { trainModel } from '../../lib/api'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { Spinner } from '../ui/Spinner'
import { useJobPoller } from '../../lib/useJobPoller'

interface Props { open: boolean; onClose: () => void }

export function TrainDialog({ open, onClose }: Props) {
  const [form, setForm] = useState({
    data_yaml: '', model: 'yolo11n.pt', epochs: '100',
    batch: '16', imgsz: '640', patience: '50', output_dir: '', device: '',
  })
  const [jobId, setJobId] = useState<string | null>(null)
  const job = useJobPoller(jobId)

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const mut = useMutation({
    mutationFn: () => trainModel({
      ...form,
      epochs: +form.epochs,
      batch: +form.batch,
      imgsz: +form.imgsz,
      patience: +form.patience,
    }),
    onSuccess: (data) => setJobId(data.job_id),
  })

  return (
    <Modal open={open} onClose={onClose} title="Train YOLO Model" width="max-w-md">
      <div className="flex flex-col gap-3">
        <Input label="data.yaml path" value={form.data_yaml} onChange={set('data_yaml')} placeholder="/data/export/data.yaml" />
        <Input label="Base model" value={form.model} onChange={set('model')} placeholder="yolo11n.pt" />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Epochs" type="number" value={form.epochs} onChange={set('epochs')} />
          <Input label="Batch size" type="number" value={form.batch} onChange={set('batch')} />
          <Input label="Image size" type="number" value={form.imgsz} onChange={set('imgsz')} />
          <Input label="Patience" type="number" value={form.patience} onChange={set('patience')} />
        </div>
        <Input label="Output dir (optional)" value={form.output_dir} onChange={set('output_dir')} />
        <Input label="Device (cpu/cuda/mps, blank=auto)" value={form.device} onChange={set('device')} />

        {job && (
          <div className={`text-xs px-3 py-2 rounded ${job.status === 'done' ? 'bg-green-900/30 text-green-300' : job.status === 'failed' ? 'bg-red-900/30 text-red-300' : 'bg-slate-800 text-slate-400'}`}>
            {job.status === 'running' && <span className="flex items-center gap-2"><Spinner size={12} /> Training… (this takes a while)</span>}
            {job.status === 'done' && `Done! Best model: ${(job.result as { best_model?: string })?.best_model}`}
            {job.status === 'failed' && `Error: ${job.error}`}
          </div>
        )}

        <div className="flex gap-2 justify-end pt-1">
          <Button variant="ghost" onClick={onClose}>Close</Button>
          {!job && (
            <Button variant="primary" onClick={() => mut.mutate()} disabled={mut.isPending || !form.data_yaml}>
              {mut.isPending ? <Spinner size={12} /> : null}
              Start Training
            </Button>
          )}
        </div>
      </div>
    </Modal>
  )
}
