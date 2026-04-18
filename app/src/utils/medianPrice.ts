import { ApartmentSummary } from '../services/api';

/**
 * Median of per-apartment midpoints ((min_price + max_price) / 2).
 * Apartments with a null price on either end are excluded.
 * Returns 0 for an empty or all-null input.
 */
export function medianApartmentPrice(apts: Pick<ApartmentSummary, 'min_price' | 'max_price'>[]): number {
  const midpoints = apts
    .filter(a => a.min_price != null && a.max_price != null)
    .map(a => (a.min_price! + a.max_price!) / 2)
    .sort((a, b) => a - b);
  if (!midpoints.length) return 0;
  const mid = Math.floor(midpoints.length / 2);
  return midpoints.length % 2 === 1
    ? midpoints[mid]
    : (midpoints[mid - 1] + midpoints[mid]) / 2;
}
