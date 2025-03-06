export const mockListings = [
  {
    id: 1,
    external_id: "apt-001",
    title: "Luxury Downtown Apartment",
    description: "Modern 2-bed apartment with city views and updated amenities",
    location: "Downtown Seattle",
    bedrooms: 2,
    bathrooms: 2,
    area_sqft: 1200,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-02-15T00:00:00Z",
    price_history: [
      { price: 2800, recorded_at: "2024-01-01T00:00:00Z" },
      { price: 2850, recorded_at: "2024-01-15T00:00:00Z" },
      { price: 2900, recorded_at: "2024-02-01T00:00:00Z" },
      { price: 2875, recorded_at: "2024-02-15T00:00:00Z" }
    ]
  },
  {
    id: 2,
    external_id: "apt-002",
    title: "Cozy Capitol Hill Studio",
    description: "Charming studio in historic building, walking distance to restaurants",
    location: "Capitol Hill",
    bedrooms: 0,
    bathrooms: 1,
    area_sqft: 500,
    created_at: "2024-01-05T00:00:00Z",
    updated_at: "2024-02-15T00:00:00Z",
    price_history: [
      { price: 1600, recorded_at: "2024-01-05T00:00:00Z" },
      { price: 1650, recorded_at: "2024-01-20T00:00:00Z" },
      { price: 1625, recorded_at: "2024-02-15T00:00:00Z" }
    ]
  },
  {
    id: 3,
    external_id: "apt-003",
    title: "Spacious Ballard 3-Bedroom",
    description: "Family-friendly apartment with private balcony and parking",
    location: "Ballard",
    bedrooms: 3,
    bathrooms: 2,
    area_sqft: 1500,
    created_at: "2024-01-10T00:00:00Z",
    updated_at: "2024-02-15T00:00:00Z",
    price_history: [
      { price: 3200, recorded_at: "2024-01-10T00:00:00Z" },
      { price: 3300, recorded_at: "2024-01-25T00:00:00Z" },
      { price: 3250, recorded_at: "2024-02-10T00:00:00Z" },
      { price: 3400, recorded_at: "2024-02-15T00:00:00Z" }
    ]
  }
];

export const mockPriceTrends = [
  { date: "2024-01-01", avg_price: 2500 },
  { date: "2024-01-15", avg_price: 2600 },
  { date: "2024-02-01", avg_price: 2550 },
  { date: "2024-02-15", avg_price: 2650 }
]; 