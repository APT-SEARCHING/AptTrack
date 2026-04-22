import React, { useState } from 'react';
import { Routes, Route, Link } from 'react-router-dom';
import { Toaster, toast } from 'sonner';
import ListingsPage from './pages/ListingsPage';
import ListingDetailPage from './pages/ListingDetailPage';
import AlertsPage from './pages/AlertsPage';
import FavoritesPage from './pages/FavoritesPage';
import UnsubscribePage from './pages/UnsubscribePage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import AuthModal from './components/AuthModal';
import { AuthProvider, useAuth } from './context/AuthContext';

const NavActions: React.FC = () => {
  const { user, logout, activeAlertsCount } = useAuth();
  const [showAuth, setShowAuth] = useState(false);

  if (user) {
    return (
      <div className="flex items-center gap-3 text-sm">
        <Link
          to="/favorites"
          className="flex items-center gap-1.5 text-slate-300 hover:text-white transition-colors"
        >
          <span>♥</span>
          <span className="hidden sm:inline">Saved</span>
        </Link>
        <Link
          to="/alerts"
          className="flex items-center gap-1.5 text-slate-300 hover:text-white transition-colors"
        >
          <span className="relative">
            🔔
            {activeAlertsCount > 0 && (
              <span
                key={activeAlertsCount}
                className="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center px-0.5 leading-none animate-bounce"
                style={{ animationIterationCount: 3, animationDuration: '0.4s' }}
              >
                {activeAlertsCount > 99 ? '99+' : activeAlertsCount}
              </span>
            )}
          </span>
          <span className="hidden sm:inline">My Alerts</span>
        </Link>
        <span className="text-slate-600 hidden sm:inline">|</span>
        <span className="text-slate-400 hidden sm:inline truncate max-w-[160px]">{user.email}</span>
        <button
          onClick={() => { logout(); toast('Signed out'); }}
          className="text-slate-400 hover:text-white transition-colors"
        >
          Sign out
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="flex items-center gap-3 text-sm">
        <span className="text-slate-400 hidden sm:inline">Live rental data</span>
        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse inline-block" />
        <button
          onClick={() => setShowAuth(true)}
          className="text-slate-300 hover:text-white transition-colors font-medium"
        >
          Sign in
        </button>
        <button
          onClick={() => setShowAuth(true)}
          className="bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors"
        >
          Register
        </button>
      </div>
      {showAuth && (
        <AuthModal
          onClose={() => setShowAuth(false)}
          onSuccess={() => setShowAuth(false)}
        />
      )}
    </>
  );
};

const Nav: React.FC = () => (
  <header className="bg-slate-900 text-white sticky top-0 z-50 shadow-lg">
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
      <Link to="/" className="flex items-center gap-2 font-bold text-lg tracking-tight">
        <span className="text-indigo-400 text-xl">⌂</span>
        <span>AptTrack</span>
        <span className="text-slate-400 font-normal text-sm hidden sm:inline">Bay Area</span>
      </Link>
      <NavActions />
    </div>
  </header>
);

const App: React.FC = () => (
  <AuthProvider>
    <Toaster
      position="bottom-right"
      richColors
      toastOptions={{ style: { borderRadius: '12px', fontFamily: 'inherit' } }}
    />
    <div className="min-h-screen flex flex-col">
      <Nav />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<ListingsPage />} />
          <Route path="/listings/:id" element={<ListingDetailPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/favorites" element={<FavoritesPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/unsubscribe/all/:token" element={<UnsubscribePage variant="all" />} />
          <Route path="/unsubscribe/:token" element={<UnsubscribePage variant="one" />} />
        </Routes>
      </main>
      <footer className="bg-slate-900 text-slate-500 text-xs text-center py-4 mt-12">
        AptTrack · Public rental data only · Updated daily
      </footer>
    </div>
  </AuthProvider>
);

export default App;
