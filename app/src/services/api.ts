// In Docker (nginx proxy), use relative /api/v1 so the browser sends requests
// to the same origin and nginx forwards them to the backend container.
// In local dev (npm start), override with REACT_APP_API_URL=http://localhost:8000/api/v1
const API_BASE_URL = process.env.REACT_APP_API_URL || '/api/v1';
const USE_MOCK = process.env.REACT_APP_USE_MOCK === 'true';

// ---------------------------------------------------------------------------
// Backend response types (mirror backend/app/schemas/apartment.py)
// ---------------------------------------------------------------------------

export interface PlanPriceHistory {
  price: number;
  recorded_at: string;
}

export interface PlanResponse {
  id: number;
  apartment_id: number;
  name: string;
  bedrooms: number;
  bathrooms: number;
  area_sqft: number;
  price: number;
  available_from: string | null;
  is_available: boolean;
  price_history: PlanPriceHistory[];
  created_at: string;
  updated_at: string;
}

export interface ApartmentResponse {
  id: number;
  external_id: string | null;
  title: string;
  description: string | null;
  address: string | null;
  city: string;
  state: string;
  zipcode: string;
  latitude: number | null;
  longitude: number | null;
  property_type: string;
  has_parking: boolean | null;
  has_pool: boolean | null;
  has_gym: boolean | null;
  has_dishwasher: boolean | null;
  has_air_conditioning: boolean | null;
  has_washer_dryer: boolean | null;
  pets_allowed: boolean | null;
  is_available: boolean;
  source_url: string | null;
  plans: PlanResponse[];
  images: { url: string; caption: string | null; is_primary: boolean }[];
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Frontend display types (used by existing UI components)
// ---------------------------------------------------------------------------

export interface PriceHistory {
  price: number;
  recorded_at: string;
}

/** Flat shape consumed by ListingCard, ListingDetailPage, etc. */
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
  /** The full backend response, kept for detail pages that need plan data. */
  _raw?: ApartmentResponse;
  created_at: string;
  updated_at: string;
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

// ---------------------------------------------------------------------------
// Adapter: ApartmentResponse → Listing
// ---------------------------------------------------------------------------

function toListingShape(apt: ApartmentResponse): Listing {
  // Pick the cheapest available plan, falling back to the first plan.
  const availablePlans = apt.plans.filter(p => p.is_available);
  const representativePlan =
    availablePlans.length > 0
      ? availablePlans.reduce((a, b) => (a.price < b.price ? a : b))
      : apt.plans[0];

  const location = apt.address
    ? `${apt.address}, ${apt.city}, ${apt.state}`
    : `${apt.city}, ${apt.state}`;

  // Build price_history from the representative plan, or synthesise a single
  // data point from the plan's current price so the chart always has data.
  const price_history: PriceHistory[] =
    representativePlan && representativePlan.price_history.length > 0
      ? representativePlan.price_history.map(h => ({
          price: h.price,
          recorded_at: h.recorded_at,
        }))
      : representativePlan
      ? [{ price: representativePlan.price, recorded_at: apt.updated_at }]
      : [];

  return {
    id: apt.id,
    external_id: apt.external_id ?? '',
    title: apt.title,
    description: apt.description ?? '',
    location,
    bedrooms: representativePlan?.bedrooms ?? 0,
    bathrooms: representativePlan?.bathrooms ?? 0,
    area_sqft: representativePlan?.area_sqft ?? 0,
    price_history,
    _raw: apt,
    created_at: apt.created_at,
    updated_at: apt.updated_at,
  };
}

// ---------------------------------------------------------------------------
// HTTP helper
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') {
        url.searchParams.set(k, String(v));
      }
    });
  }
  const res = await fetch(url.toString());
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Mock fallback (only used when REACT_APP_USE_MOCK=true)
// ---------------------------------------------------------------------------

async function getMockListings(filters: ListingsFilter): Promise<Listing[]> {
  const { mockListings } = await import('./mockData');
  let results = [...mockListings];
  if (filters.location) {
    results = results.filter(l =>
      l.location.toLowerCase().includes(filters.location!.toLowerCase())
    );
  }
  if (filters.min_price) {
    results = results.filter(l => {
      const price = l.price_history[l.price_history.length - 1]?.price ?? 0;
      return price >= filters.min_price!;
    });
  }
  if (filters.max_price) {
    results = results.filter(l => {
      const price = l.price_history[l.price_history.length - 1]?.price ?? 0;
      return price <= filters.max_price!;
    });
  }
  if (filters.bedrooms) {
    results = results.filter(l => l.bedrooms >= filters.bedrooms!);
  }
  return results;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

const api = {
  async getListings(filters: ListingsFilter = {}): Promise<Listing[]> {
    if (USE_MOCK) {
      await new Promise(r => setTimeout(r, 300));
      return getMockListings(filters);
    }

    const params: Record<string, string | number | boolean | undefined> = {
      city: filters.location,
      min_price: filters.min_price,
      max_price: filters.max_price,
      min_bedrooms: filters.bedrooms,
      skip: filters.skip ?? 0,
      limit: filters.limit ?? 50,
    };
    const apts = await apiFetch<ApartmentResponse[]>('/apartments', params);
    return apts.map(toListingShape);
  },

  async getListing(id: number): Promise<Listing> {
    if (USE_MOCK) {
      await new Promise(r => setTimeout(r, 300));
      const { mockListings } = await import('./mockData');
      const listing = mockListings.find(l => l.id === id);
      if (!listing) throw new Error('Listing not found');
      return listing;
    }

    const apt = await apiFetch<ApartmentResponse>(`/apartments/${id}`);
    return toListingShape(apt);
  },

  async getPriceTrends(location?: string, days: number = 30): Promise<PriceTrend[]> {
    if (USE_MOCK) {
      await new Promise(r => setTimeout(r, 300));
      const { mockPriceTrends } = await import('./mockData');
      return mockPriceTrends;
    }

    const params: Record<string, string | number | boolean | undefined> = {
      city: location,
      days,
    };
    return apiFetch<PriceTrend[]>('/stats/price-trends', params);
  },
};

export default api;
