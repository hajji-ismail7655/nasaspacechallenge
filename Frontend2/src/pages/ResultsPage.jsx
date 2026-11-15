import { useEffect, useMemo, useState } from 'react';
import { BODIES, PLANETS } from '../content.js';
import { asset } from '../assets.js';
import { CHARACTERISTICS, loadWeights, saveWeights } from '../data/characteristics.js';
import { getComparison } from '../data/provider.js';
import { weightedBreakdown } from '../data/scoring.js';
import { loadSelection, toProviderSelection, fmtLat, fmtLon } from '../data/selection.js';
import { reference, accuracyGrid, bestMatch, paintThermal, legend, describeItem, DATA_SOURCE } from '../data/thermal.js';
import { navigate } from '../router.js';
import { buildReport, downloadReport } from '../data/report.js';
import PlanetSphere from '../components/PlanetSphere.jsx';
import MapPicker from '../components/MapPicker.jsx';

const pct = (n) => (Number.isFinite(n) ? `${n.toFixed(1)}%` : '—');
const newCanvas = () => Object.assign(document.createElement('canvas'), { width: 1024, height: 512 });
const loadImg = (src) => new Promise((res) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => res(null); i.src = src; });

export default function ResultsPage({ body, mode }) {
  const saved = useMemo(loadSelection, []);
  const selection = saved?.selection || null;
  const [data, setData] = useState(null);
  const [status, setStatus] = useState(selection ? 'loading' : 'none');
  const [weights, setWeights] = useState(loadWeights);
  const [thermal, setThermal] = useState(true);
  const [drawer, setDrawer] = useState(false);
  const name = BODIES[body].name;

  useEffect(() => {
    if (!selection) return;
    getComparison({ body, selection: toProviderSelection(selection) })
      .then((d) => { setData(d); setStatus('ok'); })
      .catch(() => setStatus('preview')); // backend not connected: local preview values
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /* accuracy fields, recomputed whenever a weight moves */
  const refData = useMemo(() => (selection ? reference(body, selection) : null), []); // eslint-disable-line react-hooks/exhaustive-deps
  const gridE = useMemo(() => (refData ? accuracyGrid('earth', refData.ref, weights) : null), [refData, weights]);
  const gridT = useMemo(() => (refData ? accuracyGrid(body, refData.ref, weights) : null), [refData, weights, body]);
  const best = useMemo(() => (gridE ? bestMatch('earth', refData.ref, weights, gridE) : null), [gridE]); // eslint-disable-line react-hooks/exhaustive-deps

  const scores = data?.scores || best?.scores || Object.fromEntries(CHARACTERISTICS.map((c) => [c.id, null]));
  const { overall, items } = weightedBreakdown(scores, weights);
  const shown = status === 'ok' || status === 'preview';

  /* thermal canvases wrapped around both spheres */
  const cE = useMemo(newCanvas, []), cT = useMemo(newCanvas, []);
  const [imgs, setImgs] = useState(null), [tick, setTick] = useState(0);
  useEffect(() => { let on = true; Promise.all([loadImg(asset(PLANETS.earth.texture)), loadImg(asset(PLANETS[body].texture))]).then(([e, t]) => on && e && t && setImgs({ earth: e, body: t })); return () => { on = false; }; }, [body]);
  useEffect(() => {
    if (!imgs || !gridE) return;
    const id = requestAnimationFrame(() => { paintThermal(cE, imgs.earth, 'earth', gridE); paintThermal(cT, imgs.body, body, gridT); setTick((t) => t + 1); });
    return () => cancelAnimationFrame(id);
  }, [imgs, gridE, gridT]); // eslint-disable-line react-hooks/exhaustive-deps
  const thE = useMemo(() => (thermal && tick ? { canvas: cE, v: tick } : null), [thermal, tick]); // eslint-disable-line react-hooks/exhaustive-deps
  const thT = useMemo(() => (thermal && tick ? { canvas: cT, v: tick } : null), [thermal, tick]); // eslint-disable-line react-hooks/exhaustive-deps

  const mapSrc = useMemo(() => (drawer && thermal && tick ? cT.toDataURL('image/jpeg', 0.85) : undefined), [drawer, thermal, tick]); // eslint-disable-line react-hooks/exhaustive-deps
  const markT = refData ? { lat: refData.lat, lon: refData.lon, radiusDeg: selection.area?.shape === 'cap' ? selection.area.radiusDeg : 3 } : null;
  const markE = best ? { lat: best.lat, lon: best.lon, radiusDeg: 3 } : null;
  const where = best ? `${fmtLat(best.lat)}, ${fmtLon(best.lon)}` : '';

  const texts = Object.fromEntries(items.map((it, i) => [it.id, data?.texts?.[it.id] || describeItem({ label: CHARACTERISTICS[i].label, score: it.score, share: it.share, impact: it.impact, bodyName: name, where })]));
  const keyT = legend(body), keyE = legend('earth');
  const setW = (id, v) => setWeights((w) => { const n = { ...w, [id]: Number(v) }; saveWeights(n); return n; });

  return (
    <div className={`results${drawer ? ' has-drawer' : ''}`}>
      <section className="results__top">
        <a className="back noprint" href={`#/compare/${body}/${mode}`}>&larr; Back to selection</a>
        <p className="eyebrow">Earth and {name}</p>
        <div className="results__overall">
          <span className="results__pct">{shown ? pct(overall) : '—'}</span>
          <span className="eyebrow">Overall similarity</span>
        </div>
        <p className="copy copy--center results__sel">
          {selection?.point && <>Point {fmtLat(selection.point.lat)}, {fmtLon(selection.point.lon)}. </>}
          {selection?.area && <>Area ({selection.area.shape}). </>}
          {best && <>Illustrative map marker: {where}. </>}
          {status === 'none' && 'No selection. Go back and choose a point or an area.'}
        </p>
        <p className="srcnote">Discovery scores come from the backend. Thermal colors and map markers use {DATA_SOURCE.toLowerCase()} and are illustrative only.</p>
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
          <h2 className="display display--sm">Thermal preview</h2>
          <button className={`tool tool--inline${thermal ? ' is-on' : ''}`} aria-pressed={thermal} disabled={!selection} onClick={() => setThermal((v) => !v)}><span>Thermal view</span></button>
          <button className={`tool tool--inline${drawer ? ' is-on' : ''}`} aria-pressed={drawer} onClick={() => setDrawer((v) => !v)}><span>2D mapping</span></button>
        </div>
        <p className="copy">Brighter means a more accurate match to your selection. Move a slider and the colours update at once.</p>
        <div className="weights weights--main noprint">
          {CHARACTERISTICS.map((c) => (
            <label key={c.id} className="weights__row">
              <span>{c.label}</span>
              <input type="range" min="0" max="100" value={weights[c.id]} onChange={(e) => setW(c.id, e.target.value)} />
              <b>{weights[c.id]}</b>
            </label>
          ))}
        </div>
        <div className="duo">
          <figure><div className="rstage"><PlanetSphere planet="earth" thermal={thE} marker={markE} /></div><figcaption className="eyebrow">Earth: illustrative marker</figcaption></figure>
          <figure><div className="rstage"><PlanetSphere planet={body} thermal={thT} marker={markT} /></div><figcaption className="eyebrow">{name}: selected area</figcaption></figure>
        </div>
        <ul className="key">
          <li className="eyebrow">Thermal code</li>
          {keyT.map((l, i) => <li key={l.code}><i style={{ background: keyE[i].color }} /><i style={{ background: l.color }} /><b>{l.code}</b> {l.meaning}</li>)}
        </ul>
      </section>

      <section className="results__block results__text">
        <h2 className="display display--sm">Comparison by characteristic</h2>
        {items.map((it, i) => (
          <article key={it.id}>
            <h3 className="display display--sm">{CHARACTERISTICS[i].label}</h3>
            <p className="eyebrow">Similarity {pct(it.score)} · Weight share {it.missing ? '—' : pct(it.share * 100)} · Impact on overall {it.missing ? '—' : pct(it.impact)}</p>
            <p className="copy">{texts[it.id]}</p>
          </article>
        ))}
      </section>

      <section className="results__end noprint">
        <button className="cta" disabled={!shown} onClick={() => downloadReport(buildReport({ bodyName: name, selection, overall, items, labels: CHARACTERISTICS.map((c) => c.label), texts, legend: keyT.map(({ code, meaning }) => ({ code, meaning })) }), name)}>Download report</button>
        <button className="cta" onClick={() => window.print()}>Print / PDF</button>
        <button className="cta" onClick={() => navigate(`compare/${body}/${mode}`)}>Test another spot</button>
      </section>

      <aside className="drawer noprint" aria-hidden={!drawer}>
        <button className="link" onClick={() => setDrawer(false)}>Close &times;</button>
        <p className="eyebrow">2D mapping</p>
        <div className="drawer__map"><MapPicker planet={body} tools={{}} mapSrc={mapSrc} selection={selection || { point: null, area: null }} onSelect={() => {}} /></div>
      </aside>
    </div>
  );
}
