import React from 'react';
import { Routes, Route } from 'react-router-dom';
import ListingsPage from './pages/ListingsPage';
import ListingDetailPage from './pages/ListingDetailPage';

const App: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<ListingsPage />} />
      <Route path="/listings/:id" element={<ListingDetailPage />} />
    </Routes>
  );
};

export default App; 