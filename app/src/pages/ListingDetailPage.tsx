import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts';
import api, { Listing, PlanResponse, SimilarApartment, SimilarResponse } from '../services/api';
import { useAuth } from '../context/AuthContext';
import AlertModal from '../components/AlertModal';
import AuthModal from '../components/AuthModal';

const StatPill: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="bg-slate-50 rounded-xl px-4 py-3 text-center">
    <p className="text-xs text-slate-400 uppercase tracking-wider mb-0.5">{label}</p>
    <p className="font-bold text-slate-900">{value}</p>
  </div>
);

const MarketPill: React.FC<{ pct: number; city: string }> = ({ pct, city }) => {
  const absPct = Math.abs(pct);
  const label =
    absPct < 0.05
      ? `Near ${city} median`
      : pct < 0
      ? `${Math.round(absPct * 100)}% below ${city} median`
      : `${Math.round(absPct * 100)}% above ${city} median`;
  const colors =
    absPct < 0.05
      ? 'bg-slate-100 text-slate-500'
      : pct < 0
      ? 'bg-emerald-100 text-emerald-700'
      : 'bg-amber-100 text-amber-700';
  return (
    <span className={`inline-block text-xs font-medium px-2.5 py-1 rounded-full ${colors}`}>
      {label}
    </span>
  );
};

const SimilarCard: React.FC<{ apt: SimilarApartment }> = ({ apt }) => {
  const bedLabel =
    apt.min_beds === apt.max_beds
      ? apt.min_beds === 0 ? 'Studio' : `${apt.min_beds} bd`
      : apt.min_beds === 0
      ? `Studio – ${apt.max_beds} bd`
      : `${apt.min_beds} – ${apt.max_beds} bd`;

  const priceLabel =
    apt.min_price == null
      ? 'Contact'
      : apt.min_price === apt.max_price
      ? `$${apt.min_price.toLocaleString()}`
      : `$${apt.min_price.toLocaleString()} – $${(apt.max_price ?? apt.min_price).toLocaleString()}`;

  return (
    <Link to={`/listings/${apt.id}`} className="block group shrink-0 w-56">
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm group-hover:shadow-md group-hover:border-indigo-200 transition-all duration-200 p-4">
        <p className="font-semibold text-slate-900 text-sm leading-tight mb-1 group-hover:text-indigo-700 transition-colors line-clamp-2">
          {apt.title}
        </p>
        <p className="text-xs text-slate-400 mb-3 truncate">{apt.location}</p>
        <p className="text-base font-bold text-slate-900 mb-1">{priceLabel}</p>
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">{bedLabel} · {apt.plan_count} plans</span>
          <span className="text-xs font-medium text-indigo-500 group-hover:text-indigo-700 transition-colors">
            View →
          </span>
        </div>
      </div>
    </Link>
  );
};

const ListingDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [listing, setListing] = useState<Listing | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAlert, setShowAlert] = useState(false);
  const [showAuth, setShowAuth] = useState(false);
  const [alertPlan, setAlertPlan] = useState<PlanResponse | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null);
  const [similar, setSimilar] = useState<SimilarResponse | null>(null);
  const { token } = useAuth();

  const openAlertForPlan = (e: React.MouseEvent, plan: PlanResponse) => {
    e.stopPropagation();
    if (!token) { setShowAuth(true); return; }
    setAlertPlan(plan);
    setShowAlert(true);
  };

  useEffect(() => {
    const aptId = Number(id);
    setLoading(true);
    setSimilar(null);
    api.getListing(aptId)
      .then(data => {
        setListing(data);
        // default selection: first plan by price
        const plans = data._raw?.plans ?? [];
        if (plans.length > 0) {
          const sorted = [...plans].sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity));
          setSelectedPlanId(sorted[0].id);
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
    // Fire-and-forget: similar section renders when ready, doesn't block the page
    api.getSimilarApartments(aptId).then(setSimilar).catch(() => {});
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
  const allPlans: PlanResponse[] = (apt?.plans ?? []).sort((a, b) => {
    if (a.price == null && b.price == null) return 0;
    if (a.price == null) return 1;
    if (b.price == null) return -1;
    return a.price - b.price;
  });

  const selectedPlan = allPlans.find(p => p.id === selectedPlanId) ?? allPlans[0] ?? null;
  const chartData = (selectedPlan?.price_history ?? []).map(h => ({
    date: new Date(h.recorded_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    price: h.price,
  }));

  const prices = allPlans.map(p => p.price).filter((p): p is number => p != null);
  const minP = prices.length ? Math.min(...prices) : null;
  const maxP = prices.length ? Math.max(...prices) : null;
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
                {minP != null ? `$${minP.toLocaleString()}` : 'Contact'}
              </span>
              {minP != null && maxP != null && maxP > minP && (
                <span className="text-slate-400 text-sm"> – ${maxP.toLocaleString()}</span>
              )}
              {minP != null && <span className="text-slate-400 text-sm">/mo</span>}
              {similar?.pct_vs_median != null && apt && (
                <div className="mt-1">
                  <MarketPill pct={similar.pct_vs_median} city={apt.city} />
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => { if (token) { setAlertPlan(null); setShowAlert(true); } else setShowAuth(true); }}
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
          <StatPill label="From" value={minP != null ? `$${minP.toLocaleString()}` : 'Contact'} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Plans table */}
        <div className="lg:col-span-3 bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100">
            <h2 className="font-semibold text-slate-900">Floor Plans</h2>
          </div>

          {/* Mobile card grid (hidden on md+) */}
          <div className="md:hidden divide-y divide-slate-50">
            {allPlans.map(plan => {
              const isSelected = plan.id === selectedPlan?.id;
              const spec = [
                plan.bedrooms === 0 ? 'Studio' : plan.bedrooms != null ? `${plan.bedrooms} bd` : null,
                plan.bathrooms != null ? `${plan.bathrooms} ba` : null,
                plan.area_sqft != null ? `${plan.area_sqft.toLocaleString()} sqft` : null,
              ].filter(Boolean).join(' · ');
              return (
                <div
                  key={plan.id}
                  onClick={() => setSelectedPlanId(plan.id)}
                  className={`p-4 cursor-pointer transition-colors ${isSelected ? 'bg-indigo-50' : 'hover:bg-slate-50'}`}
                >
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <span className="font-semibold text-slate-900 text-sm leading-snug">{plan.name}</span>
                    <span className={`shrink-0 text-xs px-2 py-0.5 rounded-full font-medium ${
                      plan.is_available ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
                    }`}>
                      {plan.is_available ? 'Available' : 'Unavailable'}
                    </span>
                  </div>
                  {spec && <p className="text-xs text-slate-400 mb-3">{spec}</p>}
                  <div className="flex items-center justify-between">
                    <span className="text-xl font-bold text-slate-900">
                      {plan.price != null
                        ? <>{`$${plan.price.toLocaleString()}`}<span className="text-xs font-normal text-slate-400">/mo</span></>
                        : <span className="text-slate-400 text-base font-normal">Contact</span>}
                    </span>
                    <button
                      onClick={e => openAlertForPlan(e, plan)}
                      className="text-xs bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1.5 rounded-lg transition-colors"
                    >
                      Set alert
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Desktop table (hidden below md) */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500 uppercase tracking-wider">
                <tr>
                  <th className="text-left px-4 py-3">Plan</th>
                  <th className="text-left px-4 py-3">Beds</th>
                  <th className="text-left px-4 py-3">Baths</th>
                  <th className="text-left px-4 py-3">Sqft</th>
                  <th className="text-right px-4 py-3">Price</th>
                  <th className="text-center px-4 py-3">Status</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {allPlans.map(plan => {
                  const isSelected = plan.id === selectedPlan?.id;
                  return (
                    <tr
                      key={plan.id}
                      onClick={() => setSelectedPlanId(plan.id)}
                      className={`cursor-pointer transition-colors ${isSelected ? 'bg-indigo-50 hover:bg-indigo-100' : 'hover:bg-slate-50'}`}
                    >
                      <td className="px-4 py-3 font-mono font-semibold text-slate-700 whitespace-nowrap">
                        {plan.name}
                        {isSelected && (
                          <span className="ml-2 text-xs text-indigo-500 font-sans">selected</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-600 whitespace-nowrap">
                        {plan.bedrooms === 0 ? 'Studio' : plan.bedrooms}
                      </td>
                      <td className="px-4 py-3 text-slate-600">{plan.bathrooms}</td>
                      <td className="px-4 py-3 text-slate-600 whitespace-nowrap">
                        {plan.area_sqft ? plan.area_sqft.toLocaleString() : '—'}
                      </td>
                      <td className="px-4 py-3 text-right font-semibold text-slate-900 whitespace-nowrap">
                        {plan.price != null ? `$${plan.price.toLocaleString()}` : <span className="text-slate-400 font-normal">Contact</span>}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`badge ${plan.is_available ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-400'}`}>
                          {plan.is_available ? 'Available' : 'Unavailable'}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-center">
                        <button
                          title="Set price alert for this plan"
                          onClick={(e) => openAlertForPlan(e, plan)}
                          className="text-slate-400 hover:text-indigo-600 transition-colors text-base leading-none"
                        >
                          🔔
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Price history chart */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-100 shadow-sm p-6">
          <h2 className="font-semibold text-slate-900 mb-3">Price History</h2>

          {/* Plan switcher pills */}
          {allPlans.length > 1 && (
            <div className="flex gap-2 overflow-x-auto pb-2 mb-4 -mx-1 px-1">
              {allPlans.map(plan => {
                const active = plan.id === selectedPlan?.id;
                return (
                  <button
                    key={plan.id}
                    onClick={() => setSelectedPlanId(plan.id)}
                    className={`shrink-0 text-xs px-3 py-1.5 rounded-full border font-medium transition-colors whitespace-nowrap ${
                      active
                        ? 'bg-indigo-600 text-white border-indigo-600'
                        : 'bg-white text-slate-500 border-slate-200 hover:border-indigo-300 hover:text-indigo-600'
                    }`}
                  >
                    {plan.name}
                    {plan.price != null && (
                      <span className={`ml-1.5 ${active ? 'text-indigo-200' : 'text-slate-400'}`}>
                        ${plan.price.toLocaleString()}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
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

      {/* Similar apartments */}
      {similar && similar.similar.length > 0 && apt && (
        <div className="mt-8">
          <div className="flex items-baseline gap-3 mb-4">
            <h2 className="text-lg font-semibold text-slate-900">
              Similar in {apt.city}
            </h2>
            {similar.city_median_price != null && (
              <span className="text-sm text-slate-400">
                Median {apt.city} {
                  // find primary bedroom count from first similar card (or first plan)
                  (() => {
                    const beds = allPlans[0]?.bedrooms;
                    return beds === 0 ? 'studio' : beds != null ? `${beds}bd` : '';
                  })()
                }: ${Math.round(similar.city_median_price).toLocaleString()}/mo
              </span>
            )}
          </div>
          <div className="flex gap-4 overflow-x-auto pb-2 -mx-1 px-1">
            {similar.similar.map(apt => (
              <SimilarCard key={apt.id} apt={apt} />
            ))}
          </div>
        </div>
      )}

      {showAlert && apt && (
        <AlertModal
          apartmentId={apt.id}
          apartmentTitle={listing.title}
          currentPrice={alertPlan ? (alertPlan.price ?? undefined) : (minP ?? undefined)}
          planId={alertPlan?.id}
          planName={alertPlan?.name}
          onClose={() => { setShowAlert(false); setAlertPlan(null); }}
          onCreated={() => { setShowAlert(false); setAlertPlan(null); }}
        />
      )}
      {showAuth && (
        <AuthModal onClose={() => setShowAuth(false)} />
      )}
    </div>
  );
};

export default ListingDetailPage;
