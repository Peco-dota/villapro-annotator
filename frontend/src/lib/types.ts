export interface ClassDef {
  name: string
  color: string
}

export interface BoundingBox {
  id: string
  class_index: number
  cx: number
  cy: number
  w: number
  h: number
}

export interface ProjectInfo {
  name: string
  path: string
  images_dir: string
  image_count: number
  annotated_count: number
  classes: ClassDef[]
  created_at: string
  modified_at: string
}

export interface ImageEntry {
  filename: string
  width: number
  height: number
  box_count: number
}

export interface ServiceConfig {
  name: string
  model_path: string
  mode: 'http' | 'rtsp' | 'video'
  source: string
  confidence: number
  iou: number
  device: string
  imgsz: number
  classes: number[]
  gate_area_threshold: number
  auto_start: boolean
  record_video: boolean
  record_dir: string
  debug_csv: boolean
  tcp_host: string
  tcp_port: number
  tcp_ssl: boolean
  preview: boolean
}

export interface ServiceStatus {
  name: string
  running: boolean
  direction: string
  gate_open: boolean
  fps: number
  frame_count: number
  error: string | null
}

export interface DetectionResult {
  service: string
  timestamp: number
  boxes: Array<{
    class_id: number
    class_name: string
    confidence: number
    bbox: [number, number, number, number]
  }>
  direction: string
  gate_open: boolean
  fps: number
}

export interface JobStatus {
  job_id: string
  status: 'running' | 'done' | 'failed'
  result: Record<string, unknown> | null
  error: string | null
}

export interface Token {
  token: string
  label: string
  created_at: string
}
