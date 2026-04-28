import React, { useEffect, useState } from 'react';
import api, { ListingsFilter } from '../services/api';

interface Props {
  filters: ListingsFilter;
  onFilterChange: (filters: ListingsFilter) => void;
  totalCount: number;
}

const FilterPanel: React.FC<Props> = ({ filters, onFilterChange, totalCount }) => {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [cities, setCities] = useState<string[]>([]);

  useEffect(() => {
    api.getCities().then(setCities).catch(() => {});
  }, []);

  const set = (key: keyof ListingsFilter, value: string) => {
    onFilterChange({
      ...filters,
      [key]: value === '' ? undefined : key.includes('price') || key === 'bedrooms' || key.includes('sqft')
        ? parseFloat(value)
        : value,
    });
  };

  const toggleBedroom = (count: number | null) => {
    if (count === null) {
      onFilterChange({ ...filters, bedroom_counts: undefined });
      return;
    }
    const current = filters.bedroom_counts ?? [];
    const next = current.includes(count)
      ? current.filter(c => c !== count)
      : [...current, count];
    onFilterChange({ ...filters, bedroom_counts: next.length > 0 ? next : undefined });
  };

  const setBool = (key: keyof ListingsFilter, checked: boolean) => {
    onFilterChange({ ...filters, [key]: checked || undefined });
  };

  const toggleCity = (city: string) => {
    const current = filters.cities ?? [];
    const next = current.includes(city)
      ? current.filter(c => c !== city)
      : [...current, city];
    onFilterChange({ ...filters, cities: next.length > 0 ? next : undefined });
  };

  const clear = () => onFilterChange({});

  // pets_allowed (32%) and has_parking (26%) are hidden until coverage ≥ 60%.
  // Re-add to advancedKeys and the checkbox block below once data improves post-deploy.
  const advancedKeys: (keyof ListingsFilter)[] = ['min_sqft', 'max_sqft', 'available_before'];
  const hasAdvanced = advancedKeys.some(k => filters[k] !== undefined && filters[k] !== '');
  const hasFilters = Object.values(filters).some(v =>
    v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0)
  );

  // Keep advanced open if any advanced filter is active
  const effectiveOpen = advancedOpen || hasAdvanced;

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      {/* Search */}
      <div className="mb-4">
        <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
          Search
        </label>
        <input
          type="text"
          placeholder="Apartment name…"
          value={filters.search ?? ''}
          onChange={e => onFilterChange({ ...filters, search: e.target.value || undefined })}
          className="w-full px-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300 placeholder-slate-400"
        />
      </div>

      {/* City */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-1.5">
          <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">
            City
          </label>
          {(filters.cities?.length ?? 0) > 0 && (
            <button
              onClick={() => onFilterChange({ ...filters, cities: undefined })}
              className="text-xs text-indigo-500 hover:text-indigo-700"
            >
              Clear
            </button>
          )}
        </div>
        {cities.length === 0 ? (
          <p className="text-xs text-slate-400">Loading…</p>
        ) : (
          <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
            {cities.map(city => {
              const checked = (filters.cities ?? []).includes(city);
              return (
                <label key={city} className="flex items-center gap-2 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleCity(city)}
                    className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-400 cursor-pointer"
                  />
                  <span className={`text-sm transition-colors ${checked ? 'text-indigo-700 font-medium' : 'text-slate-600 group-hover:text-slate-900'}`}>
                    {city}
                  </span>
                </label>
              );
            })}
          </div>
        )}
      </div>

      {/* Price range */}
      <div className="mb-4">
        <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
          Monthly Rent
        </label>
        <div className="grid grid-cols-2 gap-2">
          <input
            type="number"
            value={filters.min_price || ''}
            onChange={e => set('min_price', e.target.value)}
            className="input-base min-w-0"
            placeholder="Min $"
          />
          <input
            type="number"
            value={filters.max_price || ''}
            onChange={e => set('max_price', e.target.value)}
            className="input-base min-w-0"
            placeholder="Max $"
          />
        </div>
      </div>

      {/* Bedrooms */}
      <div className="mb-5">
        <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
          Bedrooms
        </label>
        <div className="flex gap-1.5 flex-wrap">
          <button
            onClick={() => toggleBedroom(null)}
            className={`px-3 py-1 rounded-lg text-sm font-medium border transition-colors ${
              !filters.bedroom_counts?.length
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'bg-white text-slate-600 border-slate-200 hover:border-indigo-300'
            }`}
          >
            Any
          </button>
          {([['Studio', 0], ['1', 1], ['2', 2], ['3', 3]] as [string, number][]).map(([label, count]) => {
            const active = filters.bedroom_counts?.includes(count) ?? false;
            return (
              <button
                key={count}
                onClick={() => toggleBedroom(count)}
                className={`px-3 py-1 rounded-lg text-sm font-medium border transition-colors ${
                  active
                    ? 'bg-indigo-600 text-white border-indigo-600'
                    : 'bg-white text-slate-600 border-slate-200 hover:border-indigo-300'
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Advanced toggle */}
      <button
        onClick={() => setAdvancedOpen(o => !o)}
        className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 hover:text-indigo-600 transition-colors mb-3 w-full"
      >
        <span className={`transition-transform duration-150 inline-block ${effectiveOpen ? 'rotate-90' : ''}`}>▶</span>
        Advanced
        {hasAdvanced && (
          <span className="ml-auto bg-indigo-100 text-indigo-600 rounded-full px-1.5 py-0.5 text-xs font-semibold">
            {advancedKeys.filter(k => filters[k] !== undefined).length}
          </span>
        )}
      </button>

      {effectiveOpen && (
        <div className="space-y-4 pt-3 border-t border-slate-100">
          {/* Sqft range */}
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
              Size (sqft)
            </label>
            <div className="grid grid-cols-2 gap-2">
              <input
                type="number"
                value={filters.min_sqft || ''}
                onChange={e => set('min_sqft', e.target.value)}
                className="input-base min-w-0"
                placeholder="Min"
              />
              <input
                type="number"
                value={filters.max_sqft || ''}
                onChange={e => set('max_sqft', e.target.value)}
                className="input-base min-w-0"
                placeholder="Max"
              />
            </div>
          </div>

          {/* Available before */}
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
              Available before
            </label>
            <input
              type="date"
              value={filters.available_before || ''}
              onChange={e => onFilterChange({ ...filters, available_before: e.target.value || undefined })}
              className="input-base w-full"
            />
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-slate-100 mt-4">
        <span className="text-sm text-slate-500">
          <span className="font-semibold text-slate-800">{totalCount}</span> complexes
        </span>
        {hasFilters && (
          <button onClick={clear} className="text-xs text-indigo-600 hover:text-indigo-800 font-medium">
            Clear all
          </button>
        )}
      </div>
    </div>
  );
};

export default FilterPanel;
