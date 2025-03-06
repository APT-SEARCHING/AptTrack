import React from 'react';
import { Link } from 'react-router-dom';
import { Listing } from '../services/api';

interface Props {
  listing: Listing;
}

const ListingCard: React.FC<Props> = ({ listing }) => {
  const currentPrice = listing.price_history[listing.price_history.length - 1]?.price;
  
  return (
    <Link to={`/listings/${listing.id}`}>
      <div className="border rounded-lg shadow-lg hover:shadow-xl transition-shadow">
        <div className="p-4">
          <h2 className="text-xl font-semibold mb-2">{listing.title}</h2>
          <p className="text-gray-600 mb-2">{listing.location}</p>
          
          <div className="flex justify-between items-center mb-4">
            <span className="text-2xl font-bold">${currentPrice?.toLocaleString()}</span>
            <div className="flex items-center space-x-2">
              <span>{listing.bedrooms} beds</span>
              <span>•</span>
              <span>{listing.bathrooms} baths</span>
            </div>
          </div>
          
          <p className="text-gray-500 text-sm">
            {listing.area_sqft.toLocaleString()} sq ft
          </p>
        </div>
      </div>
    </Link>
  );
};

export default ListingCard; 