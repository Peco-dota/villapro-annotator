import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getServices } from '../lib/api'
import type { ServiceConfig } from '../lib/types'
import { ServiceCard } from '../components/detection/ServiceCard'
import { ServiceForm } from '../components/detection/ServiceForm'
import { LiveDashboard } from '../components/detection/LiveDashboard'
import { Button } from '../components/ui/Button'
import { Spinner } from '../components/ui/Spinner'

export function DetectionPage() {
  const nav = useNavigate()
  const [formOpen, setFormOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<ServiceConfig | undefined>()
  const [dashService, setDashService] = useState<ServiceConfig | null>(null)

  const { data: services = [], isLoading } = useQuery<ServiceConfig[]>({
    queryKey: ['services'],
    queryFn: getServices,
    refetchInterval: 5000,
  })

  const openCreate = () => { setEditTarget(undefined); setFormOpen(true) }
  const openEdit = (s: ServiceConfig) => { setEditTarget(s); setFormOpen(true) }

  return (
    <div className="min-h-screen bg-[#0f0d14] p-6">
      <ServiceForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        existing={editTarget}
      />

      <header className="flex items-center justify-between mb-8 max-w-4xl mx-auto">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => nav('/')}>← Back</Button>
          <h1 className="text-xl font-semibold text-slate-100">Detection Services</h1>
        </div>
        <Button variant="primary" onClick={openCreate}>+ New Service</Button>
      </header>

      <main className="max-w-4xl mx-auto flex flex-col gap-4">
        {isLoading ? (
          <div className="flex justify-center py-12"><Spinner size={28} /></div>
        ) : services.length === 0 ? (
          <div className="flex flex-col items-center py-20 text-center gap-2">
            <p className="text-slate-400 text-sm">No detection services yet</p>
            <Button variant="primary" onClick={openCreate}>Create your first service</Button>
          </div>
        ) : (
          services.map(s => (
            <div key={s.name}>
              <ServiceCard
                service={s}
                onEdit={() => openEdit(s)}
              />
              <button
                onClick={() => setDashService(dashService?.name === s.name ? null : s)}
                className="text-xs text-violet-500 hover:text-violet-400 mt-1 ml-4 cursor-pointer"
              >
                {dashService?.name === s.name ? 'Hide live stream ▲' : 'Show live stream ▼'}
              </button>
              {dashService?.name === s.name && (
                <div className="mt-2">
                  <LiveDashboard service={s} />
                </div>
              )}
            </div>
          ))
        )}
      </main>
    </div>
  )
}
