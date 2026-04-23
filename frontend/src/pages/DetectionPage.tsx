import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getServices, duplicateService } from '../lib/api'
import type { ServiceConfig } from '../lib/types'
import { ServiceCard } from '../components/detection/ServiceCard'
import { ServiceForm } from '../components/detection/ServiceForm'
import { PreviewWindow } from '../components/detection/PreviewWindow'
import { ReceiverDashboard } from '../components/detection/ReceiverDashboard'
import { Button } from '../components/ui/Button'
import { Modal } from '../components/ui/Modal'
import { Input } from '../components/ui/Input'
import { Spinner } from '../components/ui/Spinner'

function DuplicateModal({ service, onClose }: { service: ServiceConfig; onClose: () => void }) {
  const qc = useQueryClient()
  const [name, setName] = useState(`${service.name}-copy`)
  const [err, setErr] = useState('')
  const mut = useMutation({
    mutationFn: () => duplicateService(service.name, name.trim()),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['services'] }); onClose() },
    onError: (e: unknown) => setErr((e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Failed.'),
  })
  return (
    <Modal open onClose={onClose} title={`Duplicate: ${service.name}`} width="max-w-sm">
      <div className="flex flex-col gap-3">
        <Input label="New service name" value={name} onChange={e => setName(e.target.value)} autoFocus
          onKeyDown={e => { if (e.key === 'Enter' && name.trim()) mut.mutate() }} />
        {err && <p className="text-xs text-red-400">{err}</p>}
        <div className="flex gap-2 justify-end">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={() => mut.mutate()} disabled={mut.isPending || !name.trim()}>
            {mut.isPending ? <Spinner size={12} /> : null} Duplicate
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export function DetectionPage() {
  const nav = useNavigate()
  const [formOpen, setFormOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<ServiceConfig | undefined>()
  const [dupTarget, setDupTarget] = useState<ServiceConfig | null>(null)
  const [previewService, setPreviewService] = useState<ServiceConfig | null>(null)
  const [activeTab, setActiveTab] = useState<'services' | 'receiver'>('services')

  const { data: services = [], isLoading } = useQuery<ServiceConfig[]>({
    queryKey: ['services'],
    queryFn: getServices,
    refetchInterval: 2000,
  })

  const openCreate = () => { setEditTarget(undefined); setFormOpen(true) }
  const openEdit = (s: ServiceConfig) => { setEditTarget(s); setFormOpen(true) }

  return (
    <div className="min-h-screen bg-[#0f172a] flex flex-col">
      <ServiceForm open={formOpen} onClose={() => setFormOpen(false)} existing={editTarget} />
      {dupTarget && <DuplicateModal service={dupTarget} onClose={() => setDupTarget(null)} />}
      {previewService && (
        <PreviewWindow service={previewService} onClose={() => setPreviewService(null)} />
      )}

      {/* Top bar */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-[#1e293b] shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={() => nav('/')} className="text-slate-500 hover:text-slate-300 text-sm cursor-pointer">← Back</button>
          <div className="w-px h-4 bg-slate-700" />
          <span className="text-sm font-semibold text-slate-100">⚡ Service Manager</span>
        </div>
        <div className="flex items-center gap-2">
          {/* Tab switcher */}
          <div className="flex rounded-lg border border-[#1e293b] overflow-hidden">
            {(['services', 'receiver'] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-1.5 text-xs font-medium cursor-pointer transition-colors
                  ${activeTab === tab ? 'bg-violet-700 text-white' : 'text-slate-400 hover:text-slate-200'}`}
              >
                {tab === 'services' ? '⚙ Services' : '📡 Receiver'}
              </button>
            ))}
          </div>
          {activeTab === 'services' && (
            <Button variant="primary" size="sm" onClick={openCreate}>+ Add Service</Button>
          )}
        </div>
      </header>

      <main className="flex-1 overflow-y-auto">
        {activeTab === 'services' && (
          <div className="max-w-5xl mx-auto px-6 py-6 flex flex-col gap-3">
            {/* Description */}
            <p className="text-xs text-slate-600 mb-1">
              Each service runs YOLO detection and pushes JSON results to the configured output.
              Input can be an HTTP endpoint, a live RTSP camera stream, or a looping local video file.
              Services marked ⟳ auto-start when VisionQ opens.
            </p>

            {isLoading ? (
              <div className="flex justify-center py-20"><Spinner size={28} /></div>
            ) : services.length === 0 ? (
              <div className="flex flex-col items-center py-20 text-center gap-3">
                <div className="w-14 h-14 rounded-2xl bg-slate-800 border border-slate-700 flex items-center justify-center text-2xl">⚡</div>
                <p className="text-slate-400 text-sm">No detection services configured yet.</p>
                <Button variant="primary" onClick={openCreate}>+ Add Service</Button>
              </div>
            ) : (
              services.map(s => (
                <ServiceCard
                  key={s.name}
                  service={s}
                  onEdit={() => openEdit(s)}
                  onDuplicate={() => setDupTarget(s)}
                  onPreview={() => setPreviewService(s)}
                />
              ))
            )}
          </div>
        )}

        {activeTab === 'receiver' && (
          <ReceiverDashboard />
        )}
      </main>
    </div>
  )
}
