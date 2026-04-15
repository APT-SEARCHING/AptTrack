import React from 'react';
import { Link } from 'react-router-dom';
import { Listing } from '../services/api';

interface Props {
  listing: Listing;
}

const CITY_COLORS: Record<string, string> = {
  'San Jose':      'bg-violet-50 text-violet-700',
  'San Francisco': 'bg-sky-50 text-sky-700',
  'Oakland':       'bg-amber-50 text-amber-700',
  'Palo Alto':     'bg-emerald-50 text-emerald-700',
  'Fremont':       'bg-rose-50 text-rose-700',
  'Hayward':       'bg-orange-50 text-orange-700',
};

const cityColor = (location: string) => {
  for (const [city, cls] of Object.entries(CITY_COLORS)) {
    if (location.includes(city)) return cls;
  }
  return 'bg-slate-100 text-slate-600';
};

const bedLabel = (beds: number) =>
  beds === 0 ? 'Studio' : `${beds} bd`;

const ListingCard: React.FC<Props> = ({ listing }) => {
  const price = listing.price_history[listing.price_history.length - 1]?.price;
  const prevPrice = listing.price_history.length > 1
    ? listing.price_history[listing.price_history.length - 2].price
    : null;
  const priceDrop = prevPrice && price < prevPrice;

  return (
    <Link to={`/listings/${listing.id}`} className="block group">
      <div className="card group-hover:border-indigo-200 p-5 flex flex-col gap-3">

        {/* Top row: city badge + plan tag */}
        <div className="flex items-center justify-between">
          <span className={`badge ${cityColor(listing.location)}`}>
            {listing.location.split(',')[0]}
          </span>
          <span className="badge bg-slate-100 text-slate-500 font-mono">
            {listing.plan_name}
          </span>
        </div>

        {/* Title */}
        <div>
          <h2 className="font-semibold text-slate-900 text-base leading-snug group-hover:text-indigo-700 transition-colors">
            {listing.title}
          </h2>
          <p className="text-xs text-slate-400 mt-0.5 truncate">{listing.location}</p>
        </div>

        {/* Price */}
        <div className="flex items-end gap-2">
          <span className="text-2xl font-bold text-slate-900">
            ${price?.toLocaleString()}
          </span>
          <span className="text-slate-400 text-sm mb-0.5">/mo</span>
          {priceDrop && (
            <span className="badge bg-emerald-100 text-emerald-700 ml-auto">
              ↓ Price drop
            </span>
          )}
        </div>

        {/* Specs */}
        <div className="flex items-center gap-3 text-sm text-slate-500 border-t border-slate-50 pt-3">
          <span className="flex items-center gap-1">
            <span>🛏</span> {bedLabel(listing.bedrooms)}
          </span>
          <span className="text-slate-300">|</span>
          <span className="flex items-center gap-1">
            <span>🚿</span> {listing.bathrooms} ba
          </span>
          {listing.area_sqft && (
            <>
              <span className="text-slate-300">|</span>
              <span>{listing.area_sqft.toLocaleString()} sqft</span>
            </>
          )}
        </div>
      </div>
    </Link>
  );
};

export default ListingCard;
