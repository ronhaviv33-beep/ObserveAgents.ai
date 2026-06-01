export function RequestsTable({ records }) {
  if (records.length === 0) return null

  return (
    <div className="bg-[#1a1d27] rounded-xl border border-white/5 overflow-hidden">
      <div className="px-5 py-4 border-b border-white/5">
        <h2 className="text-sm font-medium text-slate-300">Recent Requests</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-slate-500 uppercase tracking-wider border-b border-white/5">
              {['Time','Team','Agent','Model','Tokens','Latency','Cost','Response'].map(h => (
                <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {records.map((r) => (
              <tr key={r.id} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                  {new Date(r.timestamp).toLocaleString()}
                </td>
                <td className="px-4 py-3">
                  <span className="px-2 py-0.5 bg-indigo-500/10 text-indigo-300 rounded text-xs">{r.team}</span>
                </td>
                <td className="px-4 py-3 text-slate-300">{r.agent}</td>
                <td className="px-4 py-3">
                  <span className="px-2 py-0.5 bg-cyan-500/10 text-cyan-300 rounded text-xs">{r.model}</span>
                </td>
                <td className="px-4 py-3 text-slate-300">{r.total_tokens.toLocaleString()}</td>
                <td className="px-4 py-3 text-slate-300">{r.latency_ms.toFixed(0)}ms</td>
                <td className="px-4 py-3 text-green-400">${r.cost_usd.toFixed(6)}</td>
                <td className="px-4 py-3 text-slate-400 max-w-xs truncate" title={r.response}>
                  {r.response}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
