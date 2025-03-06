import React from 'react';
import { ListingsFilter } from '../services/api';

interface Props {
  filters: ListingsFilter;
  onFilterChange: (filters: ListingsFilter) => void;
}

const FilterPanel: React.FC<Props> = ({ filters, onFilterChange }) => {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    onFilterChange({
      ...filters,
      [name]: value === '' ? undefined : name.includes('price') ? parseFloat(value) : value
    });
  };

  return (
    <div className="bg-white p-4 rounded-lg shadow mb-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700">Location</label>
          <input
            type="text"
            name="location"
            value={filters.location || ''}
            onChange={handleChange}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
            placeholder="Enter location"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">Min Price</label>
          <input
            type="number"
            name="min_price"
            value={filters.min_price || ''}
            onChange={handleChange}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
            placeholder="Min price"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">Max Price</label>
          <input
            type="number"
            name="max_price"
            value={filters.max_price || ''}
            onChange={handleChange}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
            placeholder="Max price"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">Bedrooms</label>
          <select
            name="bedrooms"
            value={filters.bedrooms || ''}
            onChange={handleChange}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
          >
            <option value="">Any</option>
            {[1, 2, 3, 4, 5].map(num => (
              <option key={num} value={num}>{num}+ beds</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
};

export default FilterPanel; 