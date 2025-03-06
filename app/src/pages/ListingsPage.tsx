import React, { useState, useEffect } from 'react';
import api, { Listing, ListingsFilter } from '../services/api';
import ListingCard from '../components/ListingCard';
import FilterPanel from '../components/FilterPanel';

const ListingsPage: React.FC = () => {
  const [listings, setListings] = useState<Listing[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [filters, setFilters] = useState<ListingsFilter>({});

  useEffect(() => {
    void fetchListings();
  }, [filters]);

  const fetchListings = async (): Promise<void> => {
    try {
      setLoading(true);
      const data = await api.getListings(filters);
      setListings(data);
    } catch (error) {
      console.error('Error fetching listings:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-8">Rental Listings</h1>
      
      <FilterPanel filters={filters} onFilterChange={setFilters} />
      
      {loading ? (
        <div className="flex justify-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900" />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {listings.map((listing: Listing) => (
            <ListingCard key={listing.id} listing={listing} />
          ))}
        </div>
      )}
    </div>
  );
};

export default ListingsPage; 