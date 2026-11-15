import { useRef, useState } from 'react';
import { BODIES, MODES, UI } from '../content.js';
import { navigate } from '../router.js';
import GlobePicker from '../components/GlobePicker.jsx';
import MapPicker from '../components/MapPicker.jsx';
import Toolbar from '../components/Toolbar.jsx';
import { EMPTY_SELECTION, hasSelection, fmtLat, fmtLon, saveSelection } from '../data/selection.js';

export default function WorkspacePage({ body, mode }) {
  const is3d = mode === '3d';
  const picker = useRef(null);
  const [sel, setSel] = useState(EMPTY_SELECTION);
  const [tools, setTools] = useState(is3d ? { roll: true, pointer: false, area: false } : { pan: true, pointer: true, area: false });

  const move = is3d ? 'roll' : 'pan';
  const toggle = (name) => {
    setTools((t) => {
      const next = { ...t, [name]: !t[name] };
      if (next[name] && name === 'area') next[move] = false; // dragging cannot both draw and move
      if (next[name] && name === move) next.area = false;
      return next;
    });
    if (tools[name] && name === 'pointer') setSel((s) => ({ ...s, point: null }));
    if (tools[name] && name === 'area') setSel((s) => ({ ...s, area: null }));
  };
  const patch = (p) => setSel((s) => ({ ...s, ...p }));
  const active = { point: tools.pointer && sel.point, area: tools.area && sel.area };
  const ready = hasSelection(active);
  const Picker = is3d ? GlobePicker : MapPicker;

  const [leaving, setLeaving] = useState(false);
  const go = () => { saveSelection(body, mode, active); setLeaving(true); setTimeout(() => navigate(`compare/${body}/${mode}/results`), 650); };

  const hint = [
    tools.pointer && UI.hintPointer,
    tools.area && (is3d ? UI.hintArea3d : UI.hintArea2d),
    tools[move] && (is3d ? UI.hintRoll : UI.hintPan),
  ].filter(Boolean).join(' ');

  return (
    <section className={`workspace${leaving ? ' is-leaving' : ''}`}>
      <Picker ref={picker} planet={body} tools={tools} selection={sel} onSelect={patch} />
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
        <div className="readout__actions">
          <button className="cta cta--sm" disabled={!ready} onClick={go}>{UI.compare}<span aria-hidden="true"> &rarr;</span></button>
          <button className="link" disabled={!ready} onClick={() => setSel(EMPTY_SELECTION)}>{UI.clear}</button>
        </div>
      </aside>
      <Toolbar mode={mode} tools={tools} onToggle={toggle} onZoom={(f) => picker.current?.zoomBy(f)} onReset={() => picker.current?.reset()} />
    </section>
  );
}
