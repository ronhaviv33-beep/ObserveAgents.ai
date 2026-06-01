import { DollarSign, Zap, Clock, Activity, RefreshCw } from 'lucide-react'
import { useData } from './hooks/useData'
import { KpiCard } from './components/KpiCard'
import { CostChart } from './components/CostChart'
import { TokenChart } from './components/TokenChart'
import { RequestsTable } from './components/RequestsTable'

export default function App() {
  const { summary, records, loading, error, refresh, lastRefresh } = useData(30_000)

  if (loading) return (
    <div className="flex items-center justify-center min-h-screen text-slate-400">
      Loading telemetry...
    </div>
  )

  if (error) return (
    <div className="flex items-center justify-center min-h-screen text-red-400">
      Error: {error} — is the backend running on port 8000?
    </div>
  )

  return (
    <div className="min-h-screen bg-[#0f1117] p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">AIFinOps Guard</h1>
          <p className="text-sm text-slate-400 mt-0.5">AI Runtime Intelligence Platform</p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-xs text-slate-500">
              Updated {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={refresh}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 text-sm transition-colors"
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KpiCard
          icon={DollarSign}
          label="Total Cost"
          value={`$${summary.total_cost_usd.toFixed(4)}`}
          sub={`${summary.total_requests} requests`}
          color="green"
        />
        <KpiCard
          icon={Zap}
          label="Total Tokens"
          value={summary.total_tokens.toLocaleString()}
          sub="across all models"
          color="yellow"
        />
        <KpiCard
          icon={Clock}
          label="Avg Latency"
          value={`${summary.avg_latency_ms.toFixed(0)}ms`}
          sub="per request"
          color="blue"
        />
        <KpiCard
          icon={Activity}
          label="Models Used"
          value={summary.models_used.length}
          sub={summary.models_used.join(', ') || '—'}
          color="indigo"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <CostChart records={records} />
        <TokenChart records={records} />
      </div>

      {/* Table */}
      <RequestsTable records={records} />
    </div>
  )
}
