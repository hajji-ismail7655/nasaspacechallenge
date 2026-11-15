const API = String(window.ANALOG_API || 'http://localhost:8000').replace(/\/$/, '');

const DOMAINS = [
  'topography',
  'mineralogy',
  'thermal_illumination',
  'granular_aeolian',
  'volatiles_subsurface',
];

async function getJson(path) {
  const response = await fetch(`${API}${path}`);
  if (!response.ok) {
    throw new Error(`Backend request failed (${response.status}): ${path}`);
  }
  return response.json();
}

function lonDelta(a, b) {
  return ((((a - b) + 540) % 360) - 180);
}

function distanceKm(a, b) {
  const rad = Math.PI / 180;
  const lat1 = a.lat * rad;
  const lat2 = b.lat * rad;
  const dLat = (b.lat - a.lat) * rad;
  const dLon = lonDelta(b.lon, a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2
    + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(Math.max(0, 1 - h)));
}

function areaCenter(area) {
  const { south, north, west, east } = area.bounds;
  const span = west <= east ? east - west : east + 360 - west;
  const lon = ((((west + span / 2) + 180) % 360) + 360) % 360 - 180;
  return { lat: (south + north) / 2, lon };
}

function contains(area, point) {
  const { south, north, west, east } = area.bounds;
  const lonInRange = west <= east
    ? point.lon >= west && point.lon <= east
    : point.lon >= west || point.lon <= east;
  return point.lat >= south && point.lat <= north && lonInRange;
}

function selectionPoint(selection) {
  if (selection?.point) return selection.point;
  if (selection?.type === 'point') return { lat: selection.lat, lon: selection.lon };
  if (selection?.area) return areaCenter(selection.area);
  if (selection?.type === 'area') return areaCenter(selection.area);
  return null;
}

async function candidatesForBody(body) {
  const { targets = [] } = await getJson('/targets');
  const bodyTargets = targets.filter((id) => id.startsWith(`${body}_`));
  if (!bodyTargets.length) throw new Error(`The backend has no ${body} targets.`);

  const groups = await Promise.all(bodyTargets.map(async (targetId) => {
    const { sites = [] } = await getJson(`/api/discoveries?target_id=${encodeURIComponent(targetId)}`);
    return sites.map((site) => ({ ...site, target_id: site.target_id || targetId }));
  }));
  return groups.flat();
}

function pickCandidate(sites, selection) {
  const point = selectionPoint(selection);
  if (!point) throw new Error('Choose a point or area before requesting a comparison.');

  let pool = sites;
  const area = selection?.area || (selection?.type === 'area' ? selection.area : null);
  if (area) {
    pool = sites.filter((site) => {
      const p = site.coordinates || site;
      return Number.isFinite(p.lat) && Number.isFinite(p.lon) && contains(area, p);
    });
    if (!pool.length) throw new Error('No precomputed Earth discovery falls inside the selected area.');
  }
  if (!pool.length) throw new Error('The backend has no discovery results yet. Run the discovery sweep first.');

  return pool
    .map((site) => {
      const p = site.coordinates || site;
      return { site, distance: distanceKm(point, { lat: Number(p.lat), lon: Number(p.lon) }) };
    })
    .filter((entry) => Number.isFinite(entry.distance))
    .sort((a, b) => a.distance - b.distance)[0] || null;
}

function normalizedScore(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return Math.max(0, Math.min(100, n <= 1 ? n * 100 : n));
}

/*
 * The backend stores precomputed Earth-site matches for each Moon/Mars target.
 * A point selection uses the nearest saved discovery; an area selection only
 * uses discoveries whose coordinates fall inside that area. Scores stay tied
 * to that actual discovery result instead of being fabricated for arbitrary
 * coordinates.
 */
export async function getComparison({ body, selection }) {
  const sites = await candidatesForBody(body);
  const picked = pickCandidate(sites, selection);
  if (!picked) throw new Error('No backend discovery has usable coordinates.');

  const { site, distance } = picked;
  const [detail] = await Promise.all([
    getJson(`/breakdown/${encodeURIComponent(site.site_id)}?target_id=${encodeURIComponent(site.target_id)}`)
      .catch(() => null),
  ]);
  const dossier = detail?.breakdown && typeof detail.breakdown === 'object'
    ? detail.breakdown
    : {};
  const domainScores = site.domain_scores || dossier.domain_scores || {};
  const residuals = dossier.channel_residuals || {};
  const flags = Array.isArray(dossier.physical_breakdown_flags) ? dossier.physical_breakdown_flags : [];

  const scores = Object.fromEntries(DOMAINS.map((domain) => [domain, normalizedScore(domainScores[domain])]));
  const texts = Object.fromEntries(DOMAINS.map((domain) => {
    const score = scores[domain];
    const residualCount = Object.keys(residuals).filter((key) => key.startsWith(`${domain}.`)).length;
    const value = score == null
      ? 'The discovery result has no score for this domain.'
      : `Backend ${domain.replaceAll('_', ' ')} similarity: ${score.toFixed(1)}%. `
        + `Using Earth site ${site.site_id} (${distance.toFixed(1)} km from the selected point/area center) `
        + `for ${site.target_id}; ${residualCount} channel residuals and ${flags.length} physical flags are available.`;
    return [domain, value];
  }));

  return { scores, texts, thermal: null };
}
