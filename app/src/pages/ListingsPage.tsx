import React, { useState, useEffect, useMemo, useRef, Suspense, lazy } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import api, { ApartmentSummary, ListingsFilter, SortOption } from '../services/api';
import { medianApartmentPrice } from '../utils/medianPrice';
import { cityStyle } from '../utils/cityColors';
import FilterPanel from '../components/FilterPanel';
import AuthModal from '../components/AuthModal';
import { useAuth } from '../context/AuthContext';

// Leaflet (~450 KB) is split into its own chunk and only loaded when the user
// opens the map view for the first time.
const MapView = lazy(() => import('../components/MapView'));

// ── Apartment complex card ────────────────────────────────────────────────────

const bedLabel = (min: number, max: number) => {
  if (min === max) return min === 0 ? 'Studio' : `${min} bd`;
  const lo = min === 0 ? 'Studio' : `${min} bd`;
  return `${lo} – ${max} bd`;
};

export interface ApartmentCardProps {
  apt: ApartmentSummary;
  favorited?: boolean;
  onFavoriteClick?: (e: React.MouseEvent) => void;
}

export const ApartmentCard: React.FC<ApartmentCardProps> = ({ apt, favorited = false, onFavoriteClick }) => {
  const c = cityStyle(apt.city);
  const priceRange = apt.min_price == null
    ? 'Contact for pricing'
    : apt.min_price === apt.max_price
      ? `$${apt.min_price.toLocaleString()}`
      : `$${apt.min_price.toLocaleString()} – $${(apt.max_price ?? apt.min_price).toLocaleString()}`;

  return (
    <Link to={`/listings/${apt.id}`} className="block group">
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm group-hover:shadow-md group-hover:border-indigo-200 transition-all duration-200 overflow-hidden">
        {/* Color accent bar */}
        <div className={`h-1 ${c.dot} opacity-60`} />

        <div className="p-5">
          {/* Header: city badge + heart */}
          <div className="flex items-center justify-between mb-3">
            <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full ${c.bg} ${c.text}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
              {apt.city}
            </span>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">
                {apt.available_count} / {apt.plan_count} available
              </span>
              {onFavoriteClick && (
                <button
                  onClick={onFavoriteClick}
                  title={favorited ? 'Remove from favorites' : 'Save to favorites'}
                  className={`text-lg leading-none transition-colors ${favorited ? 'text-rose-500 hover:text-rose-400' : 'text-slate-300 hover:text-rose-400'}`}
                >
                  {favorited ? '♥' : '♡'}
                </button>
              )}
            </div>
          </div>

          {/* Name */}
          <h2 className="text-lg font-bold text-slate-900 mb-0.5 group-hover:text-indigo-700 transition-colors leading-tight">
            {apt.title}
          </h2>
          <p className="text-xs text-slate-400 mb-4 truncate">{apt.location}</p>

          {/* Price */}
          <div className="mb-4">
            <span className="text-2xl font-bold text-slate-900">{priceRange}</span>
            {apt.min_price != null && <span className="text-slate-400 text-sm">/mo</span>}
          </div>

          {/* Footer: specs + cta */}
          <div className="flex items-center justify-between pt-3 border-t border-slate-50">
            <div className="flex items-center gap-3 text-sm text-slate-500">
              <span>🛏 {bedLabel(apt.min_beds, apt.max_beds)}</span>
              <span className="text-slate-200">|</span>
              <span>📋 {apt.plan_count} plans</span>
            </div>
            <span className="text-xs font-medium text-indigo-500 group-hover:text-indigo-700 transition-colors">
              View plans →
            </span>
          </div>
        </div>
      </div>
    </Link>
  );
};

// ── Skeleton ──────────────────────────────────────────────────────────────────
const Skeleton = () => (
  <div className="bg-white rounded-2xl border border-slate-100 overflow-hidden animate-pulse">
    <div className="h-1 bg-slate-100" />
    <div className="p-5 space-y-3">
      <div className="h-4 bg-slate-100 rounded w-1/3" />
      <div className="h-6 bg-slate-100 rounded w-2/3" />
      <div className="h-4 bg-slate-100 rounded w-full" />
      <div className="h-8 bg-slate-100 rounded w-1/2" />
      <div className="h-4 bg-slate-100 rounded w-full" />
    </div>
  </div>
);

// ── Page ──────────────────────────────────────────────────────────────────────
const ListingsPage: React.FC = () => {
  const { token, isFavorite, toggleFavorite } = useAuth();
  const [apts, setApts] = useState<ApartmentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<ListingsFilter>({});
  const [viewMode, setViewMode] = useState<'list' | 'map'>('list');
  const [showAuth, setShowAuth] = useState(false);
  const pendingFavoriteRef = useRef<number | null>(null);

  const handleFavorite = (e: React.MouseEvent, aptId: number) => {
    e.preventDefault(); // don't navigate into the card
    if (!token) {
      pendingFavoriteRef.current = aptId;
      setShowAuth(true);
      return;
    }
    const removing = isFavorite(aptId);
    toggleFavorite(aptId);
    toast(removing ? 'Removed from saved' : 'Saved ♥');
  };

  useEffect(() => {
    setLoading(true);
    setError(null);
    api.getApartments(filters)
      .then(setApts)
      .catch(err => setError(String(err)))
      .finally(() => setLoading(false));
  }, [filters]);

  // client-side filter by bedrooms (since API filters by min_bedrooms on plans)
  const filtered = useMemo(() => {
    let result = apts;
    if (filters.min_price) result = result.filter(a => a.max_price != null && a.max_price >= filters.min_price!);
    if (filters.max_price) result = result.filter(a => a.min_price != null && a.min_price <= filters.max_price!);
    if (filters.bedrooms !== undefined)
      result = result.filter(a => a.max_beds >= filters.bedrooms!);
    return result;
  }, [apts, filters]);

  const medianPrice = Math.round(medianApartmentPrice(apts));
  const totalPlans = apts.reduce((s, a) => s + a.plan_count, 0);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

      {/* Hero */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-slate-900 mb-1">Bay Area Rentals</h1>
        <p className="text-slate-500">
          Real floor-plan pricing scraped daily from apartment websites.
        </p>
      </div>

      {/* Stats */}
      {!loading && apts.length > 0 && (
        <div className="grid grid-cols-3 gap-2 sm:gap-4 mb-8">
          {[
            { label: 'Complexes',  value: apts.length.toString() },
            { label: 'Floor plans', value: totalPlans.toString() },
            { label: 'Median rent', value: `$${medianPrice.toLocaleString()}` },
          ].map(s => (
            <div key={s.label} className="bg-white rounded-xl border border-slate-100 shadow-sm px-3 sm:px-5 py-3 sm:py-4">
              <p className="text-xs text-slate-400 uppercase tracking-wider mb-1 truncate">{s.label}</p>
              <p className="text-xl sm:text-2xl font-bold text-slate-900">{s.value}</p>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-6">
        {/* Sidebar */}
        <aside className="w-60 shrink-0 hidden md:block">
          <div className="sticky top-20">
            <FilterPanel filters={filters} onFilterChange={setFilters} totalCount={filtered.length} />
          </div>
        </aside>

        {/* Main */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4">
            <p className="text-sm text-slate-500">
              {loading ? 'Loading…' : `${filtered.length} apartment${filtered.length !== 1 ? 's' : ''}`}
            </p>
            <div className="flex items-center gap-2 sm:gap-3">
              {/* Sort */}
              <select
                value={filters.sort ?? 'price_asc'}
                onChange={e => setFilters(f => ({ ...f, sort: e.target.value as SortOption }))}
                className="flex-1 sm:flex-none text-sm border border-slate-200 rounded-lg px-2.5 py-1.5 text-slate-600 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-300"
              >
                <option value="price_asc">Price: low to high</option>
                <option value="price_desc">Price: high to low</option>
                <option value="updated_desc">Recently updated</option>
                <option value="name_asc">Name A–Z</option>
              </select>
              {/* List / Map toggle */}
              <div className="flex items-center bg-slate-100 rounded-xl p-1 gap-1 shrink-0">
                <button
                  onClick={() => setViewMode('list')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    viewMode === 'list' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  ☰ List
                </button>
                <button
                  onClick={() => setViewMode('map')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    viewMode === 'map' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  🗺 Map
                </button>
              </div>
            </div>
          </div>

          {/* Mobile filters */}
          <div className="md:hidden mb-4">
            <FilterPanel filters={filters} onFilterChange={setFilters} totalCount={filtered.length} />
          </div>

          {loading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
              {Array.from({ length: 9 }).map((_, i) => <Skeleton key={i} />)}
            </div>
          ) : error ? (
            <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-700">
              <p className="font-semibold mb-1">Could not load listings</p>
              <p className="text-sm font-mono">{error}</p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-24 text-slate-400">
              <p className="text-5xl mb-4">🏠</p>
              <p className="text-lg font-medium text-slate-600">No apartments match your filters</p>
              <p className="text-sm mt-1">Try a different city or price range</p>
            </div>
          ) : viewMode === 'map' ? (
            <Suspense fallback={
              <div className="rounded-2xl bg-slate-50 border border-slate-100 h-[620px] flex items-center justify-center text-slate-400 text-sm">
                Loading map…
              </div>
            }>
              <MapView apartments={filtered} />
            </Suspense>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
              {filtered.map(apt => (
                <ApartmentCard
                  key={apt.id}
                  apt={apt}
                  favorited={isFavorite(apt.id)}
                  onFavoriteClick={e => handleFavorite(e, apt.id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>
      {showAuth && (
        <AuthModal
          onClose={() => setShowAuth(false)}
          onSuccess={() => {
            setShowAuth(false);
            if (pendingFavoriteRef.current != null) {
              toggleFavorite(pendingFavoriteRef.current);
              toast.success('Saved ♥');
              pendingFavoriteRef.current = null;
            }
          }}
        />
      )}
    </div>
  );
};

export default ListingsPage;
