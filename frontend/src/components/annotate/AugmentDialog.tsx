import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { augmentProject } from '../../lib/api'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { PathInput } from '../ui/PathInput'
import { Spinner } from '../ui/Spinner'
import { useJobPoller } from '../../lib/useJobPoller'

interface Props { open: boolean; onClose: () => void; projectPath: string }

const toggle = (label: string, value: boolean, onChange: (v: boolean) => void) => (
  <label className="flex items-center gap-2 cursor-pointer text-sm text-slate-300">
    <input type="checkbox" checked={value} onChange={e => onChange(e.target.checked)} className="accent-violet-500" />
    {label}
  </label>
)

export function AugmentDialog({ open, onClose, projectPath }: Props) {
  const [outputDir, setOutputDir] = useState('')
  const [copies, setCopies] = useState('2')
  const [opts, setOpts] = useState({
    flip_horizontal: true, flip_vertical: false,
    brightness: true, contrast: true, saturation: true,
    blur: false, noise: false, rotation: false,
  })
  const [jobId, setJobId] = useState<string | null>(null)
  const job = useJobPoller(jobId)

  const set = (k: keyof typeof opts) => (v: boolean) => setOpts(o => ({ ...o, [k]: v }))

  const mut = useMutation({
    mutationFn: () => augmentProject({
      project_path: projectPath,
      output_dir: outputDir,
      copies_per_image: +copies,
      ...opts,
    }),
    onSuccess: (data) => setJobId(data.job_id),
  })

  const reset = () => { setJobId(null); mut.reset() }

  return (
    <Modal open={open} onClose={() => { reset(); onClose() }} title="Augment Dataset" width="max-w-sm">
      <div className="flex flex-col gap-3">
        <PathInput
          label="Output directory"
          value={outputDir}
          onChange={setOutputDir}
          filter="dir"
          dirOnly={true}
          placeholder="/data/augmented/"
          pickerTitle="Select augmentation output folder"
        />
        <Input label="Copies per image" type="number" min="1" max="20" value={copies} onChange={e => setCopies(e.target.value)} />

        <div className="grid grid-cols-2 gap-2 pt-1">
          {toggle('Flip horizontal', opts.flip_horizontal, set('flip_horizontal'))}
          {toggle('Flip vertical', opts.flip_vertical, set('flip_vertical'))}
          {toggle('Brightness', opts.brightness, set('brightness'))}
          {toggle('Contrast', opts.contrast, set('contrast'))}
          {toggle('Saturation', opts.saturation, set('saturation'))}
          {toggle('Blur', opts.blur, set('blur'))}
          {toggle('Noise', opts.noise, set('noise'))}
          {toggle('Rotation', opts.rotation, set('rotation'))}
        </div>

        {job && (
          <div className={`text-xs px-3 py-2 rounded ${job.status === 'done' ? 'bg-green-900/30 text-green-300' : job.status === 'failed' ? 'bg-red-900/30 text-red-300' : 'bg-slate-800 text-slate-400'}`}>
            {job.status === 'running' && <span className="flex items-center gap-2"><Spinner size={12} /> Augmenting…</span>}
            {job.status === 'done' && `Done! ${JSON.stringify(job.result)}`}
            {job.status === 'failed' && `Error: ${job.error}`}
          </div>
        )}

        <div className="flex gap-2 justify-end">
          <Button variant="ghost" onClick={() => { reset(); onClose() }}>Close</Button>
          {!job && (
            <Button variant="primary" onClick={() => mut.mutate()} disabled={mut.isPending || !outputDir}>
              {mut.isPending ? <Spinner size={12} /> : null}
              Augment
            </Button>
          )}
        </div>
      </div>
    </Modal>
  )
}
