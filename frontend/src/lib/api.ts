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

// ── System ────────────────────────────────────────────────────────────────────
export const getSystemInfo = () => api.get('/api/system/info').then(r => r.data)
export const getTokens = () => api.get('/api/system/tokens').then(r => r.data)
export const createToken = (label: string) => api.post('/api/system/tokens', { label }).then(r => r.data)
export const revokeToken = (token: string) => api.delete(`/api/system/tokens/${token}`).then(r => r.data)
export const getSettings = () => api.get('/api/system/settings').then(r => r.data)
export const patchSettings = (data: Record<string, unknown>) => api.patch('/api/system/settings', data).then(r => r.data)

// ── Projects ──────────────────────────────────────────────────────────────────
export const getRecentProjects = () => api.get('/api/projects/recent').then(r => r.data)
export const openProject = (path: string) => api.post('/api/projects/open', { path }).then(r => r.data)
export const createProject = (data: { name: string; path: string; images_dir: string }) =>
  api.post('/api/projects/create', data).then(r => r.data)
export const closeProject = (path: string) => api.post('/api/projects/close', { path }).then(r => r.data)
export const saveProject = (path: string) => api.post('/api/projects/save', { path }).then(r => r.data)
export const getProjectInfo = (path: string) => api.get('/api/projects/info', { params: { path } }).then(r => r.data)
export const getProjectImages = (path: string) => api.get('/api/projects/images', { params: { path } }).then(r => r.data)
export const getImageFile = (path: string, filename: string) =>
  `${BASE}/api/projects/images/file?path=${encodeURIComponent(path)}&filename=${encodeURIComponent(filename)}`
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
  api.get('/api/annotations/', { params: { path, filename } }).then(r => r.data)
export const addAnnotation = (data: object) => api.post('/api/annotations/', data).then(r => r.data)
export const updateAnnotation = (data: object) => api.patch('/api/annotations/', data).then(r => r.data)
export const deleteAnnotation = (path: string, filename: string, box_id: string) =>
  api.delete('/api/annotations/', { data: { path, filename, box_id } }).then(r => r.data)
export const replaceAnnotations = (data: object) => api.put('/api/annotations/replace', data).then(r => r.data)
export const copyFromPrev = (path: string, filename: string) =>
  api.post('/api/annotations/copy-from-prev', { path, filename }).then(r => r.data)
export const navigate = (path: string, filename: string, direction: 'prev' | 'next') =>
  api.post('/api/annotations/navigate', { path, filename, direction }).then(r => r.data)

// ── Detection ─────────────────────────────────────────────────────────────────
export const getServices = () => api.get('/api/detection/services').then(r => r.data)
export const createService = (data: object) => api.post('/api/detection/services', data).then(r => r.data)
export const updateService = (name: string, data: object) =>
  api.patch(`/api/detection/services/${name}`, data).then(r => r.data)
export const deleteService = (name: string) => api.delete(`/api/detection/services/${name}`).then(r => r.data)
export const startService = (name: string) => api.post(`/api/detection/services/${name}/start`).then(r => r.data)
export const stopService = (name: string) => api.post(`/api/detection/services/${name}/stop`).then(r => r.data)
export const getServiceStatus = (name: string) => api.get(`/api/detection/services/${name}/status`).then(r => r.data)
export const getServiceLog = (name: string) => api.get(`/api/detection/services/${name}/log`).then(r => r.data)

// ── Datasets ──────────────────────────────────────────────────────────────────
export const exportYolo = (data: object) => api.post('/api/datasets/export/yolo', data).then(r => r.data)
export const exportCoco = (data: object) => api.post('/api/datasets/export/coco', data).then(r => r.data)
export const exportBatch = (data: object) => api.post('/api/datasets/export/batch', data).then(r => r.data)
export const augmentProject = (data: object) => api.post('/api/datasets/augment/project', data).then(r => r.data)
export const trainModel = (data: object) => api.post('/api/datasets/train', data).then(r => r.data)
export const getJob = (job_id: string) => api.get(`/api/datasets/jobs/${job_id}`).then(r => r.data)
