import { useState, useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { trainModel, cancelTrain, getActiveTrain, trainLogUrl, getJob } from '../../lib/api'
import { Button } from '../ui/Button'
import { PathInput } from '../ui/PathInput'
import { Spinner } from '../ui/Spinner'

const STORAGE_KEY = 'visionq_train_job'

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

// ── Progress bar ──────────────────────────────────────────────────────────────

function EpochProgress({ epoch, total }: { epoch: number; total: number }) {
  const pct = total > 0 ? Math.round((epoch / total) * 100) : 0
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-400">Epoch {epoch} / {total}</span>
        <span className="text-violet-400 font-medium">{pct}%</span>
      </div>
      <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-violet-500 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

// ── Active training banner (shown when navigating away) ───────────────────────

function StopButtons({ disabled }: { disabled: boolean }) {
  const qc = useQueryClient()
  const cancelMut = useMutation({
    mutationFn: (force: boolean) => cancelTrain(force),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['train-active'] }),
  })
  return (
    <div className="flex gap-2">
      <Button
        variant="ghost" size="sm"
        onClick={() => cancelMut.mutate(false)}
        disabled={disabled || cancelMut.isPending}
        title="Finish current epoch then stop"
      >
        {cancelMut.isPending ? <Spinner size={11} /> : '◻ After epoch'}
      </Button>
      <Button
        variant="danger" size="sm"
        onClick={() => cancelMut.mutate(true)}
        disabled={disabled || cancelMut.isPending}
        title="Kill training immediately"
      >
        {cancelMut.isPending ? <Spinner size={11} /> : '■ Stop now'}
      </Button>
    </div>
  )
}

function ActiveBanner({ runName, epoch, total, onAttach }: {
  runName: string; epoch: number; total: number; onAttach: () => void
}) {
  const pct = total > 0 ? Math.round((epoch / total) * 100) : 0

  return (
    <div className="bg-violet-900/20 border border-violet-500/40 rounded-xl p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-violet-400 animate-pulse" />
          <span className="text-sm font-semibold text-violet-200">Training in progress</span>
          <span className="text-xs text-slate-500 font-mono">{runName}</span>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={onAttach}>View log</Button>
          <StopButtons disabled={false} />
        </div>
      </div>
      <EpochProgress epoch={epoch} total={total} />
      {pct > 0 && <p className="text-xs text-slate-600">Epoch {epoch} of {total} complete ({pct}%)</p>}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function TrainModel() {
  const qc = useQueryClient()

  // Config state
  const [modelPreset, setModelPreset] = useState('yolo26n.pt')
  const [customModelPath, setCustomModelPath] = useState('')
  const [dataYaml, setDataYaml] = useState('')
  const [epochs, setEpochs] = useState(50)
  const [batch, setBatch] = useState(8)
  const [imgsz, setImgsz] = useState(640)
  const [patience, setPatience] = useState(15)
  const [runName, setRunName] = useState('my_training')

  // Job state — restored from localStorage on mount
  const [jobId, setJobId] = useState<string | null>(() => {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null') } catch { return null }
  })
  const [outputDir, setOutputDir] = useState('')
  const [logs, setLogs] = useState<string[]>([])
  const [logDone, setLogDone] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)
  const esRef = useRef<EventSource | null>(null)

  // Poll active job from server (survives refresh)
  const { data: activeData } = useQuery({
    queryKey: ['train-active'],
    queryFn: getActiveTrain,
    refetchInterval: 3000,
  })

  // Poll job status
  const { data: job } = useQuery({
    queryKey: ['train-job', jobId],
    queryFn: () => getJob(jobId!),
    enabled: !!jobId,
    refetchInterval: jobId ? 2000 : false,
  })

  const isRunning = !!jobId && (job?.status === 'running' || !job)
  const isDone    = job?.status === 'done'
  const isFailed  = job?.status === 'failed'
  const result    = job?.result as { best_model?: string; run_name?: string; output_dir?: string } | null

  const epoch      = job?.epoch ?? activeData?.epoch ?? 0
  const totalEpochs = job?.total_epochs ?? activeData?.total_epochs ?? epochs

  // If server has an active job but we lost our local jobId (page refresh), re-attach
  useEffect(() => {
    if (!jobId && activeData?.active && activeData.job_id) {
      setJobId(activeData.job_id)
      localStorage.setItem(STORAGE_KEY, JSON.stringify(activeData.job_id))
    }
  }, [activeData, jobId])

  // Persist jobId to localStorage
  useEffect(() => {
    if (jobId) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(jobId))
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  }, [jobId])

  // Connect SSE log stream when jobId is set
  useEffect(() => {
    if (!jobId) return
    setLogs([])
    setLogDone(false)
    esRef.current?.close()

    const es = new EventSource(trainLogUrl(jobId))
    esRef.current = es
    es.onmessage = (e) => setLogs(prev => [...prev, e.data])
    es.addEventListener('done', () => { setLogDone(true); es.close() })
    es.onerror = () => { setLogDone(true); es.close() }

    return () => es.close()
  }, [jobId])

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [logs])

  // Clear localStorage when job finishes
  useEffect(() => {
    if (isDone || isFailed) localStorage.removeItem(STORAGE_KEY)
  }, [isDone, isFailed])

  const mut = useMutation({
    mutationFn: () => trainModel({
      data_yaml: dataYaml,
      model: modelPreset === '__custom__' ? customModelPath : modelPreset,
      epochs, batch, imgsz, patience,
      run_name: runName.trim() || 'my_training',
    }),
    onSuccess: (data: { job_id: string; output_dir: string }) => {
      setJobId(data.job_id)
      setOutputDir(data.output_dir)
      qc.invalidateQueries({ queryKey: ['train-active'] })
    },
  })

  const reset = () => {
    esRef.current?.close()
    setJobId(null)
    setLogs([])
    setLogDone(false)
    setOutputDir('')
    mut.reset()
    qc.invalidateQueries({ queryKey: ['train-active'] })
  }

  const canRun = dataYaml &&
    (modelPreset !== '__custom__' || customModelPath) &&
    runName.trim() &&
    !isRunning

  // Server has a running job that isn't ours — show compact banner
  const serverHasOtherJob = activeData?.active && activeData.job_id !== jobId && !jobId

  return (
    <div className="flex flex-col gap-5 max-w-2xl">
      <div>
        <h2 className="text-base font-semibold text-slate-100 mb-1">Train Model</h2>
        <p className="text-sm text-slate-500">
          Train a YOLO model on the server using an exported dataset.
          Best weights are saved to <span className="font-mono text-slate-400">~/visionq-projects/models/&lt;run-name&gt;/weights/best.pt</span>.
        </p>
      </div>

      {/* Active training banner — when navigating back after starting a job */}
      {isRunning && logs.length === 0 && !logDone && (
        <ActiveBanner
          runName={activeData?.run_name ?? runName}
          epoch={epoch}
          total={totalEpochs}
          onAttach={() => {}}
        />
      )}

      {/* Banner for a job started from another session */}
      {serverHasOtherJob && (
        <ActiveBanner
          runName={activeData.run_name}
          epoch={activeData.epoch ?? 0}
          total={activeData.total_epochs ?? 0}
          onAttach={() => {
            setJobId(activeData.job_id)
            localStorage.setItem(STORAGE_KEY, JSON.stringify(activeData.job_id))
          }}
        />
      )}

      {/* ── Config (collapsed while running) ── */}
      {!isRunning && (
        <>
          <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-3">
            <SectionHeader label="Dataset" />
            <PathInput label="data.yaml path" value={dataYaml} onChange={setDataYaml}
              filter="yaml" placeholder="/data/my_export/data.yaml" pickerTitle="Select data.yaml file" />
            <p className="text-xs text-slate-600">
              Point to the <span className="font-mono">data.yaml</span> generated by Export or Merge. Must have train/val splits defined.
            </p>
          </div>

          <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-3">
            <SectionHeader label="Base Model" />
            <div className="flex flex-col gap-2">
              {PRESET_MODELS.map(m => (
                <label key={m.value} className="flex items-center gap-2.5 cursor-pointer text-sm select-none">
                  <input type="radio" name="model" value={m.value}
                    checked={modelPreset === m.value}
                    onChange={() => setModelPreset(m.value)}
                    className="accent-violet-500"
                  />
                  <span className={modelPreset === m.value ? 'text-slate-100' : 'text-slate-400'}>{m.label}</span>
                </label>
              ))}
            </div>
            {modelPreset === '__custom__' && (
              <PathInput label="Custom weights path" value={customModelPath} onChange={setCustomModelPath}
                filter="model" placeholder="/models/my_weights.pt" pickerTitle="Select .pt weights file" />
            )}
          </div>

          <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-4">
            <SectionHeader label="Hyperparameters" />
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <NumField label="Epochs" value={epochs} onChange={setEpochs} min={1} max={500} />
              <NumField label="Batch size" value={batch} onChange={setBatch} min={1} max={64} />
              <NumField label="Patience" value={patience} onChange={setPatience} min={1} max={200} />
              <div className="flex flex-col gap-1">
                <label className="text-xs text-slate-400">Image size</label>
                <select value={imgsz} onChange={e => setImgsz(+e.target.value)}
                  className="bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-100
                    focus:outline-none focus:border-violet-500">
                  {IMG_SIZES.map(s => <option key={s} value={s}>{s} px</option>)}
                </select>
              </div>
            </div>
          </div>

          <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-3">
            <SectionHeader label="Output" />
            <div className="flex flex-col gap-1">
              <label className="text-xs text-slate-400">Run name</label>
              <input value={runName} onChange={e => setRunName(e.target.value)} placeholder="my_training"
                className="bg-slate-800 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-100
                  focus:outline-none focus:border-violet-500" />
            </div>
            <p className="text-xs text-slate-600">
              Weights → <span className="font-mono text-slate-500">~/visionq-projects/models/{runName || 'my_training'}/weights/best.pt</span>
            </p>
          </div>
        </>
      )}

      {/* ── Log + progress (shown while running or after) ── */}
      {(jobId || logs.length > 0) && (
        <div className="bg-[#16213e] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <SectionHeader label="Training Log" />
            <div className="flex items-center gap-3">
              {isRunning && !logDone && <Spinner size={14} />}
              {isDone && <span className="text-xs text-green-400 font-medium">✓ Complete</span>}
              {isFailed && <span className="text-xs text-red-400 font-medium">✕ Failed</span>}
            </div>
          </div>

          {/* Progress bar — shown while running */}
          {isRunning && totalEpochs > 0 && (
            <EpochProgress epoch={epoch} total={totalEpochs} />
          )}

          <div ref={logRef}
            className="bg-[#0a0f1e] rounded-lg p-3 font-mono text-xs text-slate-300 overflow-y-auto"
            style={{ minHeight: 160, maxHeight: 400 }}
          >
            {logs.length === 0 ? (
              <span className="text-slate-600">Waiting for output…</span>
            ) : (
              logs.map((line, i) => {
                let cls = 'text-slate-400'
                if (line.startsWith('ERROR')) cls = 'text-red-400'
                else if (line.startsWith('Complete')) cls = 'text-green-400'
                else if (line.startsWith('Training cancelled')) cls = 'text-yellow-400'
                else if (line.startsWith('[')) cls = 'text-slate-200'
                else if (line.startsWith('─')) cls = 'text-slate-700'
                else if (/^(Model|Dataset|Config|Device|Output)/.test(line)) cls = 'text-violet-300'
                return <div key={i} className={cls}>{line}</div>
              })
            )}
          </div>

          {isDone && result?.best_model && (
            <div className="px-3 py-2 bg-green-900/20 border border-green-700/50 rounded-lg text-xs text-green-300">
              ✓ Best weights saved to: <span className="font-mono">{result.best_model}</span>
            </div>
          )}
        </div>
      )}

      {/* ── Cancelled / Failed summary card ── */}
      {isFailed && (
        <div className="bg-[#16213e] border border-red-700/40 rounded-xl p-4 flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <span className="text-red-400 text-sm">■</span>
            <span className="text-sm font-semibold text-red-300">
              {job?.error?.includes('cancel') || logs.some(l => l.toLowerCase().includes('cancel'))
                ? 'Training cancelled'
                : 'Training failed'}
            </span>
            {epoch > 0 && (
              <span className="text-xs text-slate-500 ml-1">
                — stopped at epoch {epoch} of {totalEpochs}
              </span>
            )}
          </div>
          {job?.error && !job.error.includes('cancel') && (
            <p className="text-xs text-red-400 font-mono">{job.error}</p>
          )}
          {epoch > 0 && (
            <p className="text-xs text-slate-500">
              YOLO may have saved intermediate weights from the last completed epoch in the run folder.
            </p>
          )}
          <div className="flex justify-end">
            <Button variant="primary" onClick={reset}>Start new run</Button>
          </div>
        </div>
      )}

      {/* ── Actions ── */}
      <div className="flex gap-2 justify-end">
        {isDone && (
          <Button variant="ghost" onClick={reset}>New training run</Button>
        )}
        {isRunning && <StopButtons disabled={false} />}
        {!isRunning && !isDone && !isFailed && (
          <Button variant="primary" disabled={!canRun || mut.isPending} onClick={() => mut.mutate()}>
            {mut.isPending ? <><Spinner size={12} /> Starting…</> : '⚡ Start Training'}
          </Button>
        )}
      </div>
    </div>
  )
}
