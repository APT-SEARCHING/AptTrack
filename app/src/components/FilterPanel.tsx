import React, { useState } from 'react';
import { ListingsFilter } from '../services/api';

interface Props {
  filters: ListingsFilter;
  onFilterChange: (filters: ListingsFilter) => void;
  totalCount: number;
}

const FilterPanel: React.FC<Props> = ({ filters, onFilterChange, totalCount }) => {
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const set = (key: keyof ListingsFilter, value: string) => {
    onFilterChange({
      ...filters,
      [key]: value === '' ? undefined : key.includes('price') || key === 'bedrooms' || key.includes('sqft')
        ? parseFloat(value)
        : value,
    });
  };

  const setBool = (key: keyof ListingsFilter, checked: boolean) => {
    onFilterChange({ ...filters, [key]: checked || undefined });
  };

  const clear = () => onFilterChange({});

  // pets_allowed (32%) and has_parking (26%) are hidden until coverage ≥ 60%.
  // Re-add to advancedKeys and the checkbox block below once data improves post-deploy.
  const advancedKeys: (keyof ListingsFilter)[] = ['min_sqft', 'max_sqft', 'available_before'];
  const hasAdvanced = advancedKeys.some(k => filters[k] !== undefined && filters[k] !== '');
  const hasFilters = Object.values(filters).some(v => v !== undefined && v !== '');

  // Keep advanced open if any advanced filter is active
  const effectiveOpen = advancedOpen || hasAdvanced;

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      {/* City */}
      <div className="mb-4">
        <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
          City
        </label>
        <div className="relative">
          <span className="absolute left-3 top-2.5 text-slate-400 text-sm">📍</span>
          <input
            type="text"
            value={filters.location || ''}
            onChange={e => set('location', e.target.value)}
            className="input-base pl-8"
            placeholder="e.g. Oakland"
          />
        </div>
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
          {[['Any', ''], ['Studio', '0'], ['1+', '1'], ['2+', '2'], ['3+', '3']].map(([label, val]) => (
            <button
              key={val}
              onClick={() => set('bedrooms', val)}
              className={`px-3 py-1 rounded-lg text-sm font-medium border transition-colors ${
                (filters.bedrooms?.toString() ?? '') === val || (val === '' && !filters.bedrooms)
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white text-slate-600 border-slate-200 hover:border-indigo-300'
              }`}
            >
              {label}
            </button>
          ))}
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
