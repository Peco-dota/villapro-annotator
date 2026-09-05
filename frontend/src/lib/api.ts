import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL ?? ''

export const api = axios.create({
  baseURL: BASE,
  timeout: 30_000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('visionq_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('visionq_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export function sseUrl(path: string): string {
  const token = localStorage.getItem('visionq_token') ?? ''
  const base = BASE || window.location.origin
  return `${base}${path}?token=${encodeURIComponent(token)}`
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export const login = (username: string, password: string) =>
  api.post('/api/auth/login', { username, password }).then(r => r.data)
export const getMe = () => api.get('/api/auth/me').then(r => r.data)
export const changePassword = (current_password: string, new_password: string) =>
  api.post('/api/auth/change-password', { current_password, new_password }).then(r => r.data)

// ── System ────────────────────────────────────────────────────────────────────
export const getSystemInfo = () => api.get('/api/system/info').then(r => r.data)
export const getTokens = () => api.get('/api/system/tokens').then(r => r.data)
export const createToken = (label: string, services: string[] = [], permissions: string[] = ['stream', 'results']) =>
  api.post('/api/system/tokens', { label, services, permissions }).then(r => r.data)
export const revokeToken = (token: string) => api.delete(`/api/system/tokens/${token}`).then(r => r.data)
export const getSettings = () => api.get('/api/system/settings').then(r => r.data)
export const patchSettings = (data: Record<string, unknown>) => api.patch('/api/system/settings', data).then(r => r.data)

// ── Projects ──────────────────────────────────────────────────────────────────
export const getRecentProjects = (showAll = false) =>
  api.get('/api/projects/recent', { params: showAll ? { all: true } : {} }).then(r => r.data)
export const openProject = (path: string) => api.post('/api/projects/open', { path }).then(r => r.data)
export const createProject = (data: {
  name: string
  save_path: string
  image_folders: string[]
  classes?: string[]
  import_yolo_labels?: boolean
  coco_json_path?: string
}) => api.post('/api/projects/create', data).then(r => r.data)
export const closeProject = (path: string) => api.post('/api/projects/close', { path }).then(r => r.data)
export const removeRecentProject = (path: string) => api.delete('/api/projects/recent', { params: { path } }).then(r => r.data)
export const saveProject = (path: string) => api.post('/api/projects/save', null, { params: { path } }).then(r => r.data)
export const getProjectInfo = (path: string) => api.get('/api/projects/info', { params: { path } }).then(r => r.data)
export const getProjectImages = (path: string) => api.get('/api/projects/images', { params: { path } }).then(r => r.data)
export const getImageFile = (path: string, filename: string) => {
  const token = localStorage.getItem('visionq_token') ?? ''
  return `${BASE}/api/projects/images/file?path=${encodeURIComponent(path)}&filename=${encodeURIComponent(filename)}&token=${encodeURIComponent(token)}`
}
export const deleteImage = (path: string, filename: string) =>
  api.delete('/api/projects/images', { data: { path, filename } }).then(r => r.data)
export const rescanImages = (path: string) => api.post('/api/projects/images/rescan', { path }).then(r => r.data)

export const getClasses = (path: string) => api.get('/api/projects/classes', { params: { path } }).then(r => r.data)
export const addClass = (path: string, name: string, color?: string) =>
  api.post('/api/projects/classes', { path, name, color }).then(r => r.data)
export const updateClass = (path: string, index: number, name: string, color?: string) =>
  api.patch('/api/projects/classes', { path, index, name, color }).then(r => r.data)
export const deleteClass = (path: string, index: number) =>
  api.delete('/api/projects/classes', { data: { path, index } }).then(r => r.data)

// ── Annotations ───────────────────────────────────────────────────────────────
export const getAnnotations = (path: string, filename: string) =>
  api.get('/api/annotations/', { params: { project_path: path, filename } }).then(r => r.data)
export const addAnnotation = (project_path: string, filename: string, box: object) =>
  api.post('/api/annotations/', { project_path, filename, ...box }).then(r => r.data)
export const updateAnnotation = (project_path: string, filename: string, box_id: string, updates: object) =>
  api.patch('/api/annotations/', { project_path, filename, box_id, ...updates }).then(r => r.data)
export const deleteAnnotation = (project_path: string, filename: string, box_id: string) =>
  api.delete('/api/annotations/', { data: { project_path, filename, box_id } }).then(r => r.data)
export const replaceAnnotations = (project_path: string, filename: string, boxes: object[]) =>
  api.put('/api/annotations/replace', { project_path, filename, boxes }).then(r => r.data)
export const copyFromPrev = (project_path: string, filename: string) =>
  api.post('/api/annotations/copy-from-prev', null, { params: { project_path, filename } }).then(r => r.data)
export const navigate = (project_path: string, index: number) =>
  api.post('/api/annotations/navigate', null, { params: { project_path, index } }).then(r => r.data)

// ── Detection ─────────────────────────────────────────────────────────────────
export const getServices = () => api.get('/api/detection/services').then(r => r.data)
export const createService = (data: object) => api.post('/api/detection/services', data).then(r => r.data)
export const updateService = (_name: string, data: object) =>
  api.post('/api/detection/services', data).then(r => r.data)
export const duplicateService = (name: string, newName: string) =>
  api.post(`/api/detection/services/${name}/duplicate`, { new_name: newName }).then(r => r.data)
export const deleteService = (name: string) => api.delete(`/api/detection/services/${name}`).then(r => r.data)
export const startService = (name: string) => api.post(`/api/detection/services/${name}/start`).then(r => r.data)
export const stopService = (name: string) => api.post(`/api/detection/services/${name}/stop`).then(r => r.data)
export const restartService = (name: string) => api.post(`/api/detection/services/${name}/restart`).then(r => r.data)
export const getServiceStatus = (name: string) => api.get(`/api/detection/services/${name}/status`).then(r => r.data)
export const getServiceLog = (name: string) => api.get(`/api/detection/services/${name}/log`).then(r => r.data)
// Recording
export const startRecording = (name: string, dir?: string) =>
  api.post(`/api/detection/services/${name}/recording/start`, null, { params: dir ? { record_dir: dir } : {} }).then(r => r.data)
export const stopRecording = (name: string) =>
  api.post(`/api/detection/services/${name}/recording/stop`).then(r => r.data)
// Debug CSV
export const startDebug = (name: string, path?: string) =>
  api.post(`/api/detection/services/${name}/debug/start`, null, { params: path ? { path } : {} }).then(r => r.data)
export const stopDebug = (name: string) =>
  api.post(`/api/detection/services/${name}/debug/stop`).then(r => r.data)
// Dataset capture
export const startDataset = (name: string, dir?: string, interval?: number) =>
  api.post(`/api/detection/services/${name}/dataset/start`, null, {
    params: { ...(dir ? { dataset_dir: dir } : {}), ...(interval ? { interval } : {}) }
  }).then(r => r.data)
export const stopDataset = (name: string) =>
  api.post(`/api/detection/services/${name}/dataset/stop`).then(r => r.data)
// Preview
export const startPreview = (name: string) =>
  api.post(`/api/detection/services/${name}/preview/start`).then(r => r.data)
export const stopPreview = (name: string) =>
  api.post(`/api/detection/services/${name}/preview/stop`).then(r => r.data)
export const getPreviewFrameUrl = (name: string): string => {
  const token = localStorage.getItem('visionq_token') ?? ''
  const base = (import.meta.env.VITE_API_URL as string) || ''
  return `${base}/api/detection/services/${encodeURIComponent(name)}/preview/frame?token=${encodeURIComponent(token)}`
}
export const getMjpegStreamUrl = (name: string): string => {
  const token = localStorage.getItem('visionq_token') ?? ''
  const base = (import.meta.env.VITE_API_URL as string) || ''
  return `${base}/api/detection/services/${encodeURIComponent(name)}/preview/mjpeg?token=${encodeURIComponent(token)}`
}
// Video controls
export const videoSeek = (name: string, delta: number) =>
  api.post(`/api/detection/services/${name}/video/seek`, null, { params: { delta } }).then(r => r.data)
export const videoSeekTo = (name: string, ms: number) =>
  api.post(`/api/detection/services/${name}/video/seek`, null, { params: { ms } }).then(r => r.data)
export const videoSpeed = (name: string, speed: number) =>
  api.post(`/api/detection/services/${name}/video/speed`, null, { params: { speed } }).then(r => r.data)
export const videoPause = (name: string) =>
  api.post(`/api/detection/services/${name}/video/pause`).then(r => r.data)
export const videoStep = (name: string) =>
  api.post(`/api/detection/services/${name}/video/step`).then(r => r.data)
export const videoReverse = (name: string) =>
  api.post(`/api/detection/services/${name}/video/reverse`).then(r => r.data)
export const getVideoState = (name: string) =>
  api.get(`/api/detection/services/${name}/video/state`).then(r => r.data)
export const clearAllResults = () =>
  api.delete('/api/detection/results/all').then(r => r.data)
export const clearServiceResults = (name: string) =>
  api.delete(`/api/detection/results/${name}`).then(r => r.data)
// TCP push
export const startTcpPush = (name: string, data: object) =>
  api.post(`/api/detection/services/${name}/tcp/start`, data).then(r => r.data)
export const stopTcpPush = (name: string) =>
  api.post(`/api/detection/services/${name}/tcp/stop`).then(r => r.data)

// ── Counting ──────────────────────────────────────────────────────────────────
export const getCounters = () => api.get('/api/counting/services').then(r => r.data)
export const getCounter = (name: string) => api.get(`/api/counting/services/${name}`).then(r => r.data)
export const createCounter = (data: object) => api.post('/api/counting/services', data).then(r => r.data)
export const deleteCounter = (name: string) => api.delete(`/api/counting/services/${name}`).then(r => r.data)
export const startCounter = (name: string) => api.post(`/api/counting/services/${name}/start`).then(r => r.data)
export const stopCounter = (name: string) => api.post(`/api/counting/services/${name}/stop`).then(r => r.data)
export const getCounterStatus = (name: string) => api.get(`/api/counting/services/${name}/status`).then(r => r.data)
export const resetCounter = (name: string) => api.post(`/api/counting/services/${name}/reset`).then(r => r.data)
export const counterSseUrl = (name: string): string => sseUrl(`/api/counting/services/${name}/stream`)
export const getNdjsonStreamUrl = (name: string): string => sseUrl(`/api/detection/services/${name}/stream/ndjson`)

// ── Filesystem ───────────────────────────────────────────────────────────────
export type FsFilter = 'any' | 'project' | 'images_dir' | 'model' | 'video' | 'yaml' | 'dir' | '*'

export interface FileEntry {
  name: string
  size: number       // bytes
  modified: number   // unix timestamp (seconds)
  duration?: number | null  // seconds, videos only
}

export interface FsBrowseResult {
  cwd: string
  parent: string | null
  dirs: string[]
  files: FileEntry[]
}

export const browsePath = (path: string, filter: FsFilter = 'any'): Promise<FsBrowseResult> =>
  api.get('/api/fs/browse', { params: { path, filter } }).then(r => r.data)

export const getFsHome = (): Promise<{ home: string }> =>
  api.get('/api/fs/home').then(r => r.data)

export const uploadFile = (
  file: File,
  destDir: string,
  onProgress?: (pct: number) => void,
): Promise<{ path: string }> => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/api/fs/upload', form, {
    params: { dest: destDir },
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: e => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
    },
  }).then(r => r.data)
}

// ── Recordings ────────────────────────────────────────────────────────────────

export interface Recording {
  path: string
  filename: string
  service: string
  size_bytes: number
  created_at: number  // unix timestamp (seconds)
}

export const listRecordings = (): Promise<Recording[]> =>
  api.get('/api/recordings').then(r => r.data)

export const deleteRecording = (path: string): Promise<{ deleted: string }> =>
  api.delete('/api/recordings', { params: { path } }).then(r => r.data)

export const getRecordingDownloadUrl = (path: string): string => {
  const token = localStorage.getItem('visionq_token') ?? ''
  const base = (import.meta.env.VITE_API_URL as string) || ''
  return `${base}/api/recordings/download?path=${encodeURIComponent(path)}&token=${encodeURIComponent(token)}`
}

// ── Debug Logs ────────────────────────────────────────────────────────────────

export interface DebugLog {
  path: string
  filename: string
  service: string
  size_bytes: number
  created_at: number  // unix timestamp (seconds)
}

export const listDebugLogs = (): Promise<DebugLog[]> =>
  api.get('/api/debug-logs').then(r => r.data)

export const deleteDebugLog = (path: string): Promise<{ deleted: string }> =>
  api.delete('/api/debug-logs', { params: { path } }).then(r => r.data)

export const getDebugLogDownloadUrl = (path: string): string => {
  const token = localStorage.getItem('visionq_token') ?? ''
  const base = (import.meta.env.VITE_API_URL as string) || ''
  return `${base}/api/debug-logs/download?path=${encodeURIComponent(path)}&token=${encodeURIComponent(token)}`
}

export const fsMkdir = (parent: string, name: string): Promise<{ path: string }> =>
  api.post('/api/fs/mkdir', { parent, name }).then(r => r.data)

export const fsDelete = (path: string, recursive = false): Promise<{ deleted: string }> =>
  api.delete('/api/fs/delete', { data: { path, recursive } }).then(r => r.data)

export const fsMove = (src: string, dest: string): Promise<{ src: string; dest: string }> =>
  api.post('/api/fs/move', { src, dest }).then(r => r.data)

export const fsDownloadUrl = (path: string): string => {
  const token = localStorage.getItem('visionq_token') ?? ''
  const base = (import.meta.env.VITE_API_URL as string) || ''
  return `${base}/api/fs/download?path=${encodeURIComponent(path)}&token=${encodeURIComponent(token)}`
}

// ── Datasets ──────────────────────────────────────────────────────────────────
export const exportYolo = (data: object) => api.post('/api/datasets/export/yolo', data).then(r => r.data)
export const exportCoco = (data: object) => api.post('/api/datasets/export/coco', data).then(r => r.data)
export const exportBatch = (data: {
  sources: string[]
  output_dir: string
  split?: { train: number; val: number; test?: number }
  generate_yaml?: boolean
  augmentation?: object | null
}) => api.post('/api/datasets/export/batch', data).then(r => r.data)
export const augmentProject = (data: object) => api.post('/api/datasets/augment/project', data).then(r => r.data)
export const trainModel = (data: object) => api.post('/api/datasets/train', data).then(r => r.data)
export const cancelTrain = (force = false) => api.post('/api/datasets/train/cancel', null, { params: { force } }).then(r => r.data)
export const getActiveTrain = () => api.get('/api/datasets/train/active').then(r => r.data)
export const trainLogUrl = (jobId: string): string => sseUrl(`/api/datasets/train/log/${jobId}`)
export const getJob = (job_id: string) => api.get(`/api/datasets/jobs/${job_id}`).then(r => r.data)
export const cancelJob = (job_id: string) => api.post(`/api/datasets/jobs/${job_id}/cancel`).then(r => r.data)
export const autoAnnotate = (data: { project_path: string; model_path: string; confidence: number; iou: number; skip_annotated: boolean }) =>
  api.post('/api/datasets/auto-annotate', data).then(r => r.data)
export const getActiveAugJob = () => api.get('/api/datasets/augment/active').then(r => r.data)
export const getActiveMergeJob = () => api.get('/api/datasets/merge/active').then(r => r.data)
export const dismissMergeJob = () => api.delete('/api/datasets/merge/active').then(r => r.data)

export interface TrainHistoryEntry {
  job_id: string
  run_name: string
  model: string
  data_yaml: string
  epochs_requested: number
  epochs_completed: number
  status: 'done' | 'failed' | 'cancelled'
  started_at: string | null
  finished_at: string | null
  output_dir: string
  best_model: string
  device: string
  metrics: { precision: number; recall: number; mAP50: number; 'mAP50-95': number } | null
}

export const getTrainHistory = (): Promise<TrainHistoryEntry[]> =>
  api.get('/api/datasets/train/history').then(r => r.data)

export const deleteTrainHistoryEntry = (job_id: string) =>
  api.delete(`/api/datasets/train/history/${job_id}`).then(r => r.data)
