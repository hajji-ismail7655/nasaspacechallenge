const API = String(import.meta.env?.VITE_API_BASE_URL || globalThis.window?.ANALOG_API || 'http://localhost:8000').replace(/\/$/, '');

const DOMAINS = [
  'topography',
  'mineralogy',
  'thermal_illumination',
  'granular_aeolian',
  'volatiles_subsurface',
];

async function getJson(path) {
  const response = await fetch(`${API}${path}`);
  if (!response.ok) throw new Error(`Backend request failed (${response.status}): ${path}`);
  return response.json();
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

function normalizedScore(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return Math.max(0, Math.min(100, n <= 1 ? n * 100 : n));
}

/* Sweep rows are target-level; arbitrary picker coordinates are not scored. */
export async function getComparison({ body, selection }) {
  if (!selection || (!selection.point && !selection.area && selection.type !== 'point' && selection.type !== 'area')) {
    throw new Error('Choose a point or area before requesting a comparison.');
  }
  const sites = await candidatesForBody(body);
  if (!sites.length) throw new Error('The backend has no discovery results yet. Run the discovery sweep first.');
  const site = [...sites].sort((a, b) =>
    Number(b.novel_composite_score ?? b.composite_score ?? b.composite ?? 0)
      - Number(a.novel_composite_score ?? a.composite_score ?? a.composite ?? 0),
  )[0];
  if (!site?.site_id) throw new Error('The backend discovery row has no site identifier.');

  const detail = await getJson(`/breakdown/${encodeURIComponent(site.site_id)}?target_id=${encodeURIComponent(site.target_id)}`)
    .catch(() => null);
  const dossier = detail?.breakdown && typeof detail.breakdown === 'object' ? detail.breakdown : {};
  const domainScores = site.domain_scores || dossier.domain_scores || {};
  const residuals = dossier.channel_residuals || {};
  const flags = Array.isArray(dossier.physical_breakdown_flags) ? dossier.physical_breakdown_flags : [];
  const scores = Object.fromEntries(DOMAINS.map((domain) => [domain, normalizedScore(domainScores[domain])]));
  const composite = normalizedScore(site.novel_composite_score ?? site.composite_score ?? site.composite);
  const texts = Object.fromEntries(DOMAINS.map((domain) => {
    const score = scores[domain];
    const residualCount = Object.keys(residuals).filter((key) => key.startsWith(`${domain}.`)).length;
    const value = score == null
      ? 'The stored discovery result has no score for this domain.'
      : `Stored ${domain.replaceAll('_', ' ')} similarity: ${score.toFixed(1)}%. `
        + `This is the top ranked Earth site (${site.site_id}) for fixed target ${site.target_id}`
        + `${composite == null ? '' : `; composite score ${composite.toFixed(1)}%`}. `
        + `The selected ${body} coordinates are visual context; arbitrary points are not scored by this precomputed sweep. `
        + `${residualCount} channel residuals and ${flags.length} physical flags are available.`;
    return [domain, value];
  }));
  return { scores, texts, thermal: null };
}
