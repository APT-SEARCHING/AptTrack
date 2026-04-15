import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts';
import api, { Listing, PlanResponse } from '../services/api';
import { useAuth } from '../context/AuthContext';
import AlertModal from '../components/AlertModal';
import AuthModal from '../components/AuthModal';

const StatPill: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="bg-slate-50 rounded-xl px-4 py-3 text-center">
    <p className="text-xs text-slate-400 uppercase tracking-wider mb-0.5">{label}</p>
    <p className="font-bold text-slate-900">{value}</p>
  </div>
);

const ListingDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [listing, setListing] = useState<Listing | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAlert, setShowAlert] = useState(false);
  const [showAuth, setShowAuth] = useState(false);
  const { token } = useAuth();

  useEffect(() => {
    setLoading(true);
    api.getListing(Number(id))
      .then(setListing)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[60vh]">
        <div className="w-10 h-10 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  if (!listing) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center text-slate-500">
        <p className="text-4xl mb-4">🏚</p>
        <p className="text-xl font-semibold mb-2">Listing not found</p>
        <Link to="/" className="text-indigo-600 hover:underline text-sm">← Back to listings</Link>
      </div>
    );
  }

  const apt = listing._raw;
  const allPlans: PlanResponse[] = (apt?.plans ?? []).sort((a, b) => a.price - b.price);
  const chartData = listing.price_history.map(h => ({
    date: new Date(h.recorded_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    price: h.price,
  }));

  const prices = allPlans.map(p => p.price).filter(Boolean);
  const minP = prices.length ? Math.min(...prices) : 0;
  const maxP = prices.length ? Math.max(...prices) : 0;
  const availCount = allPlans.filter(p => p.is_available).length;

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      {/* Back */}
      <Link to="/" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-indigo-600 mb-6 transition-colors">
        ← All listings
      </Link>

      {/* Header card */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6 mb-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-slate-900 mb-1">{listing.title}</h1>
            <p className="text-slate-500 flex items-center gap-1">
              <span>📍</span> {listing.location}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2 shrink-0">
            <div className="text-right">
              <span className="text-3xl font-bold text-indigo-600">
                ${minP.toLocaleString()}
              </span>
              {maxP > minP && (
                <span className="text-slate-400 text-sm"> – ${maxP.toLocaleString()}</span>
              )}
              <span className="text-slate-400 text-sm">/mo</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => token ? setShowAlert(true) : setShowAuth(true)}
                className="flex items-center gap-1.5 text-sm bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-4 py-2 rounded-xl transition-colors"
              >
                <span>🔔</span> Set Alert
              </button>
              {apt?.source_url && (
                <a
                  href={apt.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-indigo-600 hover:text-indigo-800 border border-indigo-200 hover:border-indigo-400 rounded-lg px-3 py-2 transition-colors"
                >
                  View listing ↗
                </a>
              )}
            </div>
          </div>
        </div>

        {/* Quick stats */}
        <div className="grid grid-cols-3 gap-3 mt-6">
          <StatPill label="Floor plans" value={String(allPlans.length)} />
          <StatPill label="Available now" value={`${availCount} / ${allPlans.length}`} />
          <StatPill label="From" value={`$${minP.toLocaleString()}`} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Plans table */}
        <div className="lg:col-span-3 bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100">
            <h2 className="font-semibold text-slate-900">Floor Plans</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500 uppercase tracking-wider">
                <tr>
                  <th className="text-left px-4 py-3">Plan</th>
                  <th className="text-left px-4 py-3">Beds</th>
                  <th className="text-left px-4 py-3">Baths</th>
                  <th className="text-left px-4 py-3">Sqft</th>
                  <th className="text-right px-4 py-3">Price</th>
                  <th className="text-center px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {allPlans.map(plan => (
                  <tr key={plan.id} className={`hover:bg-slate-50 transition-colors ${plan.name === listing.plan_name ? 'bg-indigo-50' : ''}`}>
                    <td className="px-4 py-3 font-mono font-semibold text-slate-700">
                      {plan.name}
                      {plan.name === listing.plan_name && (
                        <span className="ml-2 text-xs text-indigo-500 font-sans">selected</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {plan.bedrooms === 0 ? 'Studio' : plan.bedrooms}
                    </td>
                    <td className="px-4 py-3 text-slate-600">{plan.bathrooms}</td>
                    <td className="px-4 py-3 text-slate-600">
                      {plan.area_sqft ? plan.area_sqft.toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3 text-right font-semibold text-slate-900">
                      ${plan.price.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`badge ${plan.is_available ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-400'}`}>
                        {plan.is_available ? 'Available' : 'Unavailable'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Price history chart */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-100 shadow-sm p-6">
          <h2 className="font-semibold text-slate-900 mb-1">Price History</h2>
          <p className="text-xs text-slate-400 mb-4">Plan {listing.plan_name}</p>
          {chartData.length > 1 ? (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#94a3b8' }} tickLine={false} />
                <YAxis
                  tickFormatter={(v: number) => `$${(v / 1000).toFixed(1)}k`}
                  tick={{ fontSize: 11, fill: '#94a3b8' }}
                  tickLine={false}
                  axisLine={false}
                  width={52}
                />
                <Tooltip
                  formatter={(v: number) => [`$${v.toLocaleString()}`, 'Rent']}
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: 12 }}
                />
                <ReferenceLine
                  y={chartData[chartData.length - 1]?.price}
                  stroke="#6366f1"
                  strokeDasharray="4 4"
                  strokeOpacity={0.4}
                />
                <Line
                  type="monotone"
                  dataKey="price"
                  stroke="#6366f1"
                  strokeWidth={2.5}
                  dot={{ fill: '#6366f1', r: 3 }}
                  activeDot={{ r: 5 }}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-40 flex items-center justify-center text-slate-300 text-sm">
              Not enough history yet
            </div>
          )}
        </div>
      </div>

      {showAlert && apt && (
        <AlertModal
          apartmentId={apt.id}
          apartmentTitle={listing.title}
          currentPrice={minP}
          onClose={() => setShowAlert(false)}
          onCreated={() => setShowAlert(false)}
        />
      )}
      {showAuth && (
        <AuthModal onClose={() => setShowAuth(false)} />
      )}
    </div>
  );
};

export default ListingDetailPage;
