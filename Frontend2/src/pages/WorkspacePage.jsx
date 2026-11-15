import { useRef, useState } from 'react';
import { BODIES, MODES, UI } from '../content.js';
import { navigate } from '../router.js';
import GlobePicker from '../components/GlobePicker.jsx';
import MapPicker from '../components/MapPicker.jsx';
import Toolbar from '../components/Toolbar.jsx';
import { EMPTY_SELECTION, hasSelection, fmtLat, fmtLon, saveSelection } from '../data/selection.js';
import { CHARACTERISTICS, loadWeights, saveWeights } from '../data/characteristics.js';
import { accuracyAt, codeOf, cssColor, legend, DATA_SOURCE } from '../data/thermal.js';

const centerOf = ({ point, area }) => {
  if (point) return point;
  if (area?.shape === 'cap') return area.center;
  if (area?.bounds) { const b = area.bounds; return { lat: (b.north + b.south) / 2, lon: b.west <= b.east ? (b.west + b.east) / 2 : b.west } ; }
  return null;
};

export default function WorkspacePage({ body, mode }) {
  const is3d = mode === '3d';
  const picker = useRef(null);
  const [sel, setSel] = useState(EMPTY_SELECTION);
  const [tools, setTools] = useState({ pointer: true, area: false });
  const [dw, setDw] = useState(null); // hover rested 3 s with no click
  const [weights, setWeights] = useState(loadWeights);
  const [wOpen, setWOpen] = useState(false);
  const setW = (id, v) => setWeights((w) => { const n = { ...w, [id]: Number(v) }; saveWeights(n); return n; });

  const toggle = (name) => {
    setTools((t) => ({ ...t, [name]: !t[name] }));
    if (tools[name]) setSel((s) => ({ ...s, [name === 'pointer' ? 'point' : 'area']: null }));
  };
  const patch = (p) => { setDw(null); setSel((s) => ({ ...s, ...p })); };
  const active = { point: tools.pointer && sel.point, area: tools.area && sel.area };
  const ready = hasSelection(active);
  const Picker = is3d ? GlobePicker : MapPicker;

  const dAcc = dw ? accuracyAt(body, dw.lat, dw.lon, weights) : null;
  const dwell = dw ? { lat: dw.lat, lon: dw.lon, color: cssColor(body, dAcc) } : null;
  const c = ready ? centerOf(active) : null;
  const sAcc = c ? accuracyAt(body, c.lat, c.lon, weights) : null;

  const [leaving, setLeaving] = useState(false);
  const go = () => { saveSelection(body, mode, active); setLeaving(true); setTimeout(() => navigate(`compare/${body}/${mode}/results`), 650); };

  const hint = [
    tools.area ? (is3d ? UI.hintArea3d : UI.hintArea2d) : (is3d ? UI.hintRoll : UI.hintPan),
    tools.pointer && UI.hintPointer,
  ].filter(Boolean).join(' ');

  return (
    <section className={`workspace${leaving ? ' is-leaving' : ''}`}>
      <Picker ref={picker} planet={body} tools={tools} selection={sel} onSelect={patch} dwell={dwell} onDwell={setDw} />
      <div className="workspace__head">
        <a className="back" href={`#/compare/${body}`}>&larr; Back</a>
        <p className="eyebrow">Earth and {BODIES[body].name}</p>
        <h1 className="display display--sm">{MODES[mode].label} of {BODIES[body].name}</h1>
        <p className="workspace__hint">{hint || UI.hintNone}</p>
      </div>
      <aside className="readout" aria-live="polite">
        <p className="eyebrow">Selection</p>
        {!ready && <p className="readout__empty">{UI.noSelection}</p>}
        {active.point && <p><b>Point</b><span>{fmtLat(active.point.lat)}, {fmtLon(active.point.lon)}</span></p>}
        {active.area?.shape === 'cap' && <p><b>Area</b><span>{fmtLat(active.area.center.lat)}, {fmtLon(active.area.center.lon)}, radius {active.area.radiusDeg.toFixed(1)}°</span></p>}
        {active.area?.shape === 'rect' && <p><b>Area</b><span>{fmtLat(active.area.bounds.south)} to {fmtLat(active.area.bounds.north)}, {fmtLon(active.area.bounds.west)} to {fmtLon(active.area.bounds.east)}</span></p>}
        {sAcc != null && <p><b>Thermal preview</b><span className="readout__therm"><i style={{ background: cssColor(body, sAcc) }} />{codeOf(sAcc)[0]} · {sAcc.toFixed(1)}%</span><small>{DATA_SOURCE}; backend scores are target-level.</small></p>}
        <div className="readout__actions">
          <button className="cta cta--sm" disabled={!ready} onClick={go}>{UI.compare}<span aria-hidden="true"> &rarr;</span></button>
          <button className="link" disabled={!ready} onClick={() => setSel(EMPTY_SELECTION)}>{UI.clear}</button>
        </div>
      </aside>
      {dw && (
        <div className="dwell" style={{ left: dw.x, top: dw.y }}>
          <b><i style={{ background: cssColor(body, dAcc) }} />{codeOf(dAcc)[0]} · {dAcc.toFixed(1)}%</b>
          {codeOf(dAcc)[1]}<br />{fmtLat(dw.lat)}, {fmtLon(dw.lon)}
          <small>Accuracy for your current weights. {DATA_SOURCE}.</small>
        </div>
      )}
      {wOpen && (
        <aside className="wpanel">
          <p className="eyebrow">Weights change the thermal accuracy</p>
          <div className="weights">
            {CHARACTERISTICS.map((c) => (
              <label key={c.id} className="weights__row"><span>{c.label}</span><input type="range" min="0" max="100" value={weights[c.id]} onChange={(e) => setW(c.id, e.target.value)} /><b>{weights[c.id]}</b></label>
            ))}
          </div>
          <ul className="key">{legend(body).map((l) => <li key={l.code}><i style={{ background: l.color }} /><b>{l.code}</b> {l.meaning}</li>)}</ul>
        </aside>
      )}
      <Toolbar weightsOn={wOpen} onWeights={() => setWOpen((v) => !v)} tools={tools} onToggle={toggle} onZoom={(f) => picker.current?.zoomBy(f)} onReset={() => picker.current?.reset()} />
    </section>
  );
}
