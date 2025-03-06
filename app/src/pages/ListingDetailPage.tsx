import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import api, { Listing } from '../services/api';

const ListingDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [listing, setListing] = useState<Listing | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchListing = async () => {
      try {
        setLoading(true);
        const data = await api.getListing(Number(id));
        setListing(data);
      } catch (error) {
        console.error('Error fetching listing:', error);
      } finally {
        setLoading(false);
      }
    };

    void fetchListing();
  }, [id]);

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900" />
      </div>
    );
  }

  if (!listing) {
    return (
      <div className="container mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-red-600">Listing not found</h1>
      </div>
    );
  }

  const priceHistory = listing.price_history.map(history => ({
    date: new Date(history.recorded_at).toLocaleDateString(),
    price: history.price
  }));

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="bg-white rounded-lg shadow-lg overflow-hidden">
        <div className="p-6">
          <h1 className="text-3xl font-bold mb-4">{listing.title}</h1>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <p className="text-gray-600 mb-4">{listing.location}</p>
              <div className="flex items-center space-x-4 mb-4">
                <span className="text-2xl font-bold">
                  ${listing.price_history[listing.price_history.length - 1]?.price.toLocaleString()}
                </span>
                <div className="flex items-center space-x-2 text-gray-600">
                  <span>{listing.bedrooms} beds</span>
                  <span>•</span>
                  <span>{listing.bathrooms} baths</span>
                  <span>•</span>
                  <span>{listing.area_sqft.toLocaleString()} sq ft</span>
                </div>
              </div>
              <p className="text-gray-700">{listing.description}</p>
            </div>
            
            <div className="h-80">
              <h2 className="text-xl font-semibold mb-4">Price History</h2>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={priceHistory}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="date"
                    angle={-45}
                    textAnchor="end"
                    height={60}
                  />
                  <YAxis 
                    tickFormatter={(value) => `$${value.toLocaleString()}`}
                  />
                  <Tooltip 
                    formatter={(value: number) => [`$${value.toLocaleString()}`, 'Price']}
                  />
                  <Line
                    type="monotone"
                    dataKey="price"
                    stroke="#2563eb"
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ListingDetailPage; 