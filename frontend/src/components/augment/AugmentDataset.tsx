import { useState, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api, cancelJob, getActiveAugJob } from '../../lib/api'
import { Button } from '../ui/Button'
import { PathInput } from '../ui/PathInput'
import { Spinner } from '../ui/Spinner'
import { useJobPoller } from '../../lib/useJobPoller'
import { AugmentSettings, augmentConfigToPayload, DEFAULT_AUGMENT } from './AugmentSettings'
import type { AugmentConfig } from './AugmentSettings'

function SectionHeader({ label }: { label: string }) {
  return <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">{label}</p>
}

const augmentFolder = (data: object) =>
  api.post('/api/datasets/augment/folder', data).then(r => r.data)

export function AugmentDataset() {
  const [folder, setFolder] = useState('')
  const [config, setConfig] = useState<AugmentConfig>(DEFAULT_AUGMENT)

  const [jobId, setJobId] = useState<string | null>(null)
  const job = useJobPoller(jobId)

  // Restore any in-progress job when navigating back to this tab
  useEffect(() => {
    getActiveAugJob().then(data => {
      if (data.active && data.job_id) {
        setJobId(data.job_id)
        if (data.folder) setFolder(data.folder)
      }
    }).catch(() => {})
  }, [])

  const mut = useMutation({
    mutationFn: () => augmentFolder({ folder, ...augmentConfigToPayload(config) }),
    onSuccess: (data: { job_id: string }) => setJobId(data.job_id),
  })

  const isDone = job?.status === 'done'
  const isFailed = job?.status === 'failed'
  const isCancelled = isFailed && job?.error === 'Cancelled'
  const isRunning = mut.isPending || job?.status === 'running'
  const result = job?.result as { augmented?: number; skipped?: number } | null

  const [cancelling, setCancelling] = useState(false)
  const handleCancel = () => {
    if (!jobId) return
    setCancelling(true)
    cancelJob(jobId).finally(() => setCancelling(false))
  }

  const reset = () => { setJobId(null); mut.reset(); setCancelling(false) }

  const canRun = !!folder && !isRunning && !isDone

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <div>
        <h2 className="text-base font-semibold text-slate-100 mb-1">Augment Dataset</h2>
        <p className="text-sm text-slate-500">
          Enrich an already-exported dataset by generating augmented copies of existing images.
          Point to the dataset root folder — it can be a <strong className="text-slate-400">split dataset</strong> (with{' '}
          <span className="font-mono text-slate-400">train/</span>,{' '}
          <span className="font-mono text-slate-400">val/</span>,{' '}
          <span className="font-mono text-slate-400">test/</span> subfolders) or a{' '}
          <strong className="text-slate-400">flat dataset</strong> (just an{' '}
          <span className="font-mono text-slate-400">images/</span> folder).
          Each split is enriched independently — no re-splitting. Augmented files are written alongside
          the originals and are safe to run multiple times.
        </p>
      </div>

      {/* ── Folder ── */}
      <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4">
        <SectionHeader label="Dataset Folder" />
        <PathInput
          label=""
          value={folder}
          onChange={setFolder}
          filter="dir"
          dirOnly={true}
          placeholder="/villapro-data/exports/my_dataset/"
          pickerTitle="Select dataset folder"
        />
      </div>

      {/* ── Settings ── */}
      <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4">
        <SectionHeader label="Augmentation Settings" />
        <AugmentSettings
          value={config}
          onChange={patch => setConfig(prev => ({ ...prev, ...patch }))}
        />
      </div>

      {/* ── Status ── */}
      {(mut.isPending || jobId) && (() => {
        const total = job?.total ?? 0
        const progress = job?.progress ?? 0
        const pct = total > 0 ? Math.round((progress / total) * 100) : 0
        const showBar = isRunning && total > 0

        if (isDone) return (
          <div className="flex flex-col gap-2 px-4 py-4 rounded-xl border bg-green-950 border-green-500">
            <div className="flex items-center gap-2">
              <span className="text-green-400 text-lg font-bold">✓</span>
              <span className="text-green-300 font-semibold text-sm">Augmentation complete</span>
            </div>
            <div className="flex gap-4 text-xs text-green-400/80 pl-6">
              <span>{result?.augmented ?? 0} images added</span>
              <span>{result?.skipped ?? 0} skipped</span>
            </div>
          </div>
        )

        return (
          <div className={`flex flex-col gap-2 px-4 py-3 rounded-xl text-sm border
            ${isFailed ? 'bg-red-900/20 border-red-700 text-red-300'
            : 'bg-slate-800 border-slate-700 text-slate-300'}`}>
            <div className="flex items-center gap-3">
              {isRunning && <Spinner size={16} />}
              {isFailed && <span className="text-red-400">✗</span>}
              <span>
                {mut.isPending && !jobId ? 'Starting…' :
                 showBar ? `Augmenting… ${progress} / ${total} images (${pct}%)` :
                 job?.status === 'running' ? 'Augmenting…' :
                 isCancelled ? 'Cancelled' :
                 isFailed ? `Failed: ${job?.error}` : ''}
              </span>
            </div>
            {showBar && (
              <div className="w-full bg-slate-700 rounded-full h-1.5 overflow-hidden">
                <div
                  className="bg-violet-500 h-1.5 rounded-full transition-all duration-300"
                  style={{ width: `${pct}%` }}
                />
              </div>
            )}
          </div>
        )
      })()}

      {/* ── Actions ── */}
      <div className="flex gap-2 justify-end">
        {(isDone || isFailed) && <Button variant="ghost" onClick={reset}>Run Again</Button>}
        {isRunning && (
          <Button variant="ghost" disabled={cancelling} onClick={handleCancel}>
            {cancelling ? <><Spinner size={12} /> Cancelling…</> : 'Cancel'}
          </Button>
        )}
        <Button variant="primary" disabled={!canRun} onClick={() => mut.mutate()}>
          {isRunning ? <><Spinner size={12} /> Augmenting…</> : 'Run Augmentation'}
        </Button>
      </div>
    </div>
  )
}
