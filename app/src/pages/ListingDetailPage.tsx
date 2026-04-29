import React, { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';
import api, { Listing, PlanResponse, UnitResponse, SimilarApartment, SimilarResponse } from '../services/api';
import { useAuth } from '../context/AuthContext';
import AlertModal from '../components/AlertModal';
import AuthModal from '../components/AuthModal';

// Fix Leaflet default marker icons
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({ iconUrl: markerIcon, iconRetinaUrl: markerIcon2x, shadowUrl: markerShadow });

// ---------------------------------------------------------------------------
// Plan grouping helpers
// ---------------------------------------------------------------------------

interface PlanGroup {
  key: string;
  name: string | null;
  bedrooms: number | null;
  bathrooms: number | null;
  area_sqft: number | null;
  options: PlanResponse[];  // sorted cheapest first
}

function groupPlans(plans: PlanResponse[]): PlanGroup[] {
  const groups = new Map<string, PlanGroup>();
  for (const plan of plans) {
    const sqftKey = plan.area_sqft != null ? Math.round(plan.area_sqft) : 'null';
    const key = `${plan.bedrooms ?? 'x'}|${plan.bathrooms ?? 'x'}|${sqftKey}`;
    if (!groups.has(key)) {
      groups.set(key, { key, name: plan.name ?? null, bedrooms: plan.bedrooms, bathrooms: plan.bathrooms, area_sqft: plan.area_sqft, options: [] });
    }
    groups.get(key)!.options.push(plan);
  }
  groups.forEach(g => {
    g.options.sort((a: PlanResponse, b: PlanResponse) => (a.price ?? Infinity) - (b.price ?? Infinity));
  });
  const result: PlanGroup[] = [];
  groups.forEach(g => result.push(g));
  return result.sort((a: PlanGroup, b: PlanGroup) => {
    const aMin = a.options[0]?.price ?? Infinity;
    const bMin = b.options[0]?.price ?? Infinity;
    return aMin - bMin;
  });
}

// Generic name pattern: "1 Bed / 1 Bath" style auto-generated from beds/baths/sqft
const _GENERIC_PLAN_NAME_RE = /^(Studio|\d+\s*Bed(room)?s?)\s*[/\-]\s*\d+(\.\d+)?\s*Bath/i;

function planDisplayName(g: PlanGroup): string {
  // Prefer the actual plan name (e.g. "Santa Cruz", "A1", "1x1A") unless it is
  // a generic beds/baths description, in which case fall back to formatted label.
  if (g.name && !_GENERIC_PLAN_NAME_RE.test(g.name)) {
    return g.name;
  }
  const bedLabel = g.bedrooms === 0 ? 'Studio' : g.bedrooms != null ? `${g.bedrooms} Bed` : '?';
  const bathLabel = g.bathrooms != null ? `${g.bathrooms} Bath` : null;
  const sqftLabel = g.area_sqft != null ? `${g.area_sqft.toLocaleString()} sqft` : null;
  const parts = [bedLabel, bathLabel, sqftLabel].filter(Boolean);
  return parts.join(' / ');
}

function availLabel(plan: PlanResponse): string {
  if (!plan.is_available) return 'Unavailable';
  // plan.available_from is null for unit-level adapters (e.g. AvalonBay);
  // derive the soonest available date from units instead.
  let dateStr = plan.available_from;
  if (!dateStr && (plan.units ?? []).length > 0) {
    const soonest = (plan.units ?? [])
      .filter(u => u.is_available && u.available_from)
      .map(u => u.available_from!)
      .sort()[0] ?? null;
    dateStr = soonest;
  }
  if (!dateStr) return 'Now';
  const d = new Date(dateStr);
  if (d <= new Date()) return 'Now';
  return d.toLocaleDateString('en-US', { month: 'numeric', day: 'numeric' });
}

interface PriceRow {
  key: string;
  plan: PlanResponse;
  unit?: UnitResponse;
  price: number | null;
  available_from: string | null;
  external_url: string | null;
}

function priceRowsForGroup(group: PlanGroup): PriceRow[] {
  const rows: PriceRow[] = [];
  for (const plan of group.options) {
    const availableUnits = (plan.units ?? []).filter(u => u.is_available);
    if (availableUnits.length > 0) {
      for (const unit of availableUnits) {
        rows.push({
          key: `u-${unit.id}`,
          plan,
          unit,
          price: unit.price,
          available_from: unit.available_from,
          external_url: plan.external_url,
        });
      }
    } else {
      // Adapter without unit-level data — use plan as the price row
      rows.push({
        key: `p-${plan.id}`,
        plan,
        price: plan.current_price ?? plan.price,
        available_from: plan.available_from,
        external_url: plan.external_url,
      });
    }
  }
  rows.sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity));
  return rows;
}

function unitAvailLabel(row: PriceRow): string {
  if (row.unit && !row.unit.is_available) return 'Unavailable';
  if (!row.available_from) return 'Now';
  const d = new Date(row.available_from);
  if (d <= new Date()) return 'Now';
  return d.toLocaleDateString('en-US', { month: 'numeric', day: 'numeric' });
}

const StatPill: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="bg-slate-50 rounded-xl px-2 sm:px-4 py-3 text-center">
    <p className="text-xs text-slate-400 uppercase tracking-wider mb-0.5 truncate">{label}</p>
    <p className="font-bold text-slate-900 text-sm sm:text-base">{value}</p>
  </div>
);

const MarketPill: React.FC<{
  targetPrice: number;
  median: number;
  city: string;
  beds: number;
  planCount?: number;
}> = ({ targetPrice, median, city, beds, planCount }) => {
  const diff = targetPrice - median;
  const pct = diff / median;
  const absDiff = Math.abs(Math.round(diff));
  const bedLabel = beds === 0 ? 'studio' : `${beds}BR`;
  const medianFmt = `$${Math.round(median).toLocaleString()}`;

  const label =
    absDiff < 50
      ? `At ${city} median (${medianFmt}) for ${bedLabel}`
      : diff < 0
      ? `$${absDiff.toLocaleString()} below ${city} median (${medianFmt}) for ${bedLabel}`
      : `$${absDiff.toLocaleString()} above ${city} median (${medianFmt}) for ${bedLabel}`;

  const colors =
    diff <= 0
      ? 'bg-emerald-100 text-emerald-700'
      : pct > 0.10
      ? 'bg-amber-100 text-amber-700'
      : 'bg-slate-100 text-slate-600';

  const tooltip = planCount
    ? `Median of ${planCount} currently-available ${bedLabel} asking prices in ${city}`
    : `Median ${bedLabel} asking price in ${city}`;

  return (
    <div className="flex items-center gap-1.5">
      <span className={`inline-block text-xs font-medium px-2.5 py-1 rounded-full ${colors}`}>
        {label}
      </span>
      <span title={tooltip} className="text-xs text-slate-400 hover:text-slate-600 cursor-help select-none">
        ⓘ
      </span>
    </div>
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
  const [showPlanPicker, setShowPlanPicker] = useState(false);
  const [alertPlan, setAlertPlan] = useState<PlanResponse | null>(null);
  const [alertUnit, setAlertUnit] = useState<UnitResponse | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null);
  const [similar, setSimilar] = useState<SimilarResponse | null>(null);
  const { token } = useAuth();
  // Stores the action to resume after a successful login from this page
  const authSuccessRef = useRef<(() => void) | null>(null);

  const openAlertForPlan = (e: React.MouseEvent, plan: PlanResponse, unit?: UnitResponse) => {
    e.stopPropagation();
    if (!token) {
      setAlertPlan(plan);
      setAlertUnit(unit ?? null);
      authSuccessRef.current = () => { setShowAuth(false); setShowAlert(true); };
      setShowAuth(true);
      return;
    }
    setAlertPlan(plan);
    setAlertUnit(unit ?? null);
    setShowAlert(true);
  };

  const openAlertFromHeader = () => {
    // If plans are loaded, pick directly when single plan; otherwise show picker
    const plans: PlanResponse[] = (listing?._raw?.plans ?? []).filter(p => p.is_available && p.price != null);
    if (plans.length === 0) return;
    if (plans.length === 1) {
      if (!token) {
        setAlertPlan(plans[0]);
        authSuccessRef.current = () => { setShowAuth(false); setShowAlert(true); };
        setShowAuth(true);
      } else {
        setAlertPlan(plans[0]);
        setShowAlert(true);
      }
    } else {
      if (!token) {
        authSuccessRef.current = () => { setShowAuth(false); setShowPlanPicker(true); };
        setShowAuth(true);
      } else {
        setShowPlanPicker(true);
      }
    }
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
  const hasFloor = allPlans.some(p => p.floor_level != null);
  const hasFacing = allPlans.some(p => p.facing != null);
  const planGroups = groupPlans(allPlans);

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
          <div className="flex flex-col items-start sm:items-end gap-2 shrink-0">
            <div className="sm:text-right">
              <span className="text-3xl font-bold text-indigo-600">
                {minP != null ? `$${minP.toLocaleString()}` : 'Contact'}
              </span>
              {minP != null && maxP != null && maxP > minP && (
                <span className="text-slate-400 text-sm"> – ${maxP.toLocaleString()}</span>
              )}
              {minP != null && <span className="text-slate-400 text-sm">/mo</span>}
            </div>
            <div className="flex items-center gap-2 w-full sm:w-auto">
              {apt?.data_source_type !== 'unscrapeable' && apt?.data_source_type !== 'legal_block' && (
                <button
                  onClick={openAlertFromHeader}
                  className="flex items-center gap-1.5 text-sm bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-4 py-2 rounded-xl transition-colors"
                >
                  🔔 Set Alert
                </button>
              )}
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
        <div className="grid grid-cols-3 gap-2 sm:gap-3 mt-6">
          <StatPill label="Floor plans" value={String(allPlans.length)} />
          <StatPill label="Available now" value={`${availCount} / ${allPlans.length}`} />
          <StatPill label="From" value={minP != null ? `$${minP.toLocaleString()}` : 'Contact'} />
        </div>
      </div>

      {/* Market context — standalone row between header and plans */}
      {similar?.city_median_price != null && apt && minP != null && (
        <div className="mb-6">
          <MarketPill
            targetPrice={minP}
            median={similar.city_median_price}
            city={apt.city}
            beds={allPlans[0]?.bedrooms ?? 1}
            planCount={similar.city_plan_count ?? undefined}
          />
        </div>
      )}

      {/* Legal block banner — shown when ToS or C&D prevents data collection */}
      {apt?.data_source_type === 'legal_block' && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6">
          <div className="flex items-start gap-3">
            <svg className="w-5 h-5 text-amber-600 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M12 15v2m0 0v2m0-2h2m-2 0H10m2-6V7m0 0V5m0 2h2m-2 0H10M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <p className="font-medium text-amber-900">Price data not available</p>
              <p className="text-sm text-amber-800 mt-1">
                AptTrack cannot collect pricing for this property due to terms of service or legal restrictions.
                Visit the property website directly for current rates.
              </p>
              {apt?.source_url && (() => {
                try {
                  return (
                    <a href={apt.source_url} target="_blank" rel="noopener noreferrer"
                       className="inline-flex items-center gap-1 mt-2 text-sm font-medium text-amber-900 underline">
                      Visit {new URL(apt.source_url).hostname} →
                    </a>
                  );
                } catch {
                  return null;
                }
              })()}
            </div>
          </div>
        </div>
      )}

      {/* Unscrapeable banner — shown instead of floor plans for sites that don't publish pricing */}
      {apt?.data_source_type === 'unscrapeable' && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6">
          <div className="flex items-start gap-3">
            <svg className="w-5 h-5 text-amber-600 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <p className="font-medium text-amber-900">Pricing not published online</p>
              <p className="text-sm text-amber-800 mt-1">
                This property requires direct contact for current rates.
                AptTrack can&apos;t track price history for listings that don&apos;t publish prices.
              </p>
              {apt?.source_url && (() => {
                try {
                  return (
                    <a href={apt.source_url} target="_blank" rel="noopener noreferrer"
                       className="inline-flex items-center gap-1 mt-2 text-sm font-medium text-amber-900 underline">
                      Visit {new URL(apt.source_url).hostname} →
                    </a>
                  );
                } catch {
                  return null;
                }
              })()}
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Plans table — wider */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100">
            <h2 className="font-semibold text-slate-900">Floor Plans</h2>
          </div>

          {/* Mobile cards */}
          <div className="md:hidden divide-y divide-slate-50">
            {planGroups.map(group => {
              const rep = group.options[0];
              const isSelected = group.options.some(o => o.id === selectedPlan?.id);
              const spec = [
                group.bedrooms === 0 ? 'Studio' : group.bedrooms != null ? `${group.bedrooms} bd` : null,
                group.bathrooms != null ? `${group.bathrooms} ba` : null,
                group.area_sqft ? group.area_sqft.toLocaleString() + ' sqft' : null,
              ].filter(Boolean).join(' · ');
              return (
                <div key={group.key} onClick={() => setSelectedPlanId(rep.id)}
                  className={`p-4 cursor-pointer transition-colors ${isSelected ? 'bg-indigo-50' : 'hover:bg-slate-50'}`}>
                  <p className="font-semibold text-slate-800 text-sm mb-1">{spec}</p>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {group.options.map(opt => (
                      <div key={opt.id} className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5">
                        <span className="font-bold text-slate-900 text-sm">
                          {opt.price != null ? `$${opt.price.toLocaleString()}` : 'Contact'}
                        </span>
                        <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${availLabel(opt) === 'Now' ? 'bg-emerald-100 text-emerald-700' : availLabel(opt) === 'Unavailable' ? 'bg-slate-100 text-slate-400' : 'bg-amber-100 text-amber-700'}`}>
                          {availLabel(opt) === 'Now' ? 'Now' : availLabel(opt) === 'Unavailable' ? 'N/A' : availLabel(opt)}
                        </span>
                        <button onClick={e => openAlertForPlan(e, opt)} className="text-slate-300 hover:text-indigo-500 text-sm">🔔</button>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500 uppercase tracking-wider">
                <tr>
                  <th className="text-left px-4 py-3">Plan</th>
                  <th className="text-left px-4 py-3">Beds</th>
                  <th className="text-left px-4 py-3">Baths</th>
                  <th className="text-left px-4 py-3">Sqft</th>
                  {hasFloor && <th className="text-left px-4 py-3">Floor</th>}
                  {hasFacing && <th className="text-left px-4 py-3">Facing</th>}
                  <th className="text-left px-4 py-3">Price / Availability</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {planGroups.map(group => {
                  const priceRows = priceRowsForGroup(group);
                  const rep = group.options[0];
                  const isSelected = group.options.some(o => o.id === selectedPlan?.id);
                  const useDropdown = priceRows.length > 2;
                  const selectedRow = priceRows.find(r => r.plan.id === selectedPlan?.id) ?? priceRows[0];
                  return (
                    <tr key={group.key}
                      onClick={() => setSelectedPlanId(rep.id)}
                      className={`cursor-pointer transition-colors ${isSelected ? 'bg-indigo-50 hover:bg-indigo-100' : 'hover:bg-slate-50'}`}>
                      <td className="px-4 py-3 font-medium text-slate-800 whitespace-nowrap">
                        {planDisplayName(group)}
                      </td>
                      <td className="px-4 py-3 text-slate-600">
                        {group.bedrooms === 0 ? 'Studio' : group.bedrooms ?? '—'}
                      </td>
                      <td className="px-4 py-3 text-slate-600">{group.bathrooms ?? '—'}</td>
                      <td className="px-4 py-3 text-slate-600 whitespace-nowrap">
                        {group.area_sqft ? group.area_sqft.toLocaleString() : '—'}
                      </td>
                      {hasFloor && <td className="px-4 py-3 text-slate-600">{rep.floor_level ?? '—'}</td>}
                      {hasFacing && <td className="px-4 py-3 text-slate-600">{rep.facing ?? '—'}</td>}
                      <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                        {useDropdown ? (
                          /* Dropdown for groups with many price rows */
                          <div className="flex items-center gap-2">
                            <select
                              value={selectedRow?.key}
                              onChange={e => {
                                const row = priceRows.find(r => r.key === e.target.value);
                                if (row) setSelectedPlanId(row.plan.id);
                              }}
                              className="border border-slate-200 rounded-lg px-2.5 py-1.5 text-sm text-slate-800 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 cursor-pointer"
                            >
                              {priceRows.map(row => (
                                <option key={row.key} value={row.key}>
                                  {row.price != null ? `$${row.price.toLocaleString()}` : 'Contact'}
                                  {row.unit?.unit_number ? ` · ${row.unit.unit_number}` : ''}
                                  {' — '}{unitAvailLabel(row)}
                                </option>
                              ))}
                            </select>
                            {(selectedRow?.external_url || apt?.source_url) && (
                              <a href={selectedRow?.external_url || apt!.source_url!} target="_blank" rel="noopener noreferrer"
                                className="text-indigo-400 hover:text-indigo-600 text-xs">↗</a>
                            )}
                            <button title="Set price alert"
                              onClick={e => openAlertForPlan(e, selectedRow.plan, selectedRow.unit)}
                              className="text-slate-400 hover:text-indigo-500 transition-colors">🔔</button>
                          </div>
                        ) : (
                          /* Chips for 1–2 price rows */
                          <div className="flex flex-wrap gap-2">
                            {priceRows.map(row => {
                              const avail = unitAvailLabel(row);
                              const availColor = avail === 'Now' ? 'bg-emerald-100 text-emerald-700' : avail === 'Unavailable' ? 'bg-slate-100 text-slate-400' : 'bg-amber-100 text-amber-700';
                              return (
                                <div key={row.key} onClick={() => setSelectedPlanId(row.plan.id)}
                                  className="flex items-center gap-1.5 border border-slate-200 rounded-lg px-2.5 py-1.5 hover:border-indigo-300 transition-colors bg-white cursor-pointer">
                                  <span className="font-bold text-slate-900 whitespace-nowrap">
                                    {row.price != null ? `$${row.price.toLocaleString()}` : 'Contact'}
                                  </span>
                                  <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium whitespace-nowrap ${availColor}`}>
                                    {avail}
                                  </span>
                                  {(row.external_url || apt?.source_url) && (
                                    <a href={row.external_url || apt!.source_url!} target="_blank" rel="noopener noreferrer"
                                      onClick={e => e.stopPropagation()} className="text-indigo-300 hover:text-indigo-500 text-xs">↗</a>
                                  )}
                                  <button title="Set price alert"
                                    onClick={e => openAlertForPlan(e, row.plan, row.unit)}
                                    className="text-slate-300 hover:text-indigo-500 transition-colors">🔔</button>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right column: mini map + price history */}
        <div className="lg:col-span-1 flex flex-col gap-6">
          {/* Mini map */}
          {apt?.latitude != null && apt?.longitude != null && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-100">
                <h2 className="font-semibold text-slate-900 text-sm">Location</h2>
              </div>
              <div className="h-48">
                <MapContainer
                  center={[apt.latitude, apt.longitude]}
                  zoom={15}
                  scrollWheelZoom={false}
                  style={{ height: '100%', width: '100%' }}
                  zoomControl={true}
                >
                  <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                  <Marker position={[apt.latitude, apt.longitude]}>
                    <Popup>{listing.title}</Popup>
                  </Marker>
                </MapContainer>
              </div>
            </div>
          )}

          {/* Price history chart */}
          <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6 flex-1">
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
        </div> {/* end right column */}
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

      {showPlanPicker && apt && (() => {
        const pickerPlans = allPlans.filter(p => p.is_available && p.price != null);
        return (
          <div
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
            onClick={e => { if (e.target === e.currentTarget) setShowPlanPicker(false); }}
          >
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-bold text-slate-900">Which floor plan?</h2>
                <button onClick={() => setShowPlanPicker(false)} className="text-slate-400 hover:text-slate-600 text-xl leading-none">×</button>
              </div>
              <p className="text-sm text-slate-500 mb-4">Select a plan to set a price alert for:</p>
              <div className="space-y-2 max-h-72 overflow-y-auto">
                {pickerPlans.map(plan => (
                  <button
                    key={plan.id}
                    onClick={() => { setShowPlanPicker(false); setAlertPlan(plan); setShowAlert(true); }}
                    className="w-full text-left px-4 py-3 rounded-xl border border-slate-200 hover:border-indigo-400 hover:bg-indigo-50 transition-colors"
                  >
                    <span className="font-semibold text-slate-800 text-sm">{plan.name}</span>
                    <span className="text-slate-500 text-sm ml-2">
                      {plan.bedrooms === 0 ? 'Studio' : `${plan.bedrooms}bd`}
                      {plan.bathrooms != null ? ` / ${plan.bathrooms}ba` : ''}
                      {plan.area_sqft ? ` · ${plan.area_sqft.toLocaleString()} sqft` : ''}
                    </span>
                    <span className="block text-indigo-600 font-bold text-sm mt-0.5">${plan.price!.toLocaleString()}/mo</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        );
      })()}
      {showAlert && apt && apt.data_source_type !== 'unscrapeable' && apt.data_source_type !== 'legal_block' && (
        <AlertModal
          apartmentId={apt.id}
          apartmentTitle={listing.title}
          currentPrice={alertUnit?.price ?? alertPlan?.current_price ?? alertPlan?.price ?? minP ?? undefined}
          planId={alertPlan?.id}
          planName={alertPlan?.name}
          unitId={alertUnit?.id}
          unitNumber={alertUnit?.unit_number ?? undefined}
          onClose={() => { setShowAlert(false); setAlertPlan(null); setAlertUnit(null); }}
          onCreated={() => { setShowAlert(false); setAlertPlan(null); setAlertUnit(null); }}
        />
      )}
      {showAuth && (
        <AuthModal
          onClose={() => setShowAuth(false)}
          onSuccess={() => {
            authSuccessRef.current?.();
            authSuccessRef.current = null;
          }}
        />
      )}
    </div>
  );
};

export default ListingDetailPage;
