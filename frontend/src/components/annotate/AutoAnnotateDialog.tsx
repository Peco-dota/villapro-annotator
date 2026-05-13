import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { autoAnnotate, cancelJob } from '../../lib/api'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { PathInput } from '../ui/PathInput'
import { Spinner } from '../ui/Spinner'
import { useJobPoller } from '../../lib/useJobPoller'

interface Props {
  open: boolean
  onClose: () => void
  projectPath: string
}

export function AutoAnnotateDialog({ open, onClose, projectPath }: Props) {
  const qc = useQueryClient()
  const [modelPath, setModelPath] = useState('')
  const [confidence, setConfidence] = useState(0.25)
  const [skipAnnotated, setSkipAnnotated] = useState(true)
  const [jobId, setJobId] = useState<string | null>(null)

  const job = useJobPoller(jobId)

  const mut = useMutation({
    mutationFn: () => autoAnnotate({ project_path: projectPath, model_path: modelPath, confidence, skip_annotated: skipAnnotated }),
    onSuccess: (data) => setJobId(data.job_id),
  })

  const cancelMut = useMutation({ mutationFn: () => cancelJob(jobId!) })

  const isDone    = job?.status === 'done'
  const isFailed  = job?.status === 'failed'
  const isRunning = job?.status === 'running'
  const progress  = job?.progress ?? 0
  const total     = job?.total ?? 0

  const handleClose = () => {
    if (isDone) {
      qc.invalidateQueries({ queryKey: ['images', projectPath] })
      qc.invalidateQueries({ queryKey: ['annotations', projectPath] })
      qc.invalidateQueries({ queryKey: ['project', projectPath] })
    }
    setJobId(null)
    mut.reset()
    onClose()
  }

  return (
    <Modal open={open} onClose={handleClose} title="Auto-Annotate Project" width="max-w-md">
      <div className="flex flex-col gap-4">

        {!jobId ? (
          <>
            <PathInput
              label="YOLO model (.pt file)"
              value={modelPath}
              onChange={setModelPath}
              filter="model"
              placeholder="/path/to/best.pt"
              pickerTitle="Select YOLO model file"
            />

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-slate-400">
                Confidence threshold: <span className="text-violet-300 font-bold">{confidence.toFixed(2)}</span>
              </label>
              <input
                type="range" min="0.05" max="0.95" step="0.05"
                value={confidence}
                onChange={e => setConfidence(+e.target.value)}
                className="w-full accent-violet-500 h-1.5"
              />
              <div className="flex justify-between text-[10px] text-slate-600">
                <span>0.05 — more boxes</span>
                <span>0.95 — fewer, high-conf only</span>
              </div>
            </div>

            <label className="flex items-center gap-2.5 cursor-pointer text-sm text-slate-300">
              <input
                type="checkbox"
                checked={skipAnnotated}
                onChange={e => setSkipAnnotated(e.target.checked)}
                className="accent-violet-500 w-3.5 h-3.5"
              />
              Skip images that already have annotations
            </label>

            <p className="text-xs text-slate-500 bg-[#0f172a] rounded px-3 py-2">
              The model's class indices map directly to your project classes.
              Class 0 → your first class, class 1 → second class, etc.
            </p>

            {mut.isError && (
              <p className="text-xs text-red-400">{String((mut.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? mut.error)}</p>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <Button variant="ghost" onClick={handleClose}>Cancel</Button>
              <Button
                variant="primary"
                onClick={() => mut.mutate()}
                disabled={!modelPath || mut.isPending}
              >
                {mut.isPending ? <><Spinner size={12} />&nbsp;Starting…</> : '▶ Run Auto-Annotate'}
              </Button>
            </div>
          </>
        ) : (
          <>
            {isRunning && (
              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-slate-300">
                    <Spinner size={14} />
                    <span className="text-sm">
                      Annotating {total > 0 ? `${progress} / ${total}` : progress} images…
                    </span>
                  </div>
                  <button
                    onClick={() => cancelMut.mutate()}
                    disabled={cancelMut.isPending}
                    className="text-xs text-slate-500 hover:text-red-400 cursor-pointer transition-colors"
                  >
                    Cancel
                  </button>
                </div>
                {total > 0 && (
                  <div className="w-full h-2 bg-[#1e293b] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-violet-600 rounded-full transition-all duration-300"
                      style={{ width: `${(progress / total) * 100}%` }}
                    />
                  </div>
                )}
              </div>
            )}

            {isDone && (
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-2 text-green-400">
                  <span className="text-xl">✓</span>
                  <span className="text-sm font-semibold">Auto-annotation complete</span>
                </div>
                <div className="bg-[#0f172a] rounded-lg px-4 py-3 flex flex-col gap-2">
                  {[
                    { label: 'Images annotated', value: Number(job.result?.images_annotated ?? 0), color: 'text-violet-400' },
                    { label: 'Bounding boxes created', value: Number(job.result?.boxes_created ?? 0), color: 'text-violet-400' },
                    { label: 'Total images processed', value: Number(job.result?.total_images ?? 0), color: 'text-slate-500' },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="flex justify-between text-sm text-slate-300">
                      <span>{label}</span>
                      <span className={`font-bold font-mono ${color}`}>{value}</span>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-slate-500">
                  Review each image in the canvas and correct any bad boxes. Use <kbd className="bg-[#1e293b] px-1 py-0.5 rounded text-[10px] font-mono">Ctrl+Z</kbd> to undo changes on the current image.
                </p>
              </div>
            )}

            {isFailed && (
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-2 text-red-400">
                  <span>✕</span>
                  <span className="text-sm font-semibold">Auto-annotation failed</span>
                </div>
                <pre className="bg-[#0f172a] rounded px-3 py-2 text-xs text-red-300 overflow-auto max-h-48 whitespace-pre-wrap">
                  {job?.error}
                </pre>
              </div>
            )}

            {(isDone || isFailed) && (
              <div className="flex justify-end pt-1">
                <Button variant="primary" onClick={handleClose}>Close</Button>
              </div>
            )}
          </>
        )}
      </div>
    </Modal>
  )
}
