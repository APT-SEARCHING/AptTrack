/** Tailwind class sets — used by React UI components (cards, badges). */
export const CITY_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  'San Jose':      { bg: 'bg-violet-50',  text: 'text-violet-700',  dot: 'bg-violet-400' },
  'San Francisco': { bg: 'bg-sky-50',     text: 'text-sky-700',     dot: 'bg-sky-400' },
  'Oakland':       { bg: 'bg-amber-50',   text: 'text-amber-700',   dot: 'bg-amber-400' },
  'Palo Alto':     { bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-400' },
  'Fremont':       { bg: 'bg-rose-50',    text: 'text-rose-700',    dot: 'bg-rose-400' },
  'Hayward':       { bg: 'bg-orange-50',  text: 'text-orange-700',  dot: 'bg-orange-400' },
};

export const cityStyle = (city: string) =>
  CITY_COLORS[city] ?? { bg: 'bg-slate-100', text: 'text-slate-600', dot: 'bg-slate-400' };

/**
 * Hex equivalents of the Tailwind *-400 dot shades — used by Leaflet DivIcon
 * (which needs real CSS values, not class names).
 */
export const CITY_HEX: Record<string, string> = {
  'San Jose':      '#a78bfa', // violet-400
  'San Francisco': '#38bdf8', // sky-400
  'Oakland':       '#fbbf24', // amber-400
  'Palo Alto':     '#34d399', // emerald-400
  'Fremont':       '#fb7185', // rose-400
  'Hayward':       '#fb923c', // orange-400
};

/** Indigo-500 — fallback for cities not in the table. */
export const DEFAULT_MARKER_HEX = '#6366f1';
