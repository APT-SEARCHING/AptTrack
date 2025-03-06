import { mockListings, mockPriceTrends } from './mockData';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api/v1';

export interface Listing {
  id: number;
  external_id: string;
  title: string;
  description: string;
  location: string;
  bedrooms: number;
  bathrooms: number;
  area_sqft: number;
  price_history: PriceHistory[];
  created_at: string;
  updated_at: string;
}

export interface PriceHistory {
  price: number;
  recorded_at: string;
}

export interface PriceTrend {
  date: string;
  avg_price: number;
}

export interface ListingsFilter {
  location?: string;
  min_price?: number;
  max_price?: number;
  bedrooms?: number;
  skip?: number;
  limit?: number;
}

const api = {
  async getListings(filters: ListingsFilter = {}): Promise<Listing[]> {
    // Simulate API delay
    await new Promise(resolve => setTimeout(resolve, 500));
    
    let filteredListings = [...mockListings];
    
    if (filters.location) {
      filteredListings = filteredListings.filter(listing => 
        listing.location.toLowerCase().includes(filters.location!.toLowerCase())
      );
    }
    
    if (filters.min_price) {
      filteredListings = filteredListings.filter(listing => {
        const currentPrice = listing.price_history[listing.price_history.length - 1].price;
        return currentPrice >= filters.min_price!;
      });
    }
    
    if (filters.max_price) {
      filteredListings = filteredListings.filter(listing => {
        const currentPrice = listing.price_history[listing.price_history.length - 1].price;
        return currentPrice <= filters.max_price!;
      });
    }
    
    if (filters.bedrooms) {
      filteredListings = filteredListings.filter(listing => 
        listing.bedrooms >= filters.bedrooms!
      );
    }
    
    return filteredListings;
  },

  async getListing(id: number): Promise<Listing> {
    await new Promise(resolve => setTimeout(resolve, 500));
    const listing = mockListings.find(l => l.id === id);
    if (!listing) {
      throw new Error('Listing not found');
    }
    return listing;
  },

  async getPriceTrends(location?: string, days: number = 30): Promise<PriceTrend[]> {
    await new Promise(resolve => setTimeout(resolve, 500));
    return mockPriceTrends;
  }
};

export default api; 