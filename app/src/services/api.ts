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
  external_url: string | null;
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
  id: number;           // apartment id
  plan_id: number;      // plan id (unique per row)
  external_id: string;
  title: string;
  plan_name: string;
  description: string;
  location: string;
  bedrooms: number;
  bathrooms: number;
  area_sqft: number | null;
  price_history: PriceHistory[];
  /** The full backend response, kept for detail pages that need plan data. */
  _raw?: ApartmentResponse;
  created_at: string;
  updated_at: string;
}

/** One card per apartment complex shown on the home page */
export interface ApartmentSummary {
  id: number;
  title: string;
  _isAffordableHousing?: boolean;
  location: string;
  city: string;
  source_url: string | null;
  plan_count: number;
  available_count: number;
  min_price: number | null;
  max_price: number | null;
  min_beds: number;
  max_beds: number;
  latitude: number | null;
  longitude: number | null;
  _raw: ApartmentResponse;
}

export interface PriceTrend {
  date: string;
  avg_price: number;
}

export interface SimilarApartment {
  id: number;
  title: string;
  city: string;
  location: string;
  source_url: string | null;
  latitude: number | null;
  longitude: number | null;
  min_price: number | null;
  max_price: number | null;
  min_beds: number;
  max_beds: number;
  plan_count: number;
  available_count: number;
}

export interface SimilarResponse {
  city_median_price: number | null;
  pct_vs_median: number | null;
  similar: SimilarApartment[];
}

// ---------------------------------------------------------------------------
// Auth types
// ---------------------------------------------------------------------------

export interface AuthToken {
  access_token: string;
  token_type: string;
}

export interface UserProfile {
  id: number;
  email: string;
  is_active: boolean;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Subscription types
// ---------------------------------------------------------------------------

export interface SubscriptionCreate {
  apartment_id?: number;
  plan_id?: number;
  city?: string;
  target_price?: number;
  price_drop_pct?: number;
  notify_email?: boolean;
}

export interface SubscriptionResponse {
  id: number;
  user_id: number;
  apartment_id: number | null;
  plan_id: number | null;
  city: string | null;
  target_price: number | null;
  price_drop_pct: number | null;
  baseline_price: number | null;
  baseline_recorded_at: string | null;
  notify_email: boolean;
  notify_telegram: boolean;
  is_active: boolean;
  last_notified_at: string | null;
  trigger_count: number;
  created_at: string;
  // Enriched fields (populated on list, null on create)
  apartment_title: string | null;
  apartment_city: string | null;
  plan_name: string | null;
  plan_spec: string | null;
  latest_price: number | null;
}

export type SortOption = 'price_asc' | 'price_desc' | 'updated_desc' | 'name_asc';

export interface ListingsFilter {
  location?: string;
  min_price?: number;
  max_price?: number;
  bedrooms?: number;
  skip?: number;
  limit?: number;
  sort?: SortOption;
  // Advanced filters
  pets_allowed?: boolean;
  has_parking?: boolean;
  min_sqft?: number;
  max_sqft?: number;
  available_before?: string; // ISO date string YYYY-MM-DD
}

const _AMI_PATTERN = /\bami\b|\d+%\s*ami|area median income|income.restricted|income.qualified|lihtc|section 8/i;
const _AFFORDABLE_TITLE_PATTERN = /housing authority|affordable housing|community development corp|habitat for humanity|public housing/i;

function aptToSummary(apt: ApartmentResponse): ApartmentSummary {
  // Use all plans (not just available) for price range — available plans may all be
  // waitlisted/unavailable even though prices are known (e.g. affordable housing).
  const pricedPlans = apt.plans.filter(p => p.price != null && p.price > 0);
  const prices = pricedPlans.map(p => p.price as number);
  const beds = apt.plans.map(p => p.bedrooms);
  const location = apt.address
    ? `${apt.address}, ${apt.city}, ${apt.state}`
    : `${apt.city}, ${apt.state}`;
  const availableCount = apt.plans.filter(p => p.is_available).length;

  // Detect affordable / income-restricted housing by plan names or apartment title
  const isAffordableHousing =
    _AFFORDABLE_TITLE_PATTERN.test(apt.title) ||
    apt.plans.some(p => _AMI_PATTERN.test(p.name));

  return {
    id: apt.id,
    title: apt.title,
    location,
    city: apt.city,
    source_url: apt.source_url,
    plan_count: apt.plans.length,
    available_count: availableCount,
    min_price: prices.length ? Math.min(...prices) : null,
    max_price: prices.length ? Math.max(...prices) : null,
    min_beds: beds.length ? Math.min(...beds) : 0,
    max_beds: beds.length ? Math.max(...beds) : 0,
    latitude: (apt as any).latitude ?? null,
    longitude: (apt as any).longitude ?? null,
    _raw: apt,
    _isAffordableHousing: isAffordableHousing,
  };
}

// ---------------------------------------------------------------------------
// Adapter: ApartmentResponse → Listing
// ---------------------------------------------------------------------------

/** Expand one apartment into one Listing per available plan. */
function aptToListings(apt: ApartmentResponse): Listing[] {
  const location = apt.address
    ? `${apt.address}, ${apt.city}, ${apt.state}`
    : `${apt.city}, ${apt.state}`;

  const plans = apt.plans.filter(p => p.is_available && p.price > 0);
  // If no available plans, show one placeholder card for the apartment
  if (plans.length === 0) return [];

  return plans.map(plan => {
    const price_history: PriceHistory[] =
      plan.price_history.length > 0
        ? plan.price_history.map(h => ({ price: h.price, recorded_at: h.recorded_at }))
        : [{ price: plan.price, recorded_at: apt.updated_at }];

    return {
      id: apt.id,
      plan_id: plan.id,
      external_id: apt.external_id ?? '',
      title: apt.title,
      plan_name: plan.name,
      description: apt.description ?? '',
      location,
      bedrooms: plan.bedrooms,
      bathrooms: plan.bathrooms,
      area_sqft: plan.area_sqft ?? null,
      price_history,
      _raw: apt,
      created_at: apt.created_at,
      updated_at: apt.updated_at,
    };
  });
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
  async getApartments(filters: ListingsFilter = {}): Promise<ApartmentSummary[]> {
    const params = {
      city: filters.location,
      min_price: filters.min_price,
      max_price: filters.max_price,
      min_bedrooms: filters.bedrooms,
      skip: filters.skip ?? 0,
      limit: filters.limit ?? 100,
      sort: filters.sort ?? 'price_asc',
      pets_allowed: filters.pets_allowed,
      has_parking: filters.has_parking,
      min_sqft: filters.min_sqft,
      max_sqft: filters.max_sqft,
      available_before: filters.available_before,
    };
    const apts = await apiFetch<ApartmentResponse[]>('/apartments', params);
    return apts.map(aptToSummary).filter(a => a.plan_count > 0 && !a._isAffordableHousing);
  },

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
    return apts.flatMap(aptToListings);
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
    const listings = aptToListings(apt);
    if (listings.length > 0) return listings[0];
    // Apartment has no available plans — return a shell listing so the detail
    // page can still render the name, location, and floor-plan table.
    const location = apt.address
      ? `${apt.address}, ${apt.city}, ${apt.state}`
      : `${apt.city}, ${apt.state}`;
    return {
      id: apt.id,
      plan_id: -1,
      external_id: apt.external_id ?? '',
      title: apt.title,
      plan_name: '',
      description: apt.description ?? '',
      location,
      bedrooms: 0,
      bathrooms: 0,
      area_sqft: null,
      price_history: [],
      _raw: apt,
      created_at: apt.created_at,
      updated_at: apt.updated_at,
    };
  },

  // -------------------------------------------------------------------------
  // Auth
  // -------------------------------------------------------------------------

  async register(email: string, password: string): Promise<AuthToken> {
    const res = await fetch(`${API_BASE_URL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`${res.status}: ${text}`);
    }
    return res.json();
  },

  async login(email: string, password: string): Promise<AuthToken> {
    const body = new URLSearchParams({ username: email, password });
    const res = await fetch(`${API_BASE_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`${res.status}: ${text}`);
    }
    return res.json();
  },

  async getMe(token: string): Promise<UserProfile> {
    const res = await fetch(`${API_BASE_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Not authenticated');
    return res.json();
  },

  // -------------------------------------------------------------------------
  // Subscriptions
  // -------------------------------------------------------------------------

  async getSubscriptions(token: string): Promise<SubscriptionResponse[]> {
    const res = await fetch(`${API_BASE_URL}/subscriptions`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to load subscriptions');
    return res.json();
  },

  async createSubscription(token: string, payload: SubscriptionCreate): Promise<SubscriptionResponse> {
    const res = await fetch(`${API_BASE_URL}/subscriptions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`${res.status}: ${text}`);
    }
    return res.json();
  },

  async updateSubscription(token: string, subId: number, patch: Partial<SubscriptionCreate> & { is_active?: boolean }): Promise<SubscriptionResponse> {
    const res = await fetch(`${API_BASE_URL}/subscriptions/${subId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(patch),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`${res.status}: ${text}`);
    }
    return res.json();
  },

  async deleteSubscription(token: string, subId: number): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/subscriptions/${subId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to delete subscription');
  },

  async getFavorites(token: string): Promise<number[]> {
    const res = await fetch(`${API_BASE_URL}/favorites`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to load favorites');
    return res.json();
  },

  async addFavorite(token: string, apartmentId: number): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/favorites/${apartmentId}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to add favorite');
  },

  async removeFavorite(token: string, apartmentId: number): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/favorites/${apartmentId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to remove favorite');
  },

  async getSimilarApartments(id: number): Promise<SimilarResponse> {
    return apiFetch<SimilarResponse>(`/apartments/${id}/similar`);
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
