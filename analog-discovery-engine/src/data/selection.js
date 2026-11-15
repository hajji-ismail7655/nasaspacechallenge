/* Selection model shared by the 3D globe and the 2D map.
   Longitude -180..180 (east +), latitude -90..90 (north +). Both views map the texture UV directly,
   so a point picked on the globe is the same point on the map. */
export const EMPTY_SELECTION = { point: null, area: null };

export const hasSelection = (s) => !!(s && (s.point || s.area));

export const toVec = (lat, lon) => {
  const phi = ((lon + 180) / 360) * Math.PI * 2;
  const theta = (1 - (lat + 90) / 180) * Math.PI;
  return [-Math.cos(phi) * Math.sin(theta), Math.cos(theta), Math.sin(phi) * Math.sin(theta)];
};

export const angleDeg = (a, b) => {
  const d = Math.max(-1, Math.min(1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]));
  return (Math.acos(d) * 180) / Math.PI;
};

const wrap = (lon) => ((((lon + 180) % 360) + 360) % 360) - 180;

export const capBounds = (lat, lon, r) => {
  const south = Math.max(-90, lat - r), north = Math.min(90, lat + r);
  if (lat + r >= 90 || lat - r <= -90) return { south, west: -180, north, east: 180 };
  const d = r / Math.cos((lat * Math.PI) / 180);
  if (d >= 180) return { south, west: -180, north, east: 180 };
  return { south, west: wrap(lon - d), north, east: wrap(lon + d) }; // west > east means it crosses the antimeridian
};

export const makeCap = (center, radiusDeg) => ({ shape: 'cap', center, radiusDeg, bounds: capBounds(center.lat, center.lon, radiusDeg) });

export const makeRect = (a, b) => ({
  shape: 'rect',
  bounds: { south: Math.min(a.lat, b.lat), north: Math.max(a.lat, b.lat), west: Math.min(a.lon, b.lon), east: Math.max(a.lon, b.lon) },
});

/* Shape expected by src/data/provider.js getComparison({ body, selection }). */
export const toProviderSelection = ({ point, area }) => {
  if (point && area) return { type: 'both', point, area };
  if (point) return { type: 'point', lat: point.lat, lon: point.lon };
  return { type: 'area', area };
};

const f = (n) => `${Math.abs(n).toFixed(2)}°`;
export const fmtLat = (lat) => `${f(lat)} ${lat >= 0 ? 'N' : 'S'}`;
export const fmtLon = (lon) => `${f(lon)} ${lon >= 0 ? 'E' : 'W'}`;

export const saveSelection = (body, mode, selection) => {
  try { sessionStorage.setItem('ade.selection', JSON.stringify({ body, mode, selection })); } catch {}
};
export const loadSelection = () => {
  try { return JSON.parse(sessionStorage.getItem('ade.selection')); } catch { return null; }
};
