import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { Button } from '../ui/Button'
import { PathInput } from '../ui/PathInput'
import { Spinner } from '../ui/Spinner'
import { useJobPoller } from '../../lib/useJobPoller'

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer text-sm text-slate-300 select-none">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} className="accent-violet-500" />
      {label}
    </label>
  )
}

function SectionHeader({ label }: { label: string }) {
  return <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">{label}</p>
}

const augmentFolder = (data: object) =>
  api.post('/api/datasets/augment/folder', data).then(r => r.data)

export function AugmentDataset() {
  const [folder, setFolder] = useState('')

  const [copies, setCopies] = useState(2)
  const [flipH, setFlipH] = useState(true)
  const [flipV, setFlipV] = useState(false)
  const [brightness, setBrightness] = useState(true)
  const [brightnessMin, setBrightnessMin] = useState(0.6)
  const [brightnessMax, setBrightnessMax] = useState(1.4)
  const [contrast, setContrast] = useState(true)
  const [contrastMin, setContrastMin] = useState(0.6)
  const [contrastMax, setContrastMax] = useState(1.4)
  const [saturation, setSaturation] = useState(true)
  const [saturationMin, setSaturationMin] = useState(0.5)
  const [saturationMax, setSaturationMax] = useState(1.5)
  const [blur, setBlur] = useState(false)
  const [blurRadius, setBlurRadius] = useState(1.5)
  const [noise, setNoise] = useState(false)
  const [noiseStd, setNoiseStd] = useState(15)
  const [rotation, setRotation] = useState(false)
  const [rotDeg, setRotDeg] = useState(15)
  const [onlyAnnotated, setOnlyAnnotated] = useState(true)

  const [jobId, setJobId] = useState<string | null>(null)
  const job = useJobPoller(jobId)

  const mut = useMutation({
    mutationFn: () => augmentFolder({
      folder,
      copies_per_image: copies,
      flip_horizontal: flipH,
      flip_vertical: flipV,
      brightness,
      brightness_range: [brightnessMin, brightnessMax],
      contrast,
      contrast_range: [contrastMin, contrastMax],
      saturation,
      saturation_range: [saturationMin, saturationMax],
      blur,
      blur_radius: blurRadius,
      noise,
      noise_std: noiseStd,
      rotation,
      rotation_degrees: rotDeg,
      only_annotated: onlyAnnotated,
      output_original: true,
    }),
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
      <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-4">
        <SectionHeader label="Augmentation Settings" />

        {/* Copies */}
        <div className="flex items-center gap-3">
          <label className="text-sm text-slate-400 w-36 shrink-0">Copies per image</label>
          <input
            type="number" min={1} max={10} value={copies}
            onChange={e => setCopies(Math.max(1, Math.min(10, +e.target.value)))}
            className="w-20 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-sm text-slate-100 focus:outline-none focus:border-violet-500"
          />
          <span className="text-xs text-slate-500">(1–10)</span>
        </div>

        {/* Flips */}
        <div className="flex flex-col gap-1">
          <p className="text-xs text-slate-500 mb-1">Flips</p>
          <div className="flex gap-6 pl-2">
            <Toggle label="Flip horizontal" checked={flipH} onChange={setFlipH} />
            <Toggle label="Flip vertical" checked={flipV} onChange={setFlipV} />
          </div>
        </div>

        {/* Color */}
        <div className="flex flex-col gap-2">
          <p className="text-xs text-slate-500 mb-1">Color adjustments</p>
          <div className="flex flex-col gap-2 pl-2 border-l-2 border-slate-700">
            {[
              { label: 'Brightness', enabled: brightness, onToggle: setBrightness, min: brightnessMin, setMin: setBrightnessMin, max: brightnessMax, setMax: setBrightnessMax },
              { label: 'Contrast',   enabled: contrast,   onToggle: setContrast,   min: contrastMin,   setMin: setContrastMin,   max: contrastMax,   setMax: setContrastMax   },
              { label: 'Saturation', enabled: saturation, onToggle: setSaturation, min: saturationMin, setMin: setSaturationMin, max: saturationMax, setMax: setSaturationMax },
            ].map(({ label, enabled, onToggle, min, setMin, max, setMax }) => (
              <div key={label} className="flex items-center gap-3">
                <label className="flex items-center gap-2 cursor-pointer select-none w-28 shrink-0">
                  <input type="checkbox" checked={enabled} onChange={e => onToggle(e.target.checked)} className="accent-violet-500" />
                  <span className={`text-sm ${enabled ? 'text-slate-200' : 'text-slate-500'}`}>{label}</span>
                </label>
                <div className={`flex items-center gap-1.5 transition-opacity ${enabled ? 'opacity-100' : 'opacity-30 pointer-events-none'}`}>
                  <span className="text-xs text-slate-500">min</span>
                  <input type="number" value={min} step={0.05} min={0.1} max={max - 0.05}
                    onChange={e => setMin(+e.target.value)}
                    className="w-16 bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-xs text-slate-100 focus:outline-none focus:border-violet-500" />
                  <span className="text-xs text-slate-500">max</span>
                  <input type="number" value={max} step={0.05} min={min + 0.05} max={3.0}
                    onChange={e => setMax(+e.target.value)}
                    className="w-16 bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-xs text-slate-100 focus:outline-none focus:border-violet-500" />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Blur & Noise */}
        <div className="flex flex-col gap-2">
          <p className="text-xs text-slate-500 mb-1">Blur & Noise</p>
          <div className="flex flex-col gap-2 pl-2 border-l-2 border-slate-700">
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 cursor-pointer select-none w-36 shrink-0">
                <input type="checkbox" checked={blur} onChange={e => setBlur(e.target.checked)} className="accent-violet-500" />
                <span className={`text-sm ${blur ? 'text-slate-200' : 'text-slate-500'}`}>Gaussian blur</span>
              </label>
              <div className={`flex items-center gap-1.5 transition-opacity ${blur ? 'opacity-100' : 'opacity-30 pointer-events-none'}`}>
                <input type="number" value={blurRadius} step={0.5} min={0.5} max={5}
                  onChange={e => setBlurRadius(+e.target.value)}
                  className="w-16 bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-xs text-slate-100 focus:outline-none focus:border-violet-500" />
                <span className="text-xs text-slate-500">radius</span>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 cursor-pointer select-none w-36 shrink-0">
                <input type="checkbox" checked={noise} onChange={e => setNoise(e.target.checked)} className="accent-violet-500" />
                <span className={`text-sm ${noise ? 'text-slate-200' : 'text-slate-500'}`}>Gaussian noise</span>
              </label>
              <div className={`flex items-center gap-1.5 transition-opacity ${noise ? 'opacity-100' : 'opacity-30 pointer-events-none'}`}>
                <input type="number" value={noiseStd} step={1} min={1} max={60}
                  onChange={e => setNoiseStd(+e.target.value)}
                  className="w-16 bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-xs text-slate-100 focus:outline-none focus:border-violet-500" />
                <span className="text-xs text-slate-500">std</span>
              </div>
            </div>
          </div>
        </div>

        {/* Rotation */}
        <div className="flex flex-col gap-2">
          <p className="text-xs text-slate-500 mb-1">Rotation</p>
          <div className="flex items-center gap-3 pl-2">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input type="checkbox" checked={rotation} onChange={e => setRotation(e.target.checked)} className="accent-violet-500" />
              <span className={`text-sm ${rotation ? 'text-slate-200' : 'text-slate-500'}`}>Random rotation</span>
            </label>
            <div className={`flex items-center gap-1.5 transition-opacity ${rotation ? 'opacity-100' : 'opacity-30 pointer-events-none'}`}>
              <input type="number" value={rotDeg} step={1} min={1} max={45}
                onChange={e => setRotDeg(+e.target.value)}
                className="w-16 bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-xs text-slate-100 focus:outline-none focus:border-violet-500" />
              <span className="text-xs text-slate-500">± °</span>
            </div>
          </div>
        </div>

        {/* Output options */}
        <div className="flex flex-col gap-1.5">
          <p className="text-xs text-slate-500 mb-1">Options</p>
          <div className="pl-2">
            <Toggle label="Only augment annotated images (skip unannotated)" checked={onlyAnnotated} onChange={setOnlyAnnotated} />
          </div>
        </div>
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
