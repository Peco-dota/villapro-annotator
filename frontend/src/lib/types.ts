export interface ClassDef {
  id: number
  name: string
  color: string
  annotation_count?: number
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
  input_mode: 'http' | 'rtsp' | 'video' | 'udp_stream' | 'udp_packet'
  // HTTP mode
  input_host: string
  input_port: number
  output_host: string
  output_port: number
  // RTSP mode
  rtsp_user: string
  rtsp_password: string
  rtsp_ip: string
  rtsp_port: number
  rtsp_channel: string
  rtsp_low_latency: boolean
  rtsp_interval: number
  // Video mode
  video_path: string
  video_loop: boolean
  // Detection
  conf_threshold: number
  gate_trigger_mode: string
  gate_area_threshold: number
  gate_line: number[]
  gate_line_side: number[]
  strict_output: boolean
  state_changes_only: boolean
  // Misc
  auto_start: boolean
  // Recording
  record_stream: boolean
  record_dir: string
  // Dataset capture
  dataset_capture: boolean
  dataset_interval: number
  dataset_dir: string
  // TCP push
  tcp_push_enabled: boolean
  tcp_push_host: string
  tcp_push_port: number
  tcp_push_certfile: string
  tcp_push_keyfile: string
  tcp_push_ca_certs: string
  kind: 'detection' | 'counter'
  // Image enhancement
  enhance_gamma: number
  enhance_clahe: boolean
  enhance_clahe_clip: number
  // Multi-car ranked output
  result_car_count: number
  // UDP input port
  udp_port: number
  // Rolling frame cache for backtracking (udp_packet mode only)
  cache_enabled: boolean
  cache_max_seconds: number
  cache_max_frames: number
  cache_max_bytes: number
  cache_token?: string  // server-generated, read-only
  // Direction detection tuning
  dir_buf_size: number
  dir_min_frames: number
  dir_miss_tolerance: number
  dir_idle_hold: number
  dir_signal_threshold: number
}

export interface ServiceStatus {
  name: string
  state: string
  running: boolean
  error: string
  is_recording: boolean
  is_previewing: boolean
  is_direction_debugging: boolean
  is_dataset_capturing: boolean
  tcp_push_running: boolean
  last_payload: {
    car?: { detected: boolean; direction: string; confidence: number }
    car_rear?: { detected: boolean; direction: string; confidence: number }
    gate?: { open: boolean }
  }
}

export interface RankedCar {
  rank: number
  detected: boolean
  direction: string
  confidence: number
  area: number
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
  cars?: RankedCar[]
  cars_rear?: RankedCar[]
}

export interface CountingConfig {
  name: string
  source_service: string
  auto_start: boolean
  initial_count: number
  output_host: string
  output_port: number
  tcp_push_enabled: boolean
  tcp_push_host: string
  tcp_push_port: number
  tcp_push_certfile: string
  tcp_push_keyfile: string
  tcp_push_ca_certs: string
  // runtime fields returned by the API
  state?: string
  count?: number
  last_reset?: string
  tcp_push_running?: boolean
}

export interface CountingStatus {
  name: string
  source_service: string
  state: string
  running: boolean
  tcp_push_running: boolean
  count: number
  last_reset: string
}

export interface CountingResult {
  service_name: string
  source_service: string
  timestamp: string
  event: 'car_passed' | 'status' | 'reset'
  trigger_class: string
  direction: string
  change: number
  count: number
  last_reset: string
}

export interface JobStatus {
  job_id: string
  status: 'running' | 'done' | 'failed'
  result: Record<string, unknown> | null
  error: string | null
  progress?: number
  total?: number
}

export interface Token {
  token: string
  label: string
  created_at: string
  services: string[]
  permissions: string[]
}
