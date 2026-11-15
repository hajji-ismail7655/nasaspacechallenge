/* Thermal engine. Thermal colour = ACCURACY, and the user's weights change it.
   accuracy(p) = sum(w_i * q_i(p)) / sum(w_i), q_i in 0..1.
   PREVIEW DATA: until the backend supplies real per-characteristic values, q_i comes from smooth
   deterministic fields (seamless on a sphere). To plug real data in, replace `fieldAt` only. */
import { toVec, angleDeg } from './selection.js';
import { CHARACTERISTICS } from './characteristics.js';

export const W = 256, H = 128; // thermal grid, equirectangular 2:1 (same layout as the textures)
export const DATA_SOURCE = 'Preview data (backend not connected)';

const rng = (seed) => () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
const WAVES = {};
const waves = (body, id) => {
  const key = body + id;
  if (!WAVES[key]) {
    let s = 7; for (const ch of key) s = (s * 31 + ch.charCodeAt(0)) >>> 0;
    const r = rng(s);
    WAVES[key] = Array.from({ length: 6 }, () => {
      const d = [r() * 2 - 1, r() * 2 - 1, r() * 2 - 1], n = Math.hypot(...d) || 1;
      return { d: d.map((x) => x / n), f: 1.5 + r() * 3.5, p: r() * 6.283 };
    });
  }
  return WAVES[key];
};
const fieldAt = (body, id, v) => {
  let s = 0; for (const w of waves(body, id)) s += Math.sin((v[0] * w.d[0] + v[1] * w.d[1] + v[2] * w.d[2]) * w.f + w.p);
  return Math.min(1, Math.max(0, 0.5 + s / 6 * 0.9));
};

const VECS = new Map();
const gridVecs = () => {
  if (!VECS.has('g')) {
    const a = new Array(W * H);
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) a[y * W + x] = toVec(90 - ((y + 0.5) / H) * 180, ((x + 0.5) / W) * 360 - 180);
    VECS.set('g', a);
  }
  return VECS.get('g');
};
const gridFields = (body) => {
  const k = 'f' + body;
  if (!VECS.has(k)) { const g = gridVecs(); VECS.set(k, CHARACTERISTICS.map((c) => Float32Array.from(g, (v) => fieldAt(body, c.id, v)))); }
  return VECS.get(k);
};

const wsum = (weights) => CHARACTERISTICS.reduce((n, c) => n + Math.max(0, Number(weights[c.id]) || 0), 0);
const mix = (q, weights) => { // q: array of 0..1 per characteristic
  const t = wsum(weights);
  return CHARACTERISTICS.reduce((n, c, i) => n + (t ? Math.max(0, Number(weights[c.id]) || 0) / t : 1 / q.length) * q[i], 0);
};

/* Reference of a selection: mean field values of the target body inside the zone. */
export const reference = (body, selection) => {
  const g = gridVecs(), F = gridFields(body), sums = CHARACTERISTICS.map(() => 0); let n = 0;
  const c = selection.area?.shape === 'cap' ? selection.area.center : selection.point || selection.area?.center;
  const b = selection.area?.bounds;
  const lat0 = c ? c.lat : (b.north + b.south) / 2, lon0 = c ? c.lon : (b.east + b.west) / 2;
  const cv = toVec(lat0, lon0);
  for (let i = 0; i < g.length; i++) {
    const y = Math.floor(i / W), x = i % W, lat = 90 - ((y + 0.5) / H) * 180, lon = ((x + 0.5) / W) * 360 - 180;
    let inside = false;
    if (selection.area?.shape === 'cap') inside = angleDeg(cv, g[i]) <= selection.area.radiusDeg;
    else if (selection.area?.shape === 'rect') inside = lat >= b.south && lat <= b.north && lon >= b.west && lon <= b.east;
    else inside = angleDeg(cv, g[i]) <= 3;
    if (inside) { n++; F.forEach((f, k) => { sums[k] += f[i]; }); }
  }
  if (!n) CHARACTERISTICS.forEach((ch, k) => { sums[k] = fieldAt(body, ch.id, cv); n = 1; });
  return { ref: sums.map((s) => s / n), lat: lat0, lon: lon0 };
};

/* Accuracy of a single location of `body` when nothing is selected yet. */
export const accuracyAt = (body, lat, lon, weights) => {
  const v = toVec(lat, lon);
  return mix(CHARACTERISTICS.map((c) => fieldAt(body, c.id, v)), weights) * 100;
};

/* Accuracy grid (0..100) for `body`: how closely each place matches the reference, weighted. */
export const accuracyGrid = (body, ref, weights) => {
  const F = gridFields(body), out = new Float32Array(W * H), t = wsum(weights);
  const wn = CHARACTERISTICS.map((c) => (t ? Math.max(0, Number(weights[c.id]) || 0) / t : 1 / CHARACTERISTICS.length));
  for (let i = 0; i < out.length; i++) { let s = 0; for (let k = 0; k < F.length; k++) s += wn[k] * (1 - Math.abs(F[k][i] - ref[k])); out[i] = s * 100; }
  return out;
};

/* Best match on `body` and its per-characteristic scores (0..100). */
export const bestMatch = (body, ref, weights, grid = accuracyGrid(body, ref, weights)) => {
  let bi = 0; for (let i = 1; i < grid.length; i++) if (grid[i] > grid[bi]) bi = i;
  const F = gridFields(body), x = bi % W, y = Math.floor(bi / W);
  return { lat: 90 - ((y + 0.5) / H) * 180, lon: ((x + 0.5) / W) * 360 - 180, scores: Object.fromEntries(CHARACTERISTICS.map((c, k) => [c.id, (1 - Math.abs(F[k][bi] - ref[k])) * 100])) };
};

/* ---- colour: Moon white, Mars red, Earth blue; brighter = more accurate ---- */
const RAMPS = {
  moon: [[24, 24, 26], [96, 96, 100], [170, 170, 174], [255, 255, 255]],
  mars: [[40, 6, 6], [130, 16, 12], [214, 40, 26], [255, 120, 96]],
  earth: [[4, 14, 48], [12, 52, 140], [30, 120, 230], [140, 210, 255]],
};
export const BANDS = [['T1', 'Very low accuracy', 0], ['T2', 'Low accuracy', 20], ['T3', 'Moderate accuracy', 40], ['T4', 'High accuracy', 60], ['T5', 'Very high accuracy', 80]];
export const codeOf = (a) => BANDS[Math.min(4, Math.max(0, Math.floor(a / 20)))];
export const colorOf = (body, a) => {
  const r = RAMPS[body] || RAMPS.moon, t = Math.min(0.999, Math.max(0, a / 100)) * (r.length - 1), i = Math.floor(t), f = t - i;
  return r[i].map((c, k) => Math.round(c + (r[i + 1][k] - c) * f));
};
export const cssColor = (body, a) => `rgb(${colorOf(body, a).join(',')})`;
export const legend = (body) => BANDS.map(([code, meaning, lo]) => ({ code, meaning: `${meaning} (${lo}-${lo + 20}%)`, color: cssColor(body, lo + 10) }));

/* Paint base map + thermal layer (with contour lines at band edges) into a canvas (2:1). */
export const paintThermal = (canvas, baseImg, body, grid) => {
  const cw = canvas.width, ch = canvas.height, ctx = canvas.getContext('2d');
  ctx.drawImage(baseImg, 0, 0, cw, ch); ctx.fillStyle = 'rgba(0,0,0,.5)'; ctx.fillRect(0, 0, cw, ch);
  const lo = document.createElement('canvas'); lo.width = W; lo.height = H;
  const lc = lo.getContext('2d'), img = lc.createImageData(W, H);
  for (let i = 0; i < grid.length; i++) {
    const x = i % W, a = grid[i], edge = (x < W - 1 && Math.floor(a / 10) !== Math.floor(grid[i + 1] / 10)) || (i + W < grid.length && Math.floor(a / 10) !== Math.floor(grid[i + W] / 10));
    const c = colorOf(body, a), k = edge ? 1.35 : 1;
    img.data[i * 4] = Math.min(255, c[0] * k); img.data[i * 4 + 1] = Math.min(255, c[1] * k); img.data[i * 4 + 2] = Math.min(255, c[2] * k); img.data[i * 4 + 3] = edge ? 255 : 215;
  }
  lc.putImageData(img, 0, 0); ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high'; ctx.drawImage(lo, 0, 0, cw, ch);
};

/* Frontend-written text that describes the data of one characteristic. */
export const describeItem = ({ label, score, share, impact, bodyName, where }) => {
  if (!Number.isFinite(score)) return 'No value is available for this characteristic.';
  const tier = score >= 80 ? 'a very close match' : score >= 60 ? 'a close match' : score >= 40 ? 'a partial match' : score >= 20 ? 'a weak match' : 'a poor match';
  return `${label} reaches ${score.toFixed(1)}%, which is ${tier} between the selected zone on ${bodyName} and the best Earth location${where ? ` (${where})` : ''}. With the current weights it carries ${(share * 100).toFixed(1)}% of the total and contributes ${impact.toFixed(1)} points to the overall result. ${share > 0.2 ? 'It is one of the strongest drivers of the result, so changing its weight moves the thermal view the most.' : 'Its influence on the thermal view is modest at this weight.'}`;
};
