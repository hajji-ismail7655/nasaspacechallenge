import { fmtLat, fmtLon } from './selection.js';

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const pct = (n) => (Number.isFinite(n) ? `${n.toFixed(1)}%` : '—');

const describe = (sel) => {
  const out = [];
  if (sel?.point) out.push(`Point: ${fmtLat(sel.point.lat)}, ${fmtLon(sel.point.lon)}`);
  const a = sel?.area;
  if (a?.shape === 'cap') out.push(`Area (circle): centre ${fmtLat(a.center.lat)}, ${fmtLon(a.center.lon)}, radius ${a.radiusDeg.toFixed(2)}°`);
  if (a?.shape === 'rect') out.push(`Area (rectangle): ${fmtLat(a.bounds.south)} to ${fmtLat(a.bounds.north)}, ${fmtLon(a.bounds.west)} to ${fmtLon(a.bounds.east)}`);
  return out;
};

/* Standalone, printable HTML report. Contains only what the dataset returned. */
export function buildReport({ bodyName, selection, overall, items, labels, texts, legend }) {
  const rows = items.map((it, i) => `<tr><td>${esc(labels[i])}</td><td>${pct(it.score)}</td><td>${it.weight}</td><td>${it.missing ? '—' : pct(it.share * 100)}</td><td>${it.missing ? '—' : pct(it.impact)}</td></tr>`).join('');
  const paras = items.map((it, i) => `<h3>${esc(labels[i])}</h3><p class="m">Similarity ${pct(it.score)} · Weight share ${it.missing ? '—' : pct(it.share * 100)} · Impact ${it.missing ? '—' : pct(it.impact)}</p><p>${esc(texts?.[it.id] || 'No text available.')}</p>`).join('');
  const key = (legend || []).map((l) => `<li><b>${esc(l.code)}</b> ${esc(l.meaning)}</li>`).join('');
  return `<!doctype html><html lang="en"><meta charset="utf-8"><title>Earth and ${esc(bodyName)} report</title>
<style>body{font:17px/1.55 'Times New Roman',serif;max-width:820px;margin:40px auto;padding:0 20px;color:#111}h1{font-weight:500}h3{margin:28px 0 0}.m{color:#555;font-size:14px;margin:2px 0 6px}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ccc;padding:6px 8px;text-align:left}.big{font-size:56px;margin:0}</style>
<h1>Earth and ${esc(bodyName)}: similarity report</h1><p class="m">Generated ${new Date().toISOString().slice(0, 10)}</p>
${describe(selection).map((l) => `<p>${esc(l)}</p>`).join('')}
<p class="big">${pct(overall)}</p><p class="m">Overall weighted similarity</p>
<table><tr><th>Characteristic</th><th>Similarity</th><th>Weight</th><th>Share</th><th>Impact</th></tr>${rows}</table>
${key ? `<h2>Thermal code</h2><ul>${key}</ul>` : ''}<h2>Comparison by characteristic</h2>${paras}</html>`;
}

export function downloadReport(html, name) {
  const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
  const a = Object.assign(document.createElement('a'), { href: url, download: `earth-${name.toLowerCase().replace(/\W+/g, '-')}-report.html` });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
