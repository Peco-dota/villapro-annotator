import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { exportYolo, exportCoco, saveProject } from '../../lib/api'
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

type Step = 'format' | 'augment' | 'split' | 'running'

const STEPS: Step[] = ['format', 'augment', 'split', 'running']

function StepIndicator({ current }: { current: Step }) {
  const labels = ['Export', 'Augment', 'Split', 'Done']
  const idx = STEPS.indexOf(current)
  return (
    <div className="flex items-center gap-0 mb-2">
      {labels.slice(0, 3).map((label, i) => (
        <div key={i} className="flex items-center">
          <div className={`flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded
            ${i === idx ? 'text-violet-300' : i < idx ? 'text-slate-500' : 'text-slate-700'}`}>
            <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold
              ${i === idx ? 'bg-violet-600 text-white' : i < idx ? 'bg-slate-600 text-slate-400' : 'bg-slate-800 text-slate-600'}`}>
              {i < idx ? '✓' : i + 1}
            </span>
            {label}
          </div>
          {i < 2 && <div className={`w-6 h-px ${i < idx ? 'bg-slate-600' : 'bg-slate-800'}`} />}
        </div>
      ))}
    </div>
  )
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer text-sm text-slate-300 select-none">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} className="accent-violet-500" />
      {label}
    </label>
  )
}

function AugSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">{label}</p>
      <div className="flex flex-col gap-2 pl-2 border-l-2 border-slate-700">
        {children}
      </div>
    </div>
  )
}

function RangeRow({ label, enabled, onToggle, min, onMin, minBounds, max, onMax, maxBounds, step }: {
  label: string
  enabled: boolean
  onToggle: (v: boolean) => void
  min: number; onMin: (v: number) => void; minBounds: [number, number]
  max: number; onMax: (v: number) => void; maxBounds: [number, number]
  step: number
}) {
  return (
    <div className="flex items-center gap-3">
      <label className="flex items-center gap-2 cursor-pointer select-none w-28 shrink-0">
        <input type="checkbox" checked={enabled} onChange={e => onToggle(e.target.checked)} className="accent-violet-500" />
        <span className={`text-sm ${enabled ? 'text-slate-200' : 'text-slate-500'}`}>{label}</span>
      </label>
      <div className={`flex items-center gap-1.5 transition-opacity ${enabled ? 'opacity-100' : 'opacity-30 pointer-events-none'}`}>
        <span className="text-xs text-slate-500">min</span>
        <input
          type="number" value={min} step={step}
          min={minBounds[0]} max={Math.min(minBounds[1], max - step)}
          onChange={e => onMin(+e.target.value)}
          className="w-16 bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-xs text-slate-100 focus:outline-none focus:border-violet-500"
        />
        <span className="text-xs text-slate-500">max</span>
        <input
          type="number" value={max} step={step}
          min={Math.max(maxBounds[0], min + step)} max={maxBounds[1]}
          onChange={e => onMax(+e.target.value)}
          className="w-16 bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-xs text-slate-100 focus:outline-none focus:border-violet-500"
        />
      </div>
    </div>
  )
}

function SingleRow({ label, enabled, onToggle, value, onChange, min, max, step, unit }: {
  label: string
  enabled: boolean
  onToggle: (v: boolean) => void
  value: number; onChange: (v: number) => void
  min: number; max: number; step: number
  unit: string
}) {
  return (
    <div className="flex items-center gap-3">
      <label className="flex items-center gap-2 cursor-pointer select-none w-36 shrink-0">
        <input type="checkbox" checked={enabled} onChange={e => onToggle(e.target.checked)} className="accent-violet-500" />
        <span className={`text-sm ${enabled ? 'text-slate-200' : 'text-slate-500'}`}>{label}</span>
      </label>
      <div className={`flex items-center gap-1.5 transition-opacity ${enabled ? 'opacity-100' : 'opacity-30 pointer-events-none'}`}>
        <input
          type="number" value={value} step={step} min={min} max={max}
          onChange={e => onChange(+e.target.value)}
          className="w-16 bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-xs text-slate-100 focus:outline-none focus:border-violet-500"
        />
        <span className="text-xs text-slate-500">{unit}</span>
      </div>
    </div>
  )
}

export function ExportDialog({ open, onClose, projectPath }: Props) {
  const [step, setStep] = useState<Step>('format')

  // Step 1: format + output
  const [format, setFormat] = useState<'yolo' | 'coco'>('yolo')
  const [outputDir, setOutputDir] = useState('')
  const [datasetName, setDatasetName] = useState('')

  const projectName = projectPath.split('/').pop()?.replace(/\.[^.]+$/, '') ?? 'dataset'
  const effectiveName = datasetName.trim() || projectName
  const effectiveOutputDir = outputDir ? `${outputDir.replace(/\/+$/, '')}/${effectiveName}` : ''

  // Step 2: augmentation
  const [doAugment, setDoAugment] = useState(false)
  const [copies, setCopies] = useState(2)
  const [augOpts, setAugOpts] = useState({
    flip_horizontal: true,
    flip_vertical: false,
    brightness: true,
    brightness_min: 0.6,
    brightness_max: 1.4,
    contrast: true,
    contrast_min: 0.6,
    contrast_max: 1.4,
    saturation: true,
    saturation_min: 0.5,
    saturation_max: 1.5,
    blur: false,
    blur_radius: 1.5,
    noise: false,
    noise_std: 15,
    rotation: false,
    rotation_degrees: 15,
    only_annotated: true,
    output_original: true,
  })
  const setAugBool = (k: keyof typeof augOpts) => (v: boolean) => setAugOpts(o => ({ ...o, [k]: v }))
  const setAugNum = (k: keyof typeof augOpts) => (v: number) => setAugOpts(o => ({ ...o, [k]: v }))

  // Step 3: split
  const [doSplit, setDoSplit] = useState(true)
  const [trainPct, setTrainPct] = useState(80)
  const [valPct, setValPct] = useState(10)
  const testPct = Math.max(0, 100 - trainPct - valPct)

  // Job tracking
  const [jobId, setJobId] = useState<string | null>(null)
  const job = useJobPoller(jobId)

  const reset = () => {
    setStep('format')
    setJobId(null)
    setDatasetName('')
    exportMut.reset()
  }

  const split = doSplit ? {
    train: trainPct / 100,
    val: valPct / 100,
    test: testPct / 100,
  } : undefined

  const augmentation = doAugment ? {
    copies_per_image: copies,
    flip_horizontal: augOpts.flip_horizontal,
    flip_vertical: augOpts.flip_vertical,
    brightness: augOpts.brightness,
    brightness_range: [augOpts.brightness_min, augOpts.brightness_max],
    contrast: augOpts.contrast,
    contrast_range: [augOpts.contrast_min, augOpts.contrast_max],
    saturation: augOpts.saturation,
    saturation_range: [augOpts.saturation_min, augOpts.saturation_max],
    blur: augOpts.blur,
    blur_radius: augOpts.blur_radius,
    noise: augOpts.noise,
    noise_std: augOpts.noise_std,
    rotation: augOpts.rotation,
    rotation_degrees: augOpts.rotation_degrees,
    only_annotated: augOpts.only_annotated,
    output_original: augOpts.output_original,
  } : undefined

  const exportMut = useMutation({
    mutationFn: async () => {
      await saveProject(projectPath)
      return format === 'yolo'
        ? exportYolo({ project_path: projectPath, output_dir: effectiveOutputDir, split, generate_yaml: !!doSplit, augmentation })
        : exportCoco({ project_path: projectPath, output_dir: effectiveOutputDir })
    },
    onSuccess: (data) => {
      setJobId((data as { job_id: string }).job_id)
      setStep('running')
    },
  })

  const allDone = job?.status === 'done'

  return (
    <Modal open={open} onClose={() => { reset(); onClose() }} title="Export Dataset" width="max-w-lg">
      <div className="flex flex-col gap-4">

        {step !== 'running' && <StepIndicator current={step} />}

        {/* ── Step 1: Format + Output ── */}
        {step === 'format' && (
          <>
            <div className="flex gap-2">
              {(['yolo', 'coco'] as const).map(f => (
                <button
                  key={f}
                  onClick={() => setFormat(f)}
                  className={`flex-1 py-2 text-xs rounded border transition-colors cursor-pointer font-bold uppercase tracking-wider
                    ${format === f ? 'bg-violet-700 border-violet-500 text-white' : 'bg-slate-800 border-slate-600 text-slate-400 hover:border-violet-500'}`}
                >{f}</button>
              ))}
            </div>

            <PathInput
              label="Parent folder"
              value={outputDir}
              onChange={setOutputDir}
              filter="dir"
              dirOnly={true}
              placeholder="/data/exports/"
              pickerTitle="Select export parent folder"
            />

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-slate-400">Dataset name</label>
              <input
                value={datasetName}
                onChange={e => setDatasetName(e.target.value)}
                placeholder={projectName}
                className="bg-[#0f172a] border border-[#334155] rounded px-3 py-1.5 text-sm text-slate-100
                  placeholder:text-slate-600 focus:outline-none focus:border-violet-500 font-mono"
              />
              {outputDir && (
                <p className="text-[11px] text-slate-500 font-mono">
                  → <span className="text-slate-400">{effectiveOutputDir}</span>
                </p>
              )}
            </div>

            <div className="flex gap-2 justify-end pt-1">
              <Button variant="ghost" onClick={() => { reset(); onClose() }}>Cancel</Button>
              <Button variant="primary" disabled={!outputDir} onClick={() => setStep('augment')}>
                Next →
              </Button>
            </div>
          </>
        )}

        {/* ── Step 2: Augmentation ── */}
        {step === 'augment' && (
          <>
            <div className="flex flex-col gap-4 max-h-[52vh] overflow-y-auto pr-1">

                {/* Copies */}
                <div className="flex items-center gap-3">
                  <label className="text-sm text-slate-300 shrink-0">Copies per image</label>
                  <input
                    type="number" min={1} max={10} value={copies}
                    onChange={e => setCopies(Math.max(1, Math.min(10, +e.target.value)))}
                    className="w-20 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-sm text-slate-100 focus:outline-none focus:border-violet-500"
                  />
                  <span className="text-xs text-slate-500">(1–10)</span>
                </div>

                {/* Flips */}
                <AugSection label="Flips">
                  <div className="flex gap-6">
                    <Toggle label="Flip horizontal" checked={augOpts.flip_horizontal} onChange={setAugBool('flip_horizontal')} />
                    <Toggle label="Flip vertical" checked={augOpts.flip_vertical} onChange={setAugBool('flip_vertical')} />
                  </div>
                </AugSection>

                {/* Color */}
                <AugSection label="Color adjustments">
                  <RangeRow
                    label="Brightness"
                    enabled={augOpts.brightness}
                    onToggle={setAugBool('brightness')}
                    min={augOpts.brightness_min} onMin={setAugNum('brightness_min')}
                    minBounds={[0.1, 1.0]}
                    max={augOpts.brightness_max} onMax={setAugNum('brightness_max')}
                    maxBounds={[1.0, 2.0]}
                    step={0.05}
                  />
                  <RangeRow
                    label="Contrast"
                    enabled={augOpts.contrast}
                    onToggle={setAugBool('contrast')}
                    min={augOpts.contrast_min} onMin={setAugNum('contrast_min')}
                    minBounds={[0.1, 1.0]}
                    max={augOpts.contrast_max} onMax={setAugNum('contrast_max')}
                    maxBounds={[1.0, 2.0]}
                    step={0.05}
                  />
                  <RangeRow
                    label="Saturation"
                    enabled={augOpts.saturation}
                    onToggle={setAugBool('saturation')}
                    min={augOpts.saturation_min} onMin={setAugNum('saturation_min')}
                    minBounds={[0.0, 1.0]}
                    max={augOpts.saturation_max} onMax={setAugNum('saturation_max')}
                    maxBounds={[1.0, 3.0]}
                    step={0.05}
                  />
                </AugSection>

                {/* Blur */}
                <AugSection label="Blur & Noise">
                  <SingleRow
                    label="Gaussian blur"
                    enabled={augOpts.blur}
                    onToggle={setAugBool('blur')}
                    value={augOpts.blur_radius}
                    onChange={setAugNum('blur_radius')}
                    min={0.5} max={5.0} step={0.5}
                    unit="radius"
                  />
                  <SingleRow
                    label="Gaussian noise"
                    enabled={augOpts.noise}
                    onToggle={setAugBool('noise')}
                    value={augOpts.noise_std}
                    onChange={setAugNum('noise_std')}
                    min={1} max={60} step={1}
                    unit="std"
                  />
                </AugSection>

                {/* Rotation */}
                <AugSection label="Rotation">
                  <SingleRow
                    label="Random rotation"
                    enabled={augOpts.rotation}
                    onToggle={setAugBool('rotation')}
                    value={augOpts.rotation_degrees}
                    onChange={setAugNum('rotation_degrees')}
                    min={1} max={45} step={1}
                    unit="± °"
                  />
                </AugSection>

                {/* Output options */}
                <AugSection label="Output options">
                  <Toggle label="Only augment annotated images" checked={augOpts.only_annotated} onChange={setAugBool('only_annotated')} />
                  <Toggle label="Include originals in output" checked={augOpts.output_original} onChange={setAugBool('output_original')} />
                </AugSection>

            </div>

            <div className="flex gap-2 justify-end pt-1">
              <Button variant="ghost" onClick={() => setStep('format')}>← Back</Button>
              <Button variant="ghost" onClick={() => { setDoAugment(false); setStep('split') }}>Skip</Button>
              <Button variant="primary" onClick={() => { setDoAugment(true); setStep('split') }}>Apply & Next →</Button>
            </div>
          </>
        )}

        {/* ── Step 3: Train/Val/Test split ── */}
        {step === 'split' && (
          <>
            <Toggle label="Split into train / val / test sets" checked={doSplit} onChange={setDoSplit} />

            {doSplit && (
              <div className="flex flex-col gap-3 pl-2 border-l-2 border-violet-800">
                {/* Visual split bar */}
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

                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-slate-400">Train %</label>
                    <input
                      type="range" min={10} max={90} value={trainPct}
                      onChange={e => { const v = +e.target.value; setTrainPct(v); if (v + valPct > 95) setValPct(95 - v) }}
                      className="accent-violet-500"
                    />
                    <span className="text-xs text-slate-300 text-center">{trainPct}%</span>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-slate-400">Val %</label>
                    <input
                      type="range" min={5} max={Math.max(5, 90 - trainPct)} value={valPct}
                      onChange={e => setValPct(+e.target.value)}
                      className="accent-violet-500"
                    />
                    <span className="text-xs text-slate-300 text-center">{valPct}%</span>
                  </div>
                </div>
                <p className="text-xs text-slate-500">Test: {testPct}% (remainder)</p>
              </div>
            )}

            {!doSplit && (
              <p className="text-xs text-slate-600 pl-1">All images will be exported flat (no train/val/test folders). You can split later.</p>
            )}

            <div className="flex gap-2 justify-end pt-1">
              <Button variant="ghost" onClick={() => setStep('augment')}>← Back</Button>
              <Button
                variant="primary"
                disabled={exportMut.isPending}
                onClick={() => exportMut.mutate()}
              >
                {exportMut.isPending ? <Spinner size={12} /> : null}
                Export
              </Button>
            </div>
          </>
        )}

        {/* ── Running / Done ── */}
        {step === 'running' && (
          <div className="flex flex-col gap-3">
            <div className={`flex items-center gap-3 text-sm px-3 py-2.5 rounded
              ${job?.status === 'done' ? 'bg-green-900/20 text-green-300' : job?.status === 'failed' ? 'bg-red-900/20 text-red-300' : 'bg-slate-800 text-slate-300'}`}>
              {job?.status === 'running' || !job ? <Spinner size={14} /> : job.status === 'done' ? '✓' : '✗'}
              <span>
                {!job ? 'Starting…' :
                 job.status === 'running' ? (doAugment ? 'Exporting and augmenting…' : 'Exporting…') :
                 job.status === 'done' ? (() => {
                   const r = job.result as { images?: number; augmented?: number; annotations?: number }
                   const parts = [`${r?.images ?? 0} images`]
                   if (doAugment) parts.push(`${r?.augmented ?? 0} augmented`)
                   parts.push(`${r?.annotations ?? 0} annotations`)
                   return `Done — ${parts.join(', ')}`
                 })() :
                 `Failed: ${job.error}`}
              </span>
            </div>

            {allDone && (
              <p className="text-xs text-slate-400 text-center">
                Dataset saved to <span className="font-mono text-slate-300">{effectiveOutputDir}</span>
              </p>
            )}

            <div className="flex gap-2 justify-end pt-1">
              {allDone ? (
                <Button variant="primary" onClick={() => { reset(); onClose() }}>Done</Button>
              ) : (
                <Button variant="ghost" disabled>Please wait…</Button>
              )}
            </div>
          </div>
        )}

      </div>
    </Modal>
  )
}
