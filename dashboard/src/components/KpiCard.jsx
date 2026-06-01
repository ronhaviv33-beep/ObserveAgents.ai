export function KpiCard({ icon: Icon, label, value, sub, color = 'indigo' }) {
  const colors = {
    indigo: 'text-indigo-400 bg-indigo-400/10',
    green:  'text-green-400  bg-green-400/10',
    yellow: 'text-yellow-400 bg-yellow-400/10',
    blue:   'text-blue-400   bg-blue-400/10',
  }
  return (
    <div className="bg-[#1a1d27] rounded-xl p-5 flex items-center gap-4 border border-white/5">
      <div className={`p-3 rounded-lg ${colors[color]}`}>
        <Icon size={22} />
      </div>
      <div>
        <p className="text-xs text-slate-400 uppercase tracking-wider">{label}</p>
        <p className="text-2xl font-semibold text-white leading-tight">{value}</p>
        {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}
