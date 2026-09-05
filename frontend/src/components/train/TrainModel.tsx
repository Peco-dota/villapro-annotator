import { useState, useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { trainModel, cancelTrain, getActiveTrain, trainLogUrl, getJob, getTrainHistory, deleteTrainHistoryEntry } from '../../lib/api'
import type { TrainHistoryEntry } from '../../lib/api'
import { Button } from '../ui/Button'
import { PathInput } from '../ui/PathInput'
import { Spinner } from '../ui/Spinner'

const STORAGE_KEY = 'visionq_train_job'

// ── Training history ──────────────────────────────────────────────────────────

const STATUS_STYLE: Record<string, string> = {
  done:      'bg-green-900/30 text-green-400 border-green-700/40',
  failed:    'bg-red-900/30 text-red-400 border-red-700/40',
  cancelled: 'bg-slate-800 text-slate-400 border-slate-600',
}

function TrainHistory({ onUseModel }: { onUseModel: (path: string) => void }) {
  const qc = useQueryClient()
  const { data: history = [], isLoading } = useQuery({
    queryKey: ['train-history'],
    queryFn: getTrainHistory,
  })
  const delMut = useMutation({
    mutationFn: deleteTrainHistoryEntry,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['train-history'] }),
  })
  const [confirmId, setConfirmId] = useState<string | null>(null)

  const fmtDate = (iso: string | null) =>
    iso ? new Date(iso).toLocaleString() : '—'

  if (isLoading) return null
  if (history.length === 0) return (
    <div className="border border-dashed border-[#1e293b] rounded-xl p-8 text-center text-slate-600 text-sm">
      No training runs yet — history will appear here after your first run.
    </div>
  )

  return (
    <div className="border border-[#1e293b] rounded-xl overflow-hidden">
      <div className="px-4 py-2.5 bg-[#0f172a] border-b border-[#1e293b]">
        <span className="text-sm font-medium text-slate-200">Training History</span>
        <span className="text-xs text-slate-600 ml-2">{history.length} run{history.length !== 1 ? 's' : ''}</span>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[#1e293b] bg-[#0a0f1e]">
            {['Run', 'Date', 'Status', 'Epochs', 'mAP50', 'mAP50-95', ''].map(h => (
              <th key={h} className="px-3 py-2 text-left text-xs font-bold text-slate-600 uppercase tracking-wider">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {history.map((e: TrainHistoryEntry) => (
            <tr key={e.job_id} className="border-b border-[#1e293b]/50 hover:bg-[#1e293b]/20 transition-colors">
              <td className="px-3 py-2.5">
                <p className="text-slate-200 text-xs font-medium">{e.run_name}</p>
                <p className="text-slate-600 text-[10px] font-mono mt-0.5">{e.model}</p>
              </td>
              <td className="px-3 py-2.5 text-xs text-slate-500 whitespace-nowrap">{fmtDate(e.started_at)}</td>
              <td className="px-3 py-2.5">
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${STATUS_STYLE[e.status] ?? STATUS_STYLE.cancelled}`}>
                  {e.status.toUpperCase()}
                </span>
              </td>
              <td className="px-3 py-2.5 text-xs text-slate-400">
                {e.epochs_completed}/{e.epochs_requested}
              </td>
              <td className="px-3 py-2.5 text-xs font-mono text-violet-400">
                {e.metrics ? e.metrics.mAP50.toFixed(3) : '—'}
              </td>
              <td className="px-3 py-2.5 text-xs font-mono text-violet-300">
                {e.metrics ? e.metrics['mAP50-95'].toFixed(3) : '—'}
              </td>
              <td className="px-3 py-2.5">
                <div className="flex items-center gap-2 justify-end">
                  {e.best_model && (
                    <button
                      onClick={() => onUseModel(e.best_model)}
                      className="text-xs text-violet-400 hover:text-violet-300 cursor-pointer transition-colors whitespace-nowrap"
                      title={e.best_model}
                    >
                      Use model
                    </button>
                  )}
                  {confirmId === e.job_id ? (
                    <span className="flex items-center gap-1">
                      <button
                        onClick={() => { delMut.mutate(e.job_id); setConfirmId(null) }}
                        className="text-xs text-red-400 hover:text-red-300 cursor-pointer font-medium"
                      >
                        Confirm
                      </button>
                      <span className="text-slate-700">|</span>
                      <button onClick={() => setConfirmId(null)} className="text-xs text-slate-500 hover:text-slate-300 cursor-pointer">
                        Cancel
                      </button>
                    </span>
                  ) : (
                    <button
                      onClick={() => setConfirmId(e.job_id)}
                      className="text-xs text-slate-600 hover:text-red-400 cursor-pointer transition-colors"
                    >
                      Delete
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

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

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDuration(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`
  const m = Math.floor(sec / 60), s = Math.round(sec % 60)
  if (m < 60) return s > 0 ? `${m}m ${s}s` : `${m}m`
  const h = Math.floor(m / 60), rm = m % 60
  return rm > 0 ? `${h}h ${rm}m` : `${h}h`
}

type Metrics = { precision: number; recall: number; mAP50: number; 'mAP50-95': number }

function LiveMetrics({ metrics }: { metrics: Metrics }) {
  const items = [
    { label: 'mAP50',    value: metrics.mAP50,          color: 'text-violet-400' },
    { label: 'mAP50-95', value: metrics['mAP50-95'],    color: 'text-violet-300' },
    { label: 'Precision', value: metrics.precision,     color: 'text-sky-400' },
    { label: 'Recall',   value: metrics.recall,         color: 'text-teal-400' },
  ]
  return (
    <div className="grid grid-cols-4 gap-2">
      {items.map(({ label, value, color }) => (
        <div key={label} className="flex flex-col items-center gap-0.5 bg-slate-800/60 rounded-lg py-2.5">
          <span className={`text-sm font-bold font-mono ${color}`}>{value.toFixed(3)}</span>
          <span className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</span>
        </div>
      ))}
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
  const dismissedJobRef = useRef<string | null>(null)
  const [logs, setLogs] = useState<string[]>([])
  const [logDone, setLogDone] = useState(false)
  const [logOpen, setLogOpen] = useState(false)
  const [now, setNow] = useState(() => Date.now())
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

  const epoch        = job?.epoch ?? activeData?.epoch ?? 0
  const totalEpochs  = job?.total_epochs ?? activeData?.total_epochs ?? epochs
  const lastMetrics  = (job?.last_metrics ?? activeData?.last_metrics) as Metrics | null | undefined
  const curBatch     = job?.batch ?? activeData?.batch ?? 0
  const totalBatches = job?.total_batches ?? activeData?.total_batches ?? 0

  const epochStartAt       = (job?.epoch_start_at        ?? activeData?.epoch_start_at)        as string | undefined
  const lastEpochDurationS = (job?.last_epoch_duration_s ?? activeData?.last_epoch_duration_s) as number | undefined

  // Use last measured epoch duration as the per-epoch estimate — accurate and
  // doesn't drift upward while waiting between epochs like elapsed-time approaches do.
  const remaining = lastEpochDurationS !== undefined && epoch < totalEpochs
    ? lastEpochDurationS * (totalEpochs - epoch)
    : null

  // Within-epoch ETA from batch timing
  const epochElapsed   = epochStartAt && isRunning && curBatch > 0 ? (now - Date.parse(epochStartAt)) / 1000 : null
  const batchesPerSec  = epochElapsed && curBatch > 0 ? curBatch / epochElapsed : null
  const epochRemaining = batchesPerSec && totalBatches > curBatch ? (totalBatches - curBatch) / batchesPerSec : null

  // Smooth combined progress: completed epochs + fraction through current epoch
  const smoothPct = totalEpochs > 0
    ? totalBatches > 0 && isRunning
      ? ((epoch + curBatch / totalBatches) / totalEpochs) * 100
      : (epoch / totalEpochs) * 100
    : 0

  // If server has an active job but we lost our local jobId (page refresh), re-attach
  useEffect(() => {
    if (!jobId && activeData?.active && activeData.job_id && activeData.job_id !== dismissedJobRef.current) {
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

  // Tick every second while running for live time display
  useEffect(() => {
    if (!isRunning) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [isRunning])

  // Auto-open log when job finishes so the user can see the result
  useEffect(() => {
    if (isDone || isFailed) setLogOpen(true)
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
      qc.invalidateQueries({ queryKey: ['train-active'] })
    },
  })

  const reset = () => {
    if (jobId) dismissedJobRef.current = jobId
    esRef.current?.close()
    setJobId(null)
    setLogs([])
    setLogDone(false)
    mut.reset()
    qc.invalidateQueries({ queryKey: ['train-active'] })
  }

  const canRun = dataYaml &&
    (modelPreset !== '__custom__' || customModelPath) &&
    runName.trim() &&
    !isRunning

  // Server has a running job that isn't ours — show compact banner
  const serverHasOtherJob = activeData?.active && activeData?.status === 'running' && activeData.job_id !== jobId && !jobId

  return (
    <div className="flex flex-col gap-5 max-w-2xl">
      <div>
        <h2 className="text-base font-semibold text-slate-100 mb-1">Train Model</h2>
        <p className="text-sm text-slate-500">
          Train a YOLO model on the server using an exported dataset.
          Best weights are saved to <span className="font-mono text-slate-400">/villapro-data/models/&lt;run-name&gt;/weights/best.pt</span>.
        </p>
      </div>

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
              Weights → <span className="font-mono text-slate-500">/villapro-data/models/{runName || 'my_training'}/weights/best.pt</span>
            </p>
          </div>
        </>
      )}

      {/* ── Training status card (running / done / failed) ── */}
      {(jobId || logs.length > 0) && (
        <div className="flex flex-col gap-2">
          {/* Main status card */}
          <div className={`border rounded-xl p-4 flex flex-col gap-3 ${
            isDone    ? 'bg-green-950/30 border-green-700/40' :
            isFailed  ? 'bg-red-950/20 border-red-700/40' :
                        'bg-violet-900/10 border-violet-500/30'
          }`}>
            {/* Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                {isRunning && <div className="w-2 h-2 rounded-full bg-violet-400 animate-pulse shrink-0" />}
                {isDone    && <span className="text-green-400 shrink-0">✓</span>}
                {isFailed  && <span className="text-red-400 shrink-0">✕</span>}
                <span className="text-sm font-semibold text-slate-200">
                  {isRunning ? 'Training in progress' :
                   isDone    ? 'Training complete' :
                   (job?.error?.includes('Cancelled') || job?.error?.includes('Force-stopped'))
                     ? 'Training cancelled' : 'Training failed'}
                </span>
                <span className="text-xs text-slate-500 font-mono truncate">
                  {activeData?.run_name ?? runName}
                </span>
              </div>
              {isRunning && <StopButtons disabled={false} />}
            </div>

            {/* Progress bar + time */}
            {totalEpochs > 0 && (
              <div className="flex flex-col gap-1.5">
                <div className="h-3 bg-slate-700/60 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${isDone ? 'bg-green-500' : 'bg-violet-500'}`}
                    style={{ width: `${smoothPct}%` }}
                  />
                </div>
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-slate-400">Epoch {epoch} / {totalEpochs}</span>
                    {isRunning && totalBatches > 0 && (
                      <span className="text-slate-600">
                        · batch {curBatch} / {totalBatches}
                        {batchesPerSec && batchesPerSec > 0 && (
                          <span className="text-slate-700 ml-1">({batchesPerSec.toFixed(1)} it/s)</span>
                        )}
                        {epochRemaining !== null && (
                          <span className="text-slate-600 ml-1">· ~{fmtDuration(epochRemaining)} left in epoch</span>
                        )}
                      </span>
                    )}
                    {epoch === 0 && isRunning && totalBatches === 0 && (
                      <span className="text-slate-600">— loading dataset…</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    {remaining !== null && (
                      <span className="text-slate-500">~{fmtDuration(remaining)} remaining</span>
                    )}
                    {lastEpochDurationS !== undefined && (
                      <span className="text-slate-600">last epoch {fmtDuration(lastEpochDurationS)}</span>
                    )}
                    <span className={`font-medium ${isDone ? 'text-green-400' : 'text-violet-400'}`}>
                      {Math.round(smoothPct)}%
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Live metrics — shown after first epoch */}
            {lastMetrics && <LiveMetrics metrics={lastMetrics} />}

            {/* Best model path */}
            {isDone && result?.best_model && (
              <div className="px-3 py-2 bg-green-900/20 border border-green-700/50 rounded-lg text-xs text-green-300">
                Best weights → <span className="font-mono">{result.best_model}</span>
              </div>
            )}

            {/* Failed extra info */}
            {isFailed && (
              <>
                {job?.error && !job.error.includes('Cancelled') && !job.error.includes('Force-stopped') && (
                  <p className="text-xs text-red-400 font-mono">{job.error}</p>
                )}
                {epoch > 0 && (
                  <p className="text-xs text-slate-500">
                    YOLO may have saved intermediate weights from the last completed epoch in the run folder.
                  </p>
                )}
              </>
            )}

            {/* New run button */}
            {(isDone || isFailed) && (
              <div className="flex justify-end">
                <Button variant={isDone ? 'ghost' : 'primary'} size="sm" onClick={reset}>
                  {isDone ? 'New training run' : 'Start new run'}
                </Button>
              </div>
            )}
          </div>

          {/* Collapsible log */}
          <div className="bg-[#16213e] border border-[#1e293b] rounded-xl overflow-hidden">
            <button
              onClick={() => setLogOpen(o => !o)}
              className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-[#1a2744] transition-colors cursor-pointer"
            >
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Training Log</span>
                {logs.length > 0 && (
                  <span className="text-xs text-slate-700">{logs.length} lines</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                {isRunning && !logDone && <Spinner size={12} />}
                <span className="text-xs text-slate-600">{logOpen ? '▲' : '▼'}</span>
              </div>
            </button>
            {logOpen && (
              <div className="px-4 pb-4">
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
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Actions ── */}
      {!isRunning && !isDone && !isFailed && (
        <div className="flex gap-2 justify-end">
          <Button variant="primary" disabled={!canRun || mut.isPending} onClick={() => mut.mutate()}>
            {mut.isPending ? <><Spinner size={12} /> Starting…</> : '⚡ Start Training'}
          </Button>
        </div>
      )}

      <TrainHistory onUseModel={(path) => {
        setModelPreset('__custom__')
        setCustomModelPath(path)
      }} />
    </div>
  )
}
