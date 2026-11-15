import { useEffect, useMemo, useState } from 'react';
import { BODIES } from '../content.js';
import { CHARACTERISTICS, defaultWeights } from '../data/characteristics.js';
import { getComparison } from '../data/provider.js';
import { weightedBreakdown } from '../data/scoring.js';
import { loadSelection, toProviderSelection, fmtLat, fmtLon } from '../data/selection.js';
import { navigate } from '../router.js';
import { buildReport, downloadReport } from '../data/report.js';
import PlanetSphere from '../components/PlanetSphere.jsx';
import MapPicker from '../components/MapPicker.jsx';

const pct = (n) => (Number.isFinite(n) ? `${n.toFixed(1)}%` : '—');

export default function ResultsPage({ body, mode }) {
  const saved = useMemo(loadSelection, []);
  const selection = saved?.selection || null;
  const [data, setData] = useState(null);
  const [status, setStatus] = useState(selection ? 'loading' : 'none');
  const [weights, setWeights] = useState(defaultWeights);
  const [thermal, setThermal] = useState(false);
  const [drawer, setDrawer] = useState(false);

  useEffect(() => {
    if (!selection) return;
    getComparison({ body, selection: toProviderSelection(selection) })
      .then((d) => { setData(d); setStatus('ok'); })
      .catch(() => setStatus('nodata'));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const scores = data?.scores || Object.fromEntries(CHARACTERISTICS.map((c) => [c.id, null]));
  const { overall, items } = weightedBreakdown(scores, weights);
  const t = data?.thermal;
  const earthTex = thermal && t?.earth ? t.earth : undefined;
  const targetTex = thermal && t?.target ? t.target : undefined;
  const name = BODIES[body].name;
  const setW = (id, v) => setWeights((w) => ({ ...w, [id]: Number(v) }));

  const Weights = (
    <div className="weights">
      {CHARACTERISTICS.map((c) => (
        <label key={c.id} className="weights__row">
          <span>{c.label}</span>
          <input type="range" min="0" max="100" value={weights[c.id]} onChange={(e) => setW(c.id, e.target.value)} />
          <b>{weights[c.id]}</b>
        </label>
      ))}
    </div>
  );

  return (
    <div className={`results${drawer ? ' has-drawer' : ''}`}>
      <section className="results__top">
        <a className="back noprint" href={`#/compare/${body}/${mode}`}>&larr; Back to selection</a>
        <p className="eyebrow">Earth and {name}</p>
        <div className="results__overall">
          <span className="results__pct">{status === 'ok' ? pct(overall) : '—'}</span>
          <span className="eyebrow">Overall similarity</span>
        </div>
        <p className="copy copy--center results__sel">
          {selection?.point && <>Point {fmtLat(selection.point.lat)}, {fmtLon(selection.point.lon)}. </>}
          {selection?.area && <>Area ({selection.area.shape}). </>}
          {status === 'nodata' && 'Dataset not connected yet.'}
          {status === 'none' && 'No selection. Go back and choose a point or an area.'}
        </p>
      </section>

      <section className="results__block">
        <h2 className="display display--sm">Characteristics and weights</h2>
        <table className="chars">
          <thead><tr><th>Characteristic</th><th>Similarity</th><th>Weight</th><th>Share</th><th>Impact</th></tr></thead>
          <tbody>
            {items.map((it, i) => (
              <tr key={it.id}>
                <td>{CHARACTERISTICS[i].label}</td>
                <td>{pct(it.score)}</td><td>{it.weight}</td><td>{it.missing ? '—' : pct(it.share * 100)}</td><td>{it.missing ? '—' : pct(it.impact)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="results__block">
        <div className="results__bar noprint">
          <h2 className="display display--sm">Thermal similarity</h2>
          <button className={`tool tool--inline${thermal ? ' is-on' : ''}`} aria-pressed={thermal} disabled={!t} onClick={() => setThermal((v) => !v)}><span>Thermal view</span></button>
          <button className={`tool tool--inline${drawer ? ' is-on' : ''}`} aria-pressed={drawer} onClick={() => setDrawer((v) => !v)}><span>2D mapping</span></button>
        </div>
        <div className="duo">
          <figure><div className="rstage"><PlanetSphere planet="earth" textureUrl={earthTex} /></div><figcaption className="eyebrow">Earth</figcaption></figure>
          <figure><div className="rstage"><PlanetSphere planet={body} textureUrl={targetTex} /></div><figcaption className="eyebrow">{name}</figcaption></figure>
        </div>
        <ul className="key">
          <li className="eyebrow">Thermal code</li>
          {t?.legend?.length ? t.legend.map((l) => <li key={l.code}><b>{l.code}</b> {l.meaning}</li>) : <li>Key available once the dataset is connected.</li>}
        </ul>
      </section>

      <section className="results__block results__text">
        <h2 className="display display--sm">Comparison by characteristic</h2>
        {items.map((it, i) => (
          <article key={it.id}>
            <h3 className="display display--sm">{CHARACTERISTICS[i].label}</h3>
            <p className="eyebrow">Similarity {pct(it.score)} · Weight share {it.missing ? '—' : pct(it.share * 100)} · Impact on overall {it.missing ? '—' : pct(it.impact)}</p>
            <p className="copy">{data?.texts?.[it.id] || 'Text will appear here once the dataset is connected.'}</p>
          </article>
        ))}
      </section>

      <section className="results__end noprint">
        <button className="cta" disabled={status !== 'ok'} onClick={() => downloadReport(buildReport({ bodyName: name, selection, overall, items, labels: CHARACTERISTICS.map((c) => c.label), texts: data?.texts, legend: t?.legend }), name)}>Download report</button>
        <button className="cta" onClick={() => window.print()}>Print / PDF</button>
        <button className="cta" onClick={() => navigate(`compare/${body}/${mode}`)}>Test another spot</button>
      </section>

      <aside className="drawer noprint" aria-hidden={!drawer}>
        <button className="link" onClick={() => setDrawer(false)}>Close &times;</button>
        <p className="eyebrow">2D mapping</p>
        <div className="drawer__map"><MapPicker planet={body} tools={{ pan: true }} selection={selection || { point: null, area: null }} onSelect={() => {}} /></div>
        <p className="eyebrow">Weights</p>
        {Weights}
      </aside>
    </div>
  );
}
