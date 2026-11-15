import { useEffect, useRef, useState } from 'react';
import { boot } from './modules/boot.js';
import { loadTargets, tgt } from './data.js';
import Dock from './components/Dock.jsx';
import Panel from './components/Panel.jsx';

/* React owns the HUD, targets dock, credits and mission window. The 3D scene, audio and 2D maps
   (src/modules) still drive their own canvas/controls imperatively. */
export default function App() {
  const [targets, setTargets] = useState([]), [link, setLink] = useState('CHECKING'), [sel, setSel] = useState(null),
    [run, setRun] = useState(null), [open, setOpen] = useState(false), [cred, setCred] = useState(false);
  const selRef = useRef(null), tRef = useRef([]); selRef.current = sel; tRef.current = targets;
  useEffect(() => { boot(); loadTargets().then(({ ids, live }) => { setTargets(ids.map(tgt)); setLink(live ? 'NOMINAL' : 'DEMO DATA'); }); }, []);
  useEffect(() => {
    /* planet click in the 3D scene: reuse the selected target of that body, else the first one */
    window.pickBody = b => { const s = selRef.current, t = s && s.body === b ? s : tRef.current.find(x => x.body === b); if (!t) return; setSel(t); setRun(r => ({ t, n: (r ? r.n : 0) + 1 })); setOpen(true); };
    const esc = e => { if (e.key === 'Escape') { setCred(false); setOpen(false); } };
    addEventListener('keydown', esc); return () => removeEventListener('keydown', esc);
  }, []);
  return (
    <>
<canvas id="bg"></canvas>
<div id="lbls"><button className="pl" data-b="moon" onClick={() => window.pickBody('moon')} aria-label="Open Moon targets"><b>MOON</b><span className="v">3,474 km | 0.165 g</span><span className="t">~50 - 395 K</span><em>Open targets</em></button><div className="pl"><b>EARTH</b><span className="v">12,742 km | 1.00 g</span><span className="t">~215 - 335 K</span><em>Analog source</em></div><button className="pl" data-b="mars" onClick={() => window.pickBody('mars')} aria-label="Open Mars targets"><b>MARS</b><span className="v">6,779 km | 0.379 g</span><span className="t">~130 - 295 K</span><em>Open targets</em></button></div>
<div id="flat" aria-label="2D comparison maps"><figure><figcaption><b></b><span className="v"></span><span className="t"></span></figcaption><canvas></canvas></figure><figure><figcaption><b></b><span className="v"></span><span className="t"></span></figcaption><canvas></canvas></figure><small>Sun overhead at map centre. Grid every 30 degrees. Equirectangular projection.</small></div>
<div id="intro"><img id="logo" src="assets/logo.png" alt="Black Ops astronaut crew" /><button id="begin" disabled>Initializing surfaces</button></div>
<div id="hud">
 <div className="top"><div><div>SOL <span id="sol"></span></div><div>UTC <span id="utc"></span></div></div><div className="c">ANALOG DISCOVERY ENGINE</div><div className="r"><div>EARTH - MOON - MARS</div><div>DEEP SPACE NETWORK</div><div>LINK: <b id="link">{link}</b></div></div></div>
 <div className="hero"><h1>Find the Earth terrain that behaves like the Moon and Mars</h1><p>Pick a lunar or Martian target. The engine ranks where on Earth you can rehearse the mission, and shows where the match fails.</p></div>
 <Dock targets={targets} selected={sel} onSelect={setSel} onRun={t => { setRun(r => ({ t, n: (r ? r.n : 0) + 1 })); setOpen(true); }} />
</div>
<div className="ctl"><div className="grp scale"><b>DIMENSION</b><div className="seg" id="dm" data-m="3d" role="group"><i className="thumb"></i><button className="on" data-v="3d" aria-pressed="true">3D</button><button data-v="flat" aria-pressed="false">2D map</button></div></div><div className="grp scale pair" id="prg" ><b>COMPARE</b><div className="seg" id="pr" data-m="moon" role="group"><i className="thumb"></i><button className="on" data-v="moon" aria-pressed="true">Moon - Earth</button><button data-v="mars" aria-pressed="false">Mars - Earth</button></div></div><div className="grp scale"><b>PLANET SCALE</b><div className="seg" id="sz" data-m="equal" role="group" aria-label="Planet scale"><i className="thumb"></i><button className="on" data-m="equal" aria-pressed="true"><svg viewBox="0 0 26 12" aria-hidden="true"><circle cx="4" cy="6" r="3.4"/><circle cx="13" cy="6" r="3.4"/><circle cx="22" cy="6" r="3.4"/></svg>Equal size</button><button data-m="real" aria-pressed="false"><svg viewBox="0 0 26 12" aria-hidden="true"><circle cx="3.5" cy="6" r="1.8"/><circle cx="12" cy="6" r="5.4"/><circle cx="22" cy="6" r="3"/></svg>True scale</button></div></div><div className="grp scale"><b>VIEW</b><div className="seg" id="vw" data-m="visual" role="group" aria-label="Surface view"><i className="thumb"></i><button className="on" data-v="visual" aria-pressed="true"><svg viewBox="0 0 26 12" aria-hidden="true"><circle cx="13" cy="6" r="4.6"/><path d="M10 4.5a4 4 0 013-1.3"/></svg>Visual</button><button data-v="thermal" aria-pressed="false"><svg viewBox="0 0 26 12" aria-hidden="true"><path d="M3 11V8M9 11V5M15 11V3M21 11V1"/></svg>Thermal</button></div></div></div>
<div id="tlg" aria-label="Temperature scale"><b>MODELLED SURFACE<br />TEMPERATURE</b><div className="tb"><i></i><div className="tk"><span>420 K</span><span>335</span><span>250</span><span>165</span><span>80</span></div></div><button id="tsc" data-own="false" title="Switch between one shared temperature scale and a separate scale per planet">Shared scale</button><small>Estimated from albedo, sunlight and latitude. Not measured data.</small></div>
<div id="snd"><span id="mname">QUIET ECHOES</span><button id="crd" aria-expanded={cred} onClick={() => setCred(c => !c)}>Credits</button><div id="credbox" hidden={!cred}><b>CREDITS</b>Earth model: tamminen (Sketchfab, CC BY 4.0)<br />Moon model: Akshat (Sketchfab, CC BY 4.0)<br />Mars model: DURVESH123 (Sketchfab, CC BY 4.0)<br />Star photo: Paul Lichtblau (Unsplash)<br />Music: Quiet Echoes by Brioso<br />City lights on Earth are a stylised, generated layer.</div><button id="mt" data-on="true">Mute</button><label id="load" hidden>Load track<input type="file" accept="audio/*" hidden /></label></div>
<Panel run={run} open={open} onClose={() => setOpen(false)} />
    </>
  );
}
