// Shared augmentation settings panel used by both AugmentDataset and MergeDatasets

export interface AugmentConfig {
  copies: number
  flipH: boolean
  flipV: boolean
  brightness: boolean
  brightnessMin: number
  brightnessMax: number
  contrast: boolean
  contrastMin: number
  contrastMax: number
  saturation: boolean
  saturationMin: number
  saturationMax: number
  blur: boolean
  blurRadius: number
  noise: boolean
  noiseStd: number
  rotation: boolean
  rotDeg: number
  onlyAnnotated: boolean
  includeOriginals: boolean
}

export const DEFAULT_AUGMENT: AugmentConfig = {
  copies: 2,
  flipH: true,
  flipV: false,
  brightness: true,
  brightnessMin: 0.6,
  brightnessMax: 1.4,
  contrast: true,
  contrastMin: 0.6,
  contrastMax: 1.4,
  saturation: true,
  saturationMin: 0.5,
  saturationMax: 1.5,
  blur: false,
  blurRadius: 1.5,
  noise: false,
  noiseStd: 15,
  rotation: false,
  rotDeg: 15,
  onlyAnnotated: true,
  includeOriginals: true,
}

export function augmentConfigToPayload(c: AugmentConfig) {
  return {
    copies_per_image: c.copies,
    flip_horizontal: c.flipH,
    flip_vertical: c.flipV,
    brightness: c.brightness,
    brightness_range: [c.brightnessMin, c.brightnessMax],
    contrast: c.contrast,
    contrast_range: [c.contrastMin, c.contrastMax],
    saturation: c.saturation,
    saturation_range: [c.saturationMin, c.saturationMax],
    blur: c.blur,
    blur_radius: c.blurRadius,
    noise: c.noise,
    noise_std: c.noiseStd,
    rotation: c.rotation,
    rotation_degrees: c.rotDeg,
    only_annotated: c.onlyAnnotated,
    output_original: c.includeOriginals,
  }
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} className="accent-violet-500" />
      <span className={`text-sm ${checked ? 'text-slate-200' : 'text-slate-500'}`}>{label}</span>
    </label>
  )
}

interface Props {
  value: AugmentConfig
  onChange: (patch: Partial<AugmentConfig>) => void
}

export function AugmentSettings({ value: c, onChange }: Props) {
  const set = <K extends keyof AugmentConfig>(k: K) => (v: AugmentConfig[K]) => onChange({ [k]: v })

  return (
    <div className="flex flex-col gap-4">
      {/* Copies */}
      <div className="flex items-center gap-3">
        <label className="text-sm text-slate-400 w-36 shrink-0">Copies per image</label>
        <input
          type="number" min={1} max={10} value={c.copies}
          onChange={e => set('copies')(Math.max(1, Math.min(10, +e.target.value)))}
          className="w-20 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-sm text-slate-100 focus:outline-none focus:border-violet-500"
        />
        <span className="text-xs text-slate-500">(1–10)</span>
      </div>

      {/* Flips */}
      <div className="flex flex-col gap-1">
        <p className="text-xs text-slate-500 mb-1">Flips</p>
        <div className="flex gap-6 pl-2">
          <Toggle label="Flip horizontal" checked={c.flipH} onChange={set('flipH')} />
          <Toggle label="Flip vertical" checked={c.flipV} onChange={set('flipV')} />
        </div>
      </div>

      {/* Color */}
      <div className="flex flex-col gap-2">
        <p className="text-xs text-slate-500 mb-1">Color adjustments</p>
        <div className="flex flex-col gap-2 pl-2 border-l-2 border-slate-700">
          {([
            { label: 'Brightness', ek: 'brightness' as const, mink: 'brightnessMin' as const, maxk: 'brightnessMax' as const },
            { label: 'Contrast',   ek: 'contrast'   as const, mink: 'contrastMin'   as const, maxk: 'contrastMax'   as const },
            { label: 'Saturation', ek: 'saturation' as const, mink: 'saturationMin' as const, maxk: 'saturationMax' as const },
          ]).map(({ label, ek, mink, maxk }) => (
            <div key={label} className="flex items-center gap-3">
              <label className="flex items-center gap-2 cursor-pointer select-none w-28 shrink-0">
                <input type="checkbox" checked={c[ek] as boolean} onChange={e => set(ek)(e.target.checked as AugmentConfig[typeof ek])} className="accent-violet-500" />
                <span className={`text-sm ${c[ek] ? 'text-slate-200' : 'text-slate-500'}`}>{label}</span>
              </label>
              <div className={`flex items-center gap-1.5 transition-opacity ${c[ek] ? 'opacity-100' : 'opacity-30 pointer-events-none'}`}>
                <span className="text-xs text-slate-500">min</span>
                <input type="number" value={c[mink] as number} step={0.05} min={0.1} max={(c[maxk] as number) - 0.05}
                  onChange={e => set(mink)(+e.target.value as AugmentConfig[typeof mink])}
                  className="w-16 bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-xs text-slate-100 focus:outline-none focus:border-violet-500" />
                <span className="text-xs text-slate-500">max</span>
                <input type="number" value={c[maxk] as number} step={0.05} min={(c[mink] as number) + 0.05} max={3.0}
                  onChange={e => set(maxk)(+e.target.value as AugmentConfig[typeof maxk])}
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
              <input type="checkbox" checked={c.blur} onChange={e => set('blur')(e.target.checked)} className="accent-violet-500" />
              <span className={`text-sm ${c.blur ? 'text-slate-200' : 'text-slate-500'}`}>Gaussian blur</span>
            </label>
            <div className={`flex items-center gap-1.5 transition-opacity ${c.blur ? 'opacity-100' : 'opacity-30 pointer-events-none'}`}>
              <input type="number" value={c.blurRadius} step={0.5} min={0.5} max={5}
                onChange={e => set('blurRadius')(+e.target.value)}
                className="w-16 bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-xs text-slate-100 focus:outline-none focus:border-violet-500" />
              <span className="text-xs text-slate-500">radius</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 cursor-pointer select-none w-36 shrink-0">
              <input type="checkbox" checked={c.noise} onChange={e => set('noise')(e.target.checked)} className="accent-violet-500" />
              <span className={`text-sm ${c.noise ? 'text-slate-200' : 'text-slate-500'}`}>Gaussian noise</span>
            </label>
            <div className={`flex items-center gap-1.5 transition-opacity ${c.noise ? 'opacity-100' : 'opacity-30 pointer-events-none'}`}>
              <input type="number" value={c.noiseStd} step={1} min={1} max={60}
                onChange={e => set('noiseStd')(+e.target.value)}
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
            <input type="checkbox" checked={c.rotation} onChange={e => set('rotation')(e.target.checked)} className="accent-violet-500" />
            <span className={`text-sm ${c.rotation ? 'text-slate-200' : 'text-slate-500'}`}>Random rotation</span>
          </label>
          <div className={`flex items-center gap-1.5 transition-opacity ${c.rotation ? 'opacity-100' : 'opacity-30 pointer-events-none'}`}>
            <input type="number" value={c.rotDeg} step={1} min={1} max={45}
              onChange={e => set('rotDeg')(+e.target.value)}
              className="w-16 bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-xs text-slate-100 focus:outline-none focus:border-violet-500" />
            <span className="text-xs text-slate-500">± °</span>
          </div>
        </div>
      </div>

      {/* Options */}
      <div className="flex flex-col gap-1.5">
        <p className="text-xs text-slate-500 mb-1">Options</p>
        <div className="flex flex-col gap-1.5 pl-2">
          <Toggle label="Only augment annotated images (skip unannotated)" checked={c.onlyAnnotated} onChange={set('onlyAnnotated')} />
          <Toggle label="Include originals in output" checked={c.includeOriginals} onChange={set('includeOriginals')} />
        </div>
      </div>
    </div>
  )
}
