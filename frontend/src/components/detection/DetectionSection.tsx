import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getServices, duplicateService, getCounters } from '../../lib/api'
import type { ServiceConfig, CountingConfig } from '../../lib/types'
import { ServiceCard } from './ServiceCard'
import { ServiceForm } from './ServiceForm'
import { ReceiverDashboard } from './ReceiverDashboard'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { Input } from '../ui/Input'
import { Spinner } from '../ui/Spinner'

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

export function DetectionSection() {
  const [formOpen, setFormOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<ServiceConfig | undefined>()
  const [dupTarget, setDupTarget] = useState<ServiceConfig | null>(null)
  const [activeTab, setActiveTab] = useState<'services' | 'receiver'>('services')

  const { data: services = [], isLoading } = useQuery<ServiceConfig[]>({
    queryKey: ['services'],
    queryFn: getServices,
    refetchInterval: 2000,
  })

  const { data: allCounters = [] } = useQuery<CountingConfig[]>({
    queryKey: ['counters'],
    queryFn: getCounters,
    refetchInterval: 5000,
  })

  const openCreate = () => { setEditTarget(undefined); setFormOpen(true) }
  const openEdit = (s: ServiceConfig) => { setEditTarget(s); setFormOpen(true) }

  return (
    <div className="flex flex-col h-full">
      <ServiceForm open={formOpen} onClose={() => setFormOpen(false)} existing={editTarget} />
      {dupTarget && <DuplicateModal service={dupTarget} onClose={() => setDupTarget(null)} />}

      {/* Sub-header */}
      <div className="flex items-center justify-between mb-4">
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
        <div className="flex items-center gap-2">
          {activeTab === 'receiver' && (
            <button
              onClick={() => window.open('/receiver', '_blank')}
              title="Open receiver in a new browser tab"
              className="text-xs text-slate-500 hover:text-violet-400 cursor-pointer flex items-center gap-1 transition-colors"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                <polyline points="15 3 21 3 21 9"/>
                <line x1="10" y1="14" x2="21" y2="3"/>
              </svg>
              Open in new tab
            </button>
          )}
          {activeTab === 'services' && (
            <Button variant="primary" size="sm" onClick={openCreate}>+ Add Service</Button>
          )}
        </div>
      </div>

      {/* Services list */}
      {activeTab === 'services' && (
        <div className="flex flex-col gap-3">
          <p className="text-xs text-slate-600">
            Each service runs YOLO detection and pushes JSON results to the configured output.
            Input can be HTTP, RTSP camera, or a local video file. Services marked ⟳ auto-start with the server.
          </p>

          {isLoading ? (
            <div className="flex justify-center py-12"><Spinner size={24} /></div>
          ) : services.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-xl">⚡</div>
              <p className="text-slate-400 text-sm">No detection services configured yet.</p>
              <Button variant="primary" size="sm" onClick={openCreate}>+ Add Service</Button>
            </div>
          ) : (
            services.map(s => (
              <ServiceCard
                key={s.name}
                service={s}
                hasCounter={allCounters.some(c => c.name === `${s.name}_counter`)}
                onEdit={() => openEdit(s)}
                onDuplicate={() => setDupTarget(s)}
              />
            ))
          )}
        </div>
      )}

      {/* Receiver */}
      {activeTab === 'receiver' && <ReceiverDashboard />}
    </div>
  )
}
