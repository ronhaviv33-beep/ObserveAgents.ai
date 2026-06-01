import { useState, useEffect, useCallback } from 'react'
import { fetchSummary, fetchTelemetry } from '../api'

export function useData(refreshInterval = 30_000) {
  const [summary, setSummary] = useState(null)
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastRefresh, setLastRefresh] = useState(null)

  const load = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([fetchSummary(), fetchTelemetry()])
      setSummary(s)
      setRecords(r)
      setError(null)
      setLastRefresh(new Date())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, refreshInterval)
    return () => clearInterval(id)
  }, [load, refreshInterval])

  return { summary, records, loading, error, refresh: load, lastRefresh }
}
