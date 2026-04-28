import React, { useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import { Link } from 'react-router-dom';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { ApartmentSummary } from '../services/api';
import { CITY_HEX, DEFAULT_MARKER_HEX } from '../utils/cityColors';

// Fix webpack asset path issue for default Leaflet marker icons
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';
// eslint-disable-next-line @typescript-eslint/no-explicit-any
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({ iconRetinaUrl: markerIcon2x, iconUrl: markerIcon, shadowUrl: markerShadow });

/** Teardrop pin whose colour matches the city's theme. */
function cityIcon(city: string): L.DivIcon {
  const color = CITY_HEX[city] ?? DEFAULT_MARKER_HEX;
  return new L.DivIcon({
    className: '',
    html: `<div style="
      width:28px;height:28px;border-radius:50% 50% 50% 0;
      background:${color};border:2px solid #fff;
      box-shadow:0 2px 6px rgba(0,0,0,.35);
      transform:rotate(-45deg);
    "></div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 28],
    popupAnchor: [0, -30],
  });
}

const bedLabel = (min: number, max: number): string => {
  if (min === max) return min === 0 ? 'Studio' : `${min} bd`;
  const lo = min === 0 ? 'Studio' : `${min} bd`;
  return `${lo}–${max} bd`;
};

/** Re-centre the map whenever the displayed apartment list changes. */
const AutoBounds: React.FC<{ apts: ApartmentSummary[] }> = ({ apts }) => {
  const map = useMap();
  useEffect(() => {
    const pts = apts
      .filter(a => a.latitude != null && a.longitude != null)
      .map(a => [a.latitude!, a.longitude!] as [number, number]);
    if (pts.length > 0) {
      map.fitBounds(L.latLngBounds(pts), { padding: [40, 40], maxZoom: 14 });
    }
  }, [apts, map]);
  return null;
};

interface Props {
  apartments: ApartmentSummary[];
}

const MapView: React.FC<Props> = ({ apartments }) => {
  const mapped = apartments.filter(a => a.latitude != null && a.longitude != null);

  return (
    <div className="rounded-2xl overflow-hidden border border-slate-100 shadow-sm" style={{ height: '620px' }}>
      {mapped.length === 0 ? (
        <div className="h-full flex items-center justify-center bg-slate-50 text-slate-400 text-sm">
          No location data yet — coordinates are populated via the Google Maps import.
        </div>
      ) : (
        <MapContainer
          center={[37.45, -122.0]}
          zoom={10}
          style={{ height: '100%', width: '100%' }}
          scrollWheelZoom={true}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <AutoBounds apts={mapped} />
          {mapped.map(apt => (
            <Marker
              key={apt.id}
              position={[apt.latitude!, apt.longitude!]}
              icon={cityIcon(apt.city)}
            >
              <Popup minWidth={210}>
                <div className="py-1">
                  <p className="font-semibold text-slate-900 text-sm leading-snug mb-0.5">
                    {apt.title}
                  </p>
                  <p className="text-xs text-slate-500 mb-2">
                    {apt.city} · {bedLabel(apt.min_beds, apt.max_beds)}
                  </p>
                  <p className="text-base font-bold text-indigo-600 mb-3">
                    {apt.data_source_type === 'legal_block'
                      ? '🔒 Data restricted'
                      : apt.min_price != null
                        ? apt.min_price === apt.max_price
                          ? `$${apt.min_price.toLocaleString()}/mo`
                          : `$${apt.min_price.toLocaleString()} – $${apt.max_price!.toLocaleString()}/mo`
                        : 'Contact for pricing'}
                  </p>
                  <div className="flex items-center justify-between text-xs text-slate-400 mb-3">
                    <span>{apt.plan_count} plans</span>
                    <span>{apt.available_count}/{apt.plan_count} available</span>
                  </div>
                  <Link
                    to={`/listings/${apt.id}`}
                    className="block text-center text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-3 py-1.5 transition-colors"
                  >
                    View details →
                  </Link>
                </div>
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      )}
    </div>
  );
};

export default MapView;
