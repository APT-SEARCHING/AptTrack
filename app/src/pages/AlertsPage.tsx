import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import api, { SubscriptionResponse } from '../services/api';
import { useAuth } from '../context/AuthContext';

const AlertsPage: React.FC = () => {
  const { token, user } = useAuth();
  const [subs, setSubs] = useState<SubscriptionResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // transient per-row feedback: subId → 'paused' | 'resumed' | 'error'
  const [feedback, setFeedback] = useState<Record<number, string>>({});
  const feedbackTimers = useRef<Record<number, ReturnType<typeof setTimeout>>>({});

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

  const togglePause = async (sub: SubscriptionResponse) => {
    if (!token) return;
    const nextActive = !sub.is_active;

    // Optimistic update
    setSubs(prev => prev.map(s => s.id === sub.id ? { ...s, is_active: nextActive } : s));

    try {
      await api.updateSubscription(token, sub.id, { is_active: nextActive });
      showFeedback(sub.id, nextActive ? 'resumed' : 'paused');
    } catch {
      // Rollback
      setSubs(prev => prev.map(s => s.id === sub.id ? { ...s, is_active: sub.is_active } : s));
      showFeedback(sub.id, 'error');
    }
  };

  const showFeedback = (id: number, kind: string) => {
    clearTimeout(feedbackTimers.current[id]);
    setFeedback(prev => ({ ...prev, [id]: kind }));
    feedbackTimers.current[id] = setTimeout(() => {
      setFeedback(prev => { const next = { ...prev }; delete next[id]; return next; });
    }, 1500);
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
          {subs.map(sub => {
            const title = sub.apartment_title ?? (sub.apartment_id ? `Apartment #${sub.apartment_id}` : sub.city ?? 'Alert');
            const location = sub.apartment_city ?? sub.city;
            const baselineDate = sub.baseline_recorded_at
              ? new Date(sub.baseline_recorded_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
              : null;
            const fb = feedback[sub.id];

            // Pause/Resume button label: transient feedback overrides the default
            const pauseLabel = fb === 'paused' ? 'Paused ✓'
              : fb === 'resumed' ? 'Resumed ✓'
              : fb === 'error' ? 'Error'
              : sub.is_active ? 'Pause' : 'Resume';

            const pauseColors = fb === 'error'
              ? 'text-red-500 border-red-300'
              : fb
              ? 'text-emerald-600 border-emerald-300'
              : sub.is_active
              ? 'text-slate-400 hover:text-amber-600 border-slate-200 hover:border-amber-300'
              : 'text-indigo-500 hover:text-indigo-700 border-indigo-200 hover:border-indigo-400';

            return (
              <div key={sub.id} className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
                {/* Header row */}
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      {sub.apartment_id ? (
                        <Link
                          to={`/listings/${sub.apartment_id}`}
                          className="font-semibold text-slate-900 hover:text-indigo-600 transition-colors"
                        >
                          {title}
                        </Link>
                      ) : (
                        <span className="font-semibold text-slate-900">{title}</span>
                      )}
                      {location && (
                        <span className="text-xs text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
                          {location}
                        </span>
                      )}
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${sub.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                        {sub.is_active ? 'Active' : 'Paused'}
                      </span>
                    </div>
                    {/* Plan name + spec */}
                    {(sub.plan_name || sub.plan_spec) && (
                      <p className="text-sm text-slate-500 mt-0.5">
                        {sub.plan_name}
                        {sub.plan_spec && <span className="text-slate-400"> · {sub.plan_spec}</span>}
                      </p>
                    )}
                  </div>

                  {/* Action buttons */}
                  <div className="shrink-0 flex items-center gap-2">
                    <button
                      onClick={() => togglePause(sub)}
                      className={`text-xs border rounded-lg px-3 py-1.5 transition-colors ${pauseColors}`}
                    >
                      {pauseLabel}
                    </button>
                    <button
                      onClick={() => remove(sub.id)}
                      className="text-xs text-slate-400 hover:text-red-500 border border-slate-200 hover:border-red-300 rounded-lg px-3 py-1.5 transition-colors"
                    >
                      Remove
                    </button>
                  </div>
                </div>

                {/* Price row */}
                {(sub.latest_price != null || sub.baseline_price != null) && (
                  <div className="flex items-baseline gap-4 mb-2">
                    {sub.latest_price != null && (
                      <span className="text-lg font-semibold text-slate-800">
                        ${sub.latest_price.toLocaleString()}<span className="text-sm font-normal text-slate-400">/mo</span>
                      </span>
                    )}
                    {sub.baseline_price != null && (
                      <span className="text-sm text-slate-400">
                        was ${sub.baseline_price.toLocaleString()}{baselineDate && ` (${baselineDate})`}
                      </span>
                    )}
                  </div>
                )}

                {/* Alert condition */}
                <p className="text-sm text-slate-500">
                  {sub.target_price != null && sub.price_drop_pct != null
                    ? `Alert below $${sub.target_price.toLocaleString()}/mo or on ${sub.price_drop_pct}% drop`
                    : sub.target_price != null
                    ? `Alert when below $${sub.target_price.toLocaleString()}/mo`
                    : sub.price_drop_pct != null
                    ? `Alert on ${sub.price_drop_pct}% drop from baseline`
                    : null}
                </p>

                {/* Footer meta */}
                <p className="text-xs text-slate-400 mt-1.5">
                  Created {new Date(sub.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                  {sub.last_notified_at && ` · Notified ${new Date(sub.last_notified_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`}
                  {sub.trigger_count > 0 && ` · Fired ${sub.trigger_count}×`}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default AlertsPage;
