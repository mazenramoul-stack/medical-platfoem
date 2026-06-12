import { Link } from 'react-router-dom';

import { Skeleton } from '../../components/UI/Skeleton.jsx';

const TONES = {
  blue:   'bg-blue-50 text-primary',
  purple: 'bg-purple-50 text-purple-700',
  red:    'bg-red-50 text-danger',
  green:  'bg-green-50 text-success',
};

export default function StatsCard({ label, value, icon: Icon, to, tone = 'blue', loading = false }) {
  const inner = (
    <div className="bg-card rounded-xl shadow-sm border border-gray-200 p-5 flex items-center gap-4 hover:border-primary transition">
      <div className={`w-11 h-11 rounded-lg flex items-center justify-center ${TONES[tone] || TONES.blue}`}>
        {Icon && <Icon size={22} />}
      </div>
      <div className="min-w-0">
        {loading ? (
          <Skeleton className="w-12 h-6" />
        ) : (
          <div className="text-2xl font-semibold text-gray-900 leading-tight">{value ?? '—'}</div>
        )}
        <div className="text-xs text-gray-500 mt-0.5 truncate">{label}</div>
      </div>
    </div>
  );
  return to ? <Link to={to}>{inner}</Link> : inner;
}
