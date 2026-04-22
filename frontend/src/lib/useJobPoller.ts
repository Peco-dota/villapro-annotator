import { useState, useEffect, useRef } from 'react'
import { getJob } from './api'
import type { JobStatus } from './types'

export function useJobPoller(jobId: string | null, intervalMs = 1000) {
  const [job, setJob] = useState<JobStatus | null>(null)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!jobId) { setJob(null); return }

    const poll = async () => {
      try {
        const data = await getJob(jobId)
        setJob(data)
        if (data.status !== 'running') {
          if (timer.current) clearInterval(timer.current)
        }
      } catch {
        // ignore transient errors
      }
    }

    poll()
    timer.current = setInterval(poll, intervalMs)
    return () => { if (timer.current) clearInterval(timer.current) }
  }, [jobId, intervalMs])

  return job
}
