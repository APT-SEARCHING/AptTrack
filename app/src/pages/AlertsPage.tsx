import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api, { SubscriptionResponse } from '../services/api';
import { useAuth } from '../context/AuthContext';

const AlertsPage: React.FC = () => {
  const { token, user } = useAuth();
  const [subs, setSubs] = useState<SubscriptionResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    if (!token) return;
    setLoading(true);
    api.getSubscriptions(token)
      .then(setSubs)
      .catch(err => setError(String(err)))
      .finally(() => setLoading(false));
  };

  useEffect(load, [token]);

  const remove = async (id: number) => {
    if (!token) return;
    await api.deleteSubscription(token, id);
    setSubs(prev => prev.filter(s => s.id !== id));
  };

  if (!token) {
    return (
      <div className="max-w-xl mx-auto px-4 py-24 text-center">
        <p className="text-5xl mb-4">🔔</p>
        <p className="text-xl font-semibold text-slate-800 mb-2">Sign in to see your alerts</p>
        <p className="text-slate-500 text-sm">Create price alerts on any apartment listing.</p>
        <Link to="/" className="inline-block mt-6 text-indigo-600 hover:underline text-sm">← Back to listings</Link>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-8">
      <Link to="/" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-indigo-600 mb-6 transition-colors">
        ← All listings
      </Link>

      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">My Alerts</h1>
          <p className="text-slate-500 text-sm mt-1">{user?.email}</p>
        </div>
        <span className="text-sm text-slate-400">{subs.filter(s => s.is_active).length} active</span>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="bg-white rounded-2xl border border-slate-100 p-5 animate-pulse">
              <div className="h-4 bg-slate-100 rounded w-1/2 mb-2" />
              <div className="h-3 bg-slate-100 rounded w-1/3" />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">{error}</div>
      ) : subs.length === 0 ? (
        <div className="text-center py-20 text-slate-400">
          <p className="text-5xl mb-4">🔕</p>
          <p className="text-lg font-medium text-slate-600">No alerts yet</p>
          <p className="text-sm mt-1">Go to an apartment listing and click "Set Alert".</p>
          <Link to="/" className="inline-block mt-4 text-indigo-600 hover:underline text-sm">Browse listings →</Link>
        </div>
      ) : (
        <div className="space-y-3">
          {subs.map(sub => (
            <div key={sub.id} className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  {sub.apartment_id && (
                    <Link
                      to={`/listings/${sub.apartment_id}`}
                      className="font-semibold text-slate-900 hover:text-indigo-600 transition-colors text-sm"
                    >
                      Apartment #{sub.apartment_id}
                    </Link>
                  )}
                  {sub.city && (
                    <span className="text-sm text-slate-700 font-semibold">{sub.city}</span>
                  )}
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${sub.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                    {sub.is_active ? 'Active' : 'Paused'}
                  </span>
                </div>
                <p className="text-sm text-slate-500">
                  {sub.target_price && `Notify when price below $${sub.target_price.toLocaleString()}/mo`}
                  {sub.price_drop_pct && `Notify on ${sub.price_drop_pct}% price drop`}
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  Created {new Date(sub.created_at).toLocaleDateString()}
                  {sub.last_notified_at && ` · Last notified ${new Date(sub.last_notified_at).toLocaleDateString()}`}
                </p>
              </div>
              <button
                onClick={() => remove(sub.id)}
                className="shrink-0 text-xs text-slate-400 hover:text-red-500 border border-slate-200 hover:border-red-300 rounded-lg px-3 py-1.5 transition-colors"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default AlertsPage;
