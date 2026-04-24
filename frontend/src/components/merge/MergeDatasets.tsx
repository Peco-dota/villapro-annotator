import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { exportBatch } from '../../lib/api'
import { Button } from '../ui/Button'
import { PathInput } from '../ui/PathInput'
import { FilePicker } from '../ui/FilePicker'
import { Spinner } from '../ui/Spinner'
import { useJobPoller } from '../../lib/useJobPoller'
import { AugmentSettings, augmentConfigToPayload, DEFAULT_AUGMENT } from '../augment/AugmentSettings'
import type { AugmentConfig } from '../augment/AugmentSettings'

interface ProjectEntry {
  path: string
  name: string
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

export function MergeDatasets() {
  const [projects, setProjects] = useState<ProjectEntry[]>([])
  const [pickerOpen, setPickerOpen] = useState(false)
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

  const addProjects = (path: string) => {
    if (!projects.find(p => p.path === path)) {
      const name = path.split('/').pop()?.replace('.annotatex', '') ?? path
      setProjects(prev => [...prev, { path, name }])
    }
  }

  const removeProject = (path: string) => setProjects(prev => prev.filter(p => p.path !== path))

  const split = doSplit ? {
    train: trainPct / 100,
    val: valPct / 100,
    test: testPct / 100,
  } : undefined

  const augmentation = doAug ? augmentConfigToPayload(augConfig) : null

  const mergeMut = useMutation({
    mutationFn: () => exportBatch({
      project_paths: projects.map(p => p.path),
      output_dir: outputDir,
      split,
      generate_yaml: generateYaml,
      augmentation,
    }),
    onSuccess: (data: { job_id: string }) => setJobId(data.job_id),
  })

  const canRun = projects.length >= 2 && outputDir && !mergeMut.isPending && job?.status !== 'running'
  const isDone = job?.status === 'done'
  const isFailed = job?.status === 'failed'
  const result = job?.result as { images?: number; augmented?: number; annotations?: number; classes?: number; projects?: number } | null

  const reset = () => {
    setJobId(null)
    mergeMut.reset()
  }

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <FilePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onSelect={addProjects}
        filter="project"
        title="Select Project File"
      />

      <div>
        <h2 className="text-base font-semibold text-slate-100 mb-1">Merge Datasets</h2>
        <p className="text-sm text-slate-500">
          Add two or more .annotatex project files. All images and annotations will be merged
          into one dataset with unified class IDs (matched by name).
        </p>
      </div>

      {/* ── Projects ── */}
      <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-3">
        <SectionHeader label="Projects" />

        {projects.length === 0 ? (
          <div className="flex items-center justify-center border border-dashed border-slate-700 rounded-lg py-6 text-sm text-slate-600">
            No projects added — click "Add Project" to begin
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            {projects.map(p => (
              <div key={p.path} className="flex items-center gap-3 px-3 py-2 bg-[#0f172a] rounded-lg group">
                <span className="text-sm text-slate-200 truncate flex-1">{p.name}</span>
                <span className="text-xs text-slate-600 font-mono truncate max-w-[260px] hidden sm:block">{p.path}</span>
                <button
                  onClick={() => removeProject(p.path)}
                  className="text-slate-600 hover:text-red-400 cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                >×</button>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-600">{projects.length} project{projects.length !== 1 ? 's' : ''}{projects.length < 2 ? ' — need at least 2' : ''}</span>
          <Button variant="secondary" size="sm" onClick={() => setPickerOpen(true)}>+ Add Project…</Button>
        </div>
      </div>

      {/* ── Split ── */}
      <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-3">
        <SectionHeader label="Train / Val / Test Split" />
        <Toggle label="Enable split" checked={doSplit} onChange={setDoSplit} />

        {doSplit && (
          <>
            {/* Visual bar */}
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
          placeholder="/data/merged_dataset/"
          pickerTitle="Select output folder"
        />
      </div>

      {/* ── Result / Progress ── */}
      {(mergeMut.isPending || jobId) && (
        <div className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm border
          ${isDone ? 'bg-green-900/20 border-green-700 text-green-300'
          : isFailed ? 'bg-red-900/20 border-red-700 text-red-300'
          : 'bg-slate-800 border-slate-700 text-slate-300'}`}>
          {!isDone && !isFailed && <Spinner size={16} />}
          {isDone && <span className="text-green-400">✓</span>}
          {isFailed && <span className="text-red-400">✗</span>}
          <span>
            {mergeMut.isPending && !jobId ? 'Starting…' :
             job?.status === 'running' ? 'Merging datasets…' :
             isDone ? `Done — ${result?.projects ?? 0} projects, ${result?.images ?? 0} images, ${result?.augmented ?? 0} augmented, ${result?.annotations ?? 0} annotations, ${result?.classes ?? 0} classes` :
             isFailed ? `Failed: ${job?.error}` : ''}
          </span>
        </div>
      )}

      {/* ── Run button ── */}
      <div className="flex gap-2 justify-end">
        {isDone && (
          <Button variant="ghost" onClick={reset}>Reset</Button>
        )}
        <Button
          variant="primary"
          disabled={!canRun}
          onClick={() => mergeMut.mutate()}
        >
          {mergeMut.isPending || job?.status === 'running' ? <><Spinner size={12} /> Merging…</> : 'Merge & Export'}
        </Button>
      </div>
    </div>
  )
}
