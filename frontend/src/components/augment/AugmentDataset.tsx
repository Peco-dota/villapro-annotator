import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../../lib/api'
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

  const mut = useMutation({
    mutationFn: () => augmentFolder({ folder, ...augmentConfigToPayload(config) }),
    onSuccess: (data: { job_id: string }) => setJobId(data.job_id),
  })

  const isDone = job?.status === 'done'
  const isFailed = job?.status === 'failed'
  const isRunning = mut.isPending || job?.status === 'running'
  const result = job?.result as { augmented?: number; skipped?: number } | null

  const reset = () => { setJobId(null); mut.reset() }

  const canRun = !!folder && !isRunning && !isDone

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <div>
        <h2 className="text-base font-semibold text-slate-100 mb-1">Augment Dataset</h2>
        <p className="text-sm text-slate-500">
          Enrich an already-exported dataset by generating augmented copies of existing images.
          Point to the export folder (must contain an <span className="font-mono text-slate-400">images/</span> subfolder).
          Augmented files are written alongside the originals — safe to run multiple times.
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
          placeholder="/data/my_export/"
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
      {(mut.isPending || jobId) && (
        <div className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm border
          ${isDone ? 'bg-green-900/20 border-green-700 text-green-300'
          : isFailed ? 'bg-red-900/20 border-red-700 text-red-300'
          : 'bg-slate-800 border-slate-700 text-slate-300'}`}>
          {isRunning && <Spinner size={16} />}
          {isDone && <span className="text-green-400">✓</span>}
          {isFailed && <span className="text-red-400">✗</span>}
          <span>
            {mut.isPending && !jobId ? 'Starting…' :
             job?.status === 'running' ? 'Augmenting…' :
             isDone ? `Done — ${result?.augmented ?? 0} augmented images added (${result?.skipped ?? 0} skipped)` :
             isFailed ? `Failed: ${job?.error}` : ''}
          </span>
        </div>
      )}

      {/* ── Actions ── */}
      <div className="flex gap-2 justify-end">
        {isDone && <Button variant="ghost" onClick={reset}>Augment Again</Button>}
        <Button variant="primary" disabled={!canRun} onClick={() => mut.mutate()}>
          {isRunning ? <><Spinner size={12} /> Augmenting…</> : 'Run Augmentation'}
        </Button>
      </div>
    </div>
  )
}
