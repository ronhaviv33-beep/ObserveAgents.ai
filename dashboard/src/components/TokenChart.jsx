import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'

function buildModelData(records) {
  const byModel = {}
  for (const r of records) {
    if (!byModel[r.model]) byModel[r.model] = { model: r.model, prompt: 0, completion: 0 }
    byModel[r.model].prompt     += r.prompt_tokens
    byModel[r.model].completion += r.completion_tokens
  }
  return Object.values(byModel)
}

export function TokenChart({ records }) {
  const data = buildModelData(records)
  if (data.length === 0) return null

  return (
    <div className="bg-[#1a1d27] rounded-xl p-5 border border-white/5">
      <h2 className="text-sm font-medium text-slate-300 mb-4">Token Usage by Model</h2>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#ffffff0a" />
          <XAxis dataKey="model" tick={{ fill: '#64748b', fontSize: 11 }} />
          <YAxis tick={{ fill: '#64748b', fontSize: 11 }} width={60} />
          <Tooltip
            contentStyle={{ background: '#0f1117', border: '1px solid #ffffff15', borderRadius: 8 }}
          />
          <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
          <Bar dataKey="prompt"     name="Prompt tokens"     fill="#6366f1" radius={[4,4,0,0]} />
          <Bar dataKey="completion" name="Completion tokens" fill="#22d3ee" radius={[4,4,0,0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
