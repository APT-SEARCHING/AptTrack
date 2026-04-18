import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import api, { ApartmentSummary } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { ApartmentCard } from './ListingsPage';

const FavoritesPage: React.FC = () => {
  const { token, favoriteIds, isFavorite, toggleFavorite } = useAuth();
  const [apts, setApts] = useState<ApartmentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) { setLoading(false); return; }
    const ids = Array.from(favoriteIds);
    if (ids.length === 0) { setApts([]); setLoading(false); return; }

    setLoading(true);
    // Fetch all apartments and filter to favorited ones
    api.getApartments({ limit: 500 })
      .then(all => {
        const favSet = new Set(ids);
        const favApts = all.filter(a => favSet.has(a.id));
        // Preserve order: most-recently-favorited first (ids is desc from API)
        favApts.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id));
        setApts(favApts);
      })
      .catch(err => setError(String(err)))
      .finally(() => setLoading(false));
  }, [token, favoriteIds]);

  if (!token) {
    return (
      <div className="max-w-xl mx-auto px-4 py-24 text-center">
        <p className="text-5xl mb-4">♥</p>
        <p className="text-xl font-semibold text-slate-800 mb-2">Sign in to see your saved apartments</p>
        <p className="text-slate-500 text-sm">Click the heart on any listing to save it here.</p>
        <Link to="/" className="inline-block mt-6 text-indigo-600 hover:underline text-sm">← Browse listings</Link>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Link to="/" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-indigo-600 mb-6 transition-colors">
        ← All listings
      </Link>

      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Saved</h1>
          <p className="text-slate-500 text-sm mt-1">{favoriteIds.size} apartment{favoriteIds.size !== 1 ? 's' : ''}</p>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="bg-white rounded-2xl border border-slate-100 p-5 animate-pulse">
              <div className="h-4 bg-slate-100 rounded w-1/3 mb-3" />
              <div className="h-6 bg-slate-100 rounded w-2/3 mb-2" />
              <div className="h-4 bg-slate-100 rounded w-full mb-4" />
              <div className="h-8 bg-slate-100 rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">{error}</div>
      ) : apts.length === 0 ? (
        <div className="text-center py-20 text-slate-400">
          <p className="text-5xl mb-4">♡</p>
          <p className="text-lg font-medium text-slate-600">No saved apartments yet</p>
          <p className="text-sm mt-1">Click the heart on any listing to save it here.</p>
          <Link to="/" className="inline-block mt-4 text-indigo-600 hover:underline text-sm">Browse listings →</Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {apts.map(apt => (
            <ApartmentCard
              key={apt.id}
              apt={apt}
              favorited={isFavorite(apt.id)}
              onFavoriteClick={e => {
                e.preventDefault();
                const removing = isFavorite(apt.id);
                toggleFavorite(apt.id);
                toast(removing ? 'Removed from saved' : 'Saved ♥');
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default FavoritesPage;
