import React from 'react';
import { ListingsFilter } from '../services/api';

interface Props {
  filters: ListingsFilter;
  onFilterChange: (filters: ListingsFilter) => void;
  totalCount: number;
}

const FilterPanel: React.FC<Props> = ({ filters, onFilterChange, totalCount }) => {
  const set = (key: keyof ListingsFilter, value: string) => {
    onFilterChange({
      ...filters,
      [key]: value === '' ? undefined : key.includes('price') || key === 'bedrooms'
        ? parseFloat(value)
        : value,
    });
  };

  const clear = () => onFilterChange({});
  const hasFilters = Object.values(filters).some(v => v !== undefined && v !== '');

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      {/* Search */}
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
        <div className="flex gap-2">
          <input
            type="number"
            value={filters.min_price || ''}
            onChange={e => set('min_price', e.target.value)}
            className="input-base"
            placeholder="Min $"
          />
          <input
            type="number"
            value={filters.max_price || ''}
            onChange={e => set('max_price', e.target.value)}
            className="input-base"
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

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-slate-100">
        <span className="text-sm text-slate-500">
          <span className="font-semibold text-slate-800">{totalCount}</span> plans
        </span>
        {hasFilters && (
          <button onClick={clear} className="text-xs text-indigo-600 hover:text-indigo-800 font-medium">
            Clear filters
          </button>
        )}
      </div>
    </div>
  );
};

export default FilterPanel;
