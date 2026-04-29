import { useState, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { exportBatch, cancelJob, getActiveMergeJob } from '../../lib/api'
import { Button } from '../ui/Button'
import { PathInput } from '../ui/PathInput'
import { FilePicker } from '../ui/FilePicker'
import { Spinner } from '../ui/Spinner'
import { useJobPoller } from '../../lib/useJobPoller'
import { AugmentSettings, augmentConfigToPayload, DEFAULT_AUGMENT } from '../augment/AugmentSettings'
import type { AugmentConfig } from '../augment/AugmentSettings'

type SourceType = 'project' | 'dataset'

interface SourceEntry {
  path: string
  name: string
  type: SourceType
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer text-sm text-slate-300 select-none">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} className="accent-violet-500" />
      {label}
    </label>
  )
}

function SectionHeader({ label }: { label: string }) {
  return (
    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">{label}</p>
  )
}

function TypeBadge({ type }: { type: SourceType }) {
  return (
    <span className={`shrink-0 text-[9px] font-bold uppercase px-1.5 py-0.5 rounded
      ${type === 'project'
        ? 'bg-violet-900/50 text-violet-300 border border-violet-700/50'
        : 'bg-teal-900/50 text-teal-300 border border-teal-700/50'}`}>
      {type === 'project' ? 'project' : 'dataset'}
    </span>
  )
}

export function MergeDatasets() {
  const [sources, setSources] = useState<SourceEntry[]>([])
  const [projectPickerOpen, setProjectPickerOpen] = useState(false)
  const [datasetPickerOpen, setDatasetPickerOpen] = useState(false)
  const [outputDir, setOutputDir] = useState('')

  // Split
  const [doSplit, setDoSplit] = useState(true)
  const [trainPct, setTrainPct] = useState(80)
  const [valPct, setValPct] = useState(10)
  const testPct = Math.max(0, 100 - trainPct - valPct)
  const [generateYaml, setGenerateYaml] = useState(true)

  // Augmentation
  const [doAug, setDoAug] = useState(false)
  const [augConfig, setAugConfig] = useState<AugmentConfig>(DEFAULT_AUGMENT)

  // Job
  const [jobId, setJobId] = useState<string | null>(null)
  const job = useJobPoller(jobId)

  // Restore any in-progress job when navigating back to this tab
  useEffect(() => {
    getActiveMergeJob().then(data => {
      if (data.active && data.job_id) {
        setJobId(data.job_id)
      }
    }).catch(() => {})
  }, [])

  const addSource = (path: string, type: SourceType) => {
    if (sources.find(s => s.path === path)) return
    const raw = path.split('/').pop() ?? path
    const name = type === 'project' ? raw.replace('.annotatex', '') : raw
    setSources(prev => [...prev, { path, name, type }])
  }

  const removeSource = (path: string) => setSources(prev => prev.filter(s => s.path !== path))

  const split = doSplit ? { train: trainPct / 100, val: valPct / 100, test: testPct / 100 } : undefined
  const augmentation = doAug ? augmentConfigToPayload(augConfig) : null

  const mergeMut = useMutation({
    mutationFn: () => exportBatch({
      sources: sources.map(s => s.path),
      output_dir: outputDir,
      split,
      generate_yaml: generateYaml,
      augmentation,
    }),
    onSuccess: (data: { job_id: string }) => setJobId(data.job_id),
  })

  const canRun = sources.length >= 1 && outputDir && !mergeMut.isPending && job?.status !== 'running'
  const isDone = job?.status === 'done'
  const isFailed = job?.status === 'failed'
  const isCancelled = isFailed && job?.error === 'Cancelled'
  const isRunning = mergeMut.isPending || job?.status === 'running'
  const result = job?.result as { images?: number; augmented?: number; annotations?: number; classes?: number; projects?: number } | null

  const [cancelling, setCancelling] = useState(false)
  const handleCancel = () => {
    if (!jobId) return
    setCancelling(true)
    cancelJob(jobId).finally(() => setCancelling(false))
  }

  const reset = () => { setJobId(null); mergeMut.reset(); setCancelling(false) }

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      {/* Project file picker */}
      <FilePicker
        open={projectPickerOpen}
        onClose={() => setProjectPickerOpen(false)}
        onSelect={path => addSource(path, 'project')}
        filter="project"
        title="Select Project File (.annotatex)"
      />

      {/* Dataset folder picker */}
      <FilePicker
        open={datasetPickerOpen}
        onClose={() => setDatasetPickerOpen(false)}
        onSelect={path => addSource(path, 'dataset')}
        filter="dir"
        dirOnly={true}
        title="Select YOLO Dataset Folder"
      />

      <div>
        <h2 className="text-base font-semibold text-slate-100 mb-1">Merge Datasets</h2>
        <p className="text-sm text-slate-500">
          Add .annotatex project files and/or exported YOLO dataset folders (with <code className="text-slate-400">train/</code>, <code className="text-slate-400">val/</code>, <code className="text-slate-400">test/</code> or flat <code className="text-slate-400">images/</code>).
          All images are pooled, class IDs unified by name, then re-split to your specification.
        </p>
      </div>

      {/* ── Sources ── */}
      <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-3">
        <SectionHeader label="Sources" />

        {sources.length === 0 ? (
          <div className="flex items-center justify-center border border-dashed border-slate-700 rounded-lg py-6 text-sm text-slate-600">
            No sources added — add a project or dataset folder below
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            {sources.map(s => (
              <div key={s.path} className="flex items-center gap-2 px-3 py-2 bg-[#0f172a] rounded-lg group">
                <TypeBadge type={s.type} />
                <span className="text-sm text-slate-200 truncate flex-1">{s.name}</span>
                <span className="text-xs text-slate-600 font-mono truncate max-w-[220px] hidden sm:block">{s.path}</span>
                <button
                  onClick={() => removeSource(s.path)}
                  className="text-slate-600 hover:text-red-400 cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                >×</button>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-600">{sources.length} source{sources.length !== 1 ? 's' : ''}</span>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={() => setDatasetPickerOpen(true)}>+ Dataset Folder…</Button>
            <Button variant="secondary" size="sm" onClick={() => setProjectPickerOpen(true)}>+ Project File…</Button>
          </div>
        </div>
      </div>

      {/* ── Split ── */}
      <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-3">
        <SectionHeader label="Train / Val / Test Split" />
        <Toggle label="Re-split all images" checked={doSplit} onChange={setDoSplit} />

        {doSplit && (
          <>
            <div className="flex rounded overflow-hidden h-4 text-[10px] font-bold">
              <div className="flex items-center justify-center bg-violet-700 text-white" style={{ width: `${trainPct}%` }}>
                {trainPct > 10 ? `Train ${trainPct}%` : ''}
              </div>
              <div className="flex items-center justify-center bg-teal-700 text-white" style={{ width: `${valPct}%` }}>
                {valPct > 10 ? `Val ${valPct}%` : ''}
              </div>
              <div className="flex items-center justify-center bg-amber-700 text-white" style={{ width: `${testPct}%` }}>
                {testPct > 10 ? `Test ${testPct}%` : ''}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              {[
                { label: 'Train %', value: trainPct, set: (v: number) => { setTrainPct(v); if (v + valPct > 95) setValPct(95 - v) }, min: 10, max: 90 },
                { label: 'Val %', value: valPct, set: setValPct, min: 5, max: Math.max(5, 90 - trainPct) },
                { label: 'Test %', value: testPct, set: () => {}, min: 0, max: 0, readonly: true },
              ].map(({ label, value, set, min, max, readonly }) => (
                <div key={label} className="flex flex-col gap-1">
                  <label className="text-xs text-slate-400">{label}</label>
                  {readonly ? (
                    <p className="text-sm text-slate-300 text-center">{value}% (remainder)</p>
                  ) : (
                    <>
                      <input type="range" min={min} max={max} value={value} onChange={e => set(+e.target.value)} className="accent-violet-500" />
                      <span className="text-xs text-slate-300 text-center">{value}%</span>
                    </>
                  )}
                </div>
              ))}
            </div>

            <Toggle label="Generate data.yaml (YOLOv8)" checked={generateYaml} onChange={setGenerateYaml} />
          </>
        )}
      </div>

      {/* ── Augmentation ── */}
      <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-3">
        <SectionHeader label="Augmentation (optional)" />
        <Toggle label="Enable augmentation" checked={doAug} onChange={setDoAug} />
        {doAug && (
          <div className="mt-2">
            <AugmentSettings
              value={augConfig}
              onChange={patch => setAugConfig(prev => ({ ...prev, ...patch }))}
            />
          </div>
        )}
      </div>

      {/* ── Output ── */}
      <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4">
        <SectionHeader label="Output Directory" />
        <PathInput
          label=""
          value={outputDir}
          onChange={setOutputDir}
          filter="dir"
          dirOnly={true}
          placeholder="/villapro-data/merged_dataset/"
          pickerTitle="Select output folder"
        />
      </div>

      {/* ── Result / Progress ── */}
      {(mergeMut.isPending || jobId) && (() => {
        const total = job?.total ?? 0
        const progress = job?.progress ?? 0
        const pct = total > 0 ? Math.round((progress / total) * 100) : 0
        const showBar = isRunning && total > 0

        if (isDone) return (
          <div className="flex flex-col gap-2 px-4 py-4 rounded-xl border bg-green-950 border-green-500">
            <div className="flex items-center gap-2">
              <span className="text-green-400 text-lg font-bold">✓</span>
              <span className="text-green-300 font-semibold text-sm">Merge complete</span>
            </div>
            <div className="flex flex-wrap gap-4 text-xs text-green-400/80 pl-6">
              <span>{result?.projects ?? 0} sources</span>
              <span>{result?.images ?? 0} images</span>
              {(result?.augmented ?? 0) > 0 && <span>{result!.augmented} augmented</span>}
              <span>{result?.annotations ?? 0} annotations</span>
              <span>{result?.classes ?? 0} classes</span>
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
                {mergeMut.isPending && !jobId ? 'Starting…' :
                 showBar ? `Merging… ${progress} / ${total} images (${pct}%)` :
                 job?.status === 'running' ? 'Merging datasets…' :
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

      {/* ── Run button ── */}
      <div className="flex gap-2 justify-end">
        {(isDone || isFailed) && <Button variant="ghost" onClick={reset}>Reset</Button>}
        {isRunning && (
          <Button variant="ghost" disabled={cancelling} onClick={handleCancel}>
            {cancelling ? <><Spinner size={12} /> Cancelling…</> : 'Cancel'}
          </Button>
        )}
        <Button
          variant="primary"
          disabled={!canRun}
          onClick={() => mergeMut.mutate()}
        >
          {isRunning ? <><Spinner size={12} /> Merging…</> : 'Merge & Export'}
        </Button>
      </div>
    </div>
  )
}
