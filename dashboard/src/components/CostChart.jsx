import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'

function buildTimeSeries(records) {
  const byHour = {}
  for (const r of records) {
    const key = r.timestamp.slice(0, 13) // "2024-01-15T14"
    byHour[key] = (byHour[key] || 0) + r.cost_usd
  }
  return Object.entries(byHour)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, cost]) => ({
      time: key.slice(5).replace('T', ' ') + 'h',
      cost: +cost.toFixed(6),
    }))
}

export function CostChart({ records }) {
  const data = buildTimeSeries(records)
  if (data.length === 0) return <Empty />

  return (
    <div className="bg-[#1a1d27] rounded-xl p-5 border border-white/5">
      <h2 className="text-sm font-medium text-slate-300 mb-4">Cost Over Time (USD)</h2>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="costGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#6366f1" stopOpacity={0}   />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#ffffff0a" />
          <XAxis dataKey="time" tick={{ fill: '#64748b', fontSize: 11 }} />
          <YAxis tick={{ fill: '#64748b', fontSize: 11 }} width={60} tickFormatter={v => `$${v}`} />
          <Tooltip
            contentStyle={{ background: '#0f1117', border: '1px solid #ffffff15', borderRadius: 8 }}
            formatter={v => [`$${v}`, 'Cost']}
          />
          <Area type="monotone" dataKey="cost" stroke="#6366f1" fill="url(#costGrad)" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

function Empty() {
  return (
    <div className="bg-[#1a1d27] rounded-xl p-5 border border-white/5 flex items-center justify-center h-48 text-slate-500 text-sm">
      No data yet — send a request via <code className="mx-1 px-1 bg-white/5 rounded">/ask</code> to populate
    </div>
  )
}
