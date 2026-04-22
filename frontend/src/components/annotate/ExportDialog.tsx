import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { exportYolo, exportCoco } from '../../lib/api'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { Spinner } from '../ui/Spinner'
import { useJobPoller } from '../../lib/useJobPoller'

interface Props {
  open: boolean
  onClose: () => void
  projectPath: string
}

export function ExportDialog({ open, onClose, projectPath }: Props) {
  const [format, setFormat] = useState<'yolo' | 'coco'>('yolo')
  const [outputDir, setOutputDir] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const job = useJobPoller(jobId)

  const mut = useMutation({
    mutationFn: () =>
      format === 'yolo'
        ? exportYolo({ project_path: projectPath, output_dir: outputDir, generate_yaml: true })
        : exportCoco({ project_path: projectPath, output_dir: outputDir }),
    onSuccess: (data) => setJobId(data.job_id),
  })

  const reset = () => { setJobId(null); mut.reset() }

  return (
    <Modal open={open} onClose={() => { reset(); onClose() }} title="Export Dataset" width="max-w-sm">
      <div className="flex flex-col gap-4">
        <div className="flex gap-2">
          {(['yolo', 'coco'] as const).map(f => (
            <button
              key={f}
              onClick={() => setFormat(f)}
              className={`flex-1 py-1.5 text-xs rounded border transition-colors cursor-pointer font-medium uppercase tracking-wider
                ${format === f ? 'bg-violet-600 border-violet-500 text-white' : 'bg-slate-800 border-slate-600 text-slate-400 hover:border-violet-500'}`}
            >{f}</button>
          ))}
        </div>
        <Input label="Output directory" value={outputDir} onChange={e => setOutputDir(e.target.value)} placeholder="/data/export/" />

        {job && (
          <div className={`text-xs px-3 py-2 rounded ${job.status === 'done' ? 'bg-green-900/30 text-green-300' : job.status === 'failed' ? 'bg-red-900/30 text-red-300' : 'bg-slate-800 text-slate-400'}`}>
            {job.status === 'running' && <span className="flex items-center gap-2"><Spinner size={12} /> Exporting…</span>}
            {job.status === 'done' && `Done! ${JSON.stringify(job.result)}`}
            {job.status === 'failed' && `Error: ${job.error}`}
          </div>
        )}

        <div className="flex gap-2 justify-end">
          <Button variant="ghost" onClick={() => { reset(); onClose() }}>Close</Button>
          {!job && (
            <Button variant="primary" onClick={() => mut.mutate()} disabled={mut.isPending || !outputDir}>
              {mut.isPending ? <Spinner size={12} /> : null}
              Export
            </Button>
          )}
        </div>
      </div>
    </Modal>
  )
}
