import { useState, useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { trainModel, trainLogUrl } from '../../lib/api'
import { Button } from '../ui/Button'
import { PathInput } from '../ui/PathInput'
import { Spinner } from '../ui/Spinner'
import { useJobPoller } from '../../lib/useJobPoller'

function SectionHeader({ label }: { label: string }) {
  return <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">{label}</p>
}

const PRESET_MODELS = [
  { label: 'YOLO26n  —  Nano (fastest, least accurate)', value: 'yolo26n.pt' },
  { label: 'YOLO26s  —  Small (good balance)', value: 'yolo26s.pt' },
  { label: 'YOLO26m  —  Medium', value: 'yolo26m.pt' },
  { label: 'YOLO26l  —  Large', value: 'yolo26l.pt' },
  { label: 'YOLO26x  —  XLarge (most accurate, slowest)', value: 'yolo26x.pt' },
  { label: 'Custom .pt file…', value: '__custom__' },
]

const IMG_SIZES = [320, 416, 512, 640, 768, 1024]

function NumField({ label, value, onChange, min, max }: {
  label: string; value: number; onChange: (v: number) => void; min: number; max: number
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-slate-400">{label}</label>
      <input
        type="number" value={value} min={min} max={max}
        onChange={e => onChange(Math.max(min, Math.min(max, +e.target.value)))}
        className="w-full bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-100
          focus:outline-none focus:border-violet-500"
      />
    </div>
  )
}

export function TrainModel() {
  // Model
  const [modelPreset, setModelPreset] = useState('yolo26n.pt')
  const [customModelPath, setCustomModelPath] = useState('')

  // Dataset — either pick a data.yaml directly
  const [dataYaml, setDataYaml] = useState('')

  // Hyperparams
  const [epochs, setEpochs] = useState(50)
  const [batch, setBatch] = useState(8)
  const [imgsz, setImgsz] = useState(640)
  const [patience, setPatience] = useState(15)

  // Output
  const [runName, setRunName] = useState('my_training')

  // Job / log state
  const [jobId, setJobId] = useState<string | null>(null)
  const [outputDir, setOutputDir] = useState('')
  const [logs, setLogs] = useState<string[]>([])
  const [logDone, setLogDone] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)
  const esRef = useRef<EventSource | null>(null)

  const job = useJobPoller(jobId)

  const isRunning = !!jobId && (job?.status === 'running' || !job)
  const isDone = job?.status === 'done'
  const isFailed = job?.status === 'failed'
  const result = job?.result as { best_model?: string; run_name?: string; output_dir?: string; device?: string } | null

  // Open SSE log stream once jobId is set
  useEffect(() => {
    if (!jobId) return
    setLogs([])
    setLogDone(false)

    const url = trainLogUrl(jobId)
    const es = new EventSource(url)
    esRef.current = es

    es.onmessage = (e) => {
      setLogs(prev => [...prev, e.data])
    }
    es.addEventListener('done', () => {
      setLogDone(true)
      es.close()
    })
    es.onerror = () => {
      setLogDone(true)
      es.close()
    }

    return () => { es.close() }
  }, [jobId])

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [logs])

  const mut = useMutation({
    mutationFn: () => trainModel({
      data_yaml: dataYaml,
      model: modelPreset === '__custom__' ? customModelPath : modelPreset,
      epochs,
      batch,
      imgsz,
      patience,
      run_name: runName.trim() || 'my_training',
    }),
    onSuccess: (data: { job_id: string; output_dir: string }) => {
      setJobId(data.job_id)
      setOutputDir(data.output_dir)
    },
  })

  const reset = () => {
    esRef.current?.close()
    setJobId(null)
    setLogs([])
    setLogDone(false)
    setOutputDir('')
    mut.reset()
  }

  const canRun = dataYaml &&
    (modelPreset !== '__custom__' || customModelPath) &&
    runName.trim() &&
    !isRunning

  const isCustom = modelPreset === '__custom__'

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <div>
        <h2 className="text-base font-semibold text-slate-100 mb-1">Train Model</h2>
        <p className="text-sm text-slate-500">
          Train a YOLO model on the server using an exported dataset.
          The best weights are saved to <span className="font-mono text-slate-400">~/visionq-projects/models/&lt;run-name&gt;/weights/best.pt</span>.
        </p>
      </div>

      {/* ── Dataset ── */}
      <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-3">
        <SectionHeader label="Dataset" />
        <PathInput
          label="data.yaml path"
          value={dataYaml}
          onChange={setDataYaml}
          filter="yaml"
          placeholder="/data/my_export/data.yaml"
          pickerTitle="Select data.yaml file"
        />
        <p className="text-xs text-slate-600">
          Point to the <span className="font-mono">data.yaml</span> generated by Export or Merge. Must have train/val splits defined.
        </p>
      </div>

      {/* ── Model ── */}
      <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-3">
        <SectionHeader label="Base Model" />
        <div className="flex flex-col gap-2">
          {PRESET_MODELS.map(m => (
            <label key={m.value} className="flex items-center gap-2.5 cursor-pointer text-sm select-none">
              <input
                type="radio" name="model" value={m.value}
                checked={modelPreset === m.value}
                onChange={() => setModelPreset(m.value)}
                className="accent-violet-500"
              />
              <span className={modelPreset === m.value ? 'text-slate-100' : 'text-slate-400'}>{m.label}</span>
            </label>
          ))}
        </div>
        {isCustom && (
          <PathInput
            label="Custom weights path"
            value={customModelPath}
            onChange={setCustomModelPath}
            filter="model"
            placeholder="/models/my_weights.pt"
            pickerTitle="Select .pt weights file"
          />
        )}
      </div>

      {/* ── Hyperparameters ── */}
      <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-4">
        <SectionHeader label="Hyperparameters" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <NumField label="Epochs" value={epochs} onChange={setEpochs} min={1} max={500} />
          <NumField label="Batch size" value={batch} onChange={setBatch} min={1} max={64} />
          <NumField label="Patience" value={patience} onChange={setPatience} min={1} max={200} />
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400">Image size</label>
            <select
              value={imgsz}
              onChange={e => setImgsz(+e.target.value)}
              className="bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-100
                focus:outline-none focus:border-violet-500"
            >
              {IMG_SIZES.map(s => <option key={s} value={s}>{s} px</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* ── Output ── */}
      <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-3">
        <SectionHeader label="Output" />
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-400">Run name</label>
          <input
            value={runName}
            onChange={e => setRunName(e.target.value)}
            placeholder="my_training"
            className="bg-slate-800 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-100
              focus:outline-none focus:border-violet-500"
          />
        </div>
        <p className="text-xs text-slate-600">
          Weights will be saved to <span className="font-mono text-slate-500">~/visionq-projects/models/{runName || 'my_training'}/weights/best.pt</span>
        </p>
      </div>

      {/* ── Log ── */}
      {(jobId || logs.length > 0) && (
        <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-2">
          <div className="flex items-center justify-between mb-1">
            <SectionHeader label="Training Log" />
            {isRunning && !logDone && <Spinner size={14} />}
            {isDone && <span className="text-xs text-green-400 font-medium">Complete</span>}
            {isFailed && <span className="text-xs text-red-400 font-medium">Failed</span>}
          </div>
          <div
            ref={logRef}
            className="bg-[#0a0f1e] rounded-lg p-3 font-mono text-xs text-slate-300 overflow-y-auto"
            style={{ minHeight: 160, maxHeight: 320 }}
          >
            {logs.length === 0 ? (
              <span className="text-slate-600">Waiting for output…</span>
            ) : (
              logs.map((line, i) => {
                let cls = 'text-slate-400'
                if (line.startsWith('ERROR')) cls = 'text-red-400'
                else if (line.startsWith('Complete')) cls = 'text-green-400'
                else if (line.startsWith('[')) cls = 'text-slate-200'  // epoch lines — bright
                else if (line.startsWith('─')) cls = 'text-slate-600'
                else if (line.startsWith('Model') || line.startsWith('Dataset') || line.startsWith('Config') || line.startsWith('Device') || line.startsWith('Output')) cls = 'text-violet-300'
                return <div key={i} className={cls}>{line}</div>
              })
            )}
          </div>

          {isDone && result?.best_model && (
            <div className="mt-1 px-3 py-2 bg-green-900/20 border border-green-700 rounded-lg text-xs text-green-300">
              Best weights saved to: <span className="font-mono">{result.best_model}</span>
            </div>
          )}
        </div>
      )}

      {/* ── Error ── */}
      {isFailed && (
        <div className="px-4 py-3 bg-red-900/20 border border-red-700 rounded-xl text-sm text-red-300">
          Training failed: {job?.error}
        </div>
      )}

      {/* ── Actions ── */}
      <div className="flex gap-2 justify-end">
        {(isDone || isFailed) && (
          <Button variant="ghost" onClick={reset}>Reset</Button>
        )}
        <Button variant="primary" disabled={!canRun} onClick={() => mut.mutate()}>
          {isRunning ? <><Spinner size={12} /> Training…</> : '⚡ Start Training'}
        </Button>
      </div>
    </div>
  )
}
