import { useEffect, useMemo, useRef, useState } from 'react';
import { SFX } from '../modules/audio.js';
import { sleep, rnd, hs } from '../modules/util.js';
import { ASP, PH, WIDS, OCT, score, compOf } from '../data.js';
import Icon from './Icon.jsx';
import Zones from './Zones.jsx';

const BOOT = 'UPLINK ESTABLISHED. LOADING TILE PYRAMID 30-480 M. FUSING 5 DOMAINS...';
const init = () => Object.fromEntries(WIDS.map(a => [a, 50]));

function useTypewriter(text, speed, delay) {
  const [s, setS] = useState('');
  useEffect(() => {
    let dead = false; setS('');
    (async () => { if (delay) await sleep(delay); for (let i = 1; i <= text.length; i++) { if (dead) return; setS(text.slice(0, i)); if (text[i - 1] !== ' ') SFX.type(); await sleep(speed) } })();
    return () => { dead = true };
  }, [text, speed, delay]);
  return s;
}

/* run = {t: target, n: counter}; a new run (even of the same target) restarts the boot sequence */
export default function Panel({ run, open, onClose }) {
  const t = run && run.t;
  const [aspect, setAspect] = useState('composite'), [oct, setOct] = useState(2), [w, setW] = useState(init), [ready, setReady] = useState(false), [fs, setFs] = useState(false);
  const wRef = useRef(w); wRef.current = w;
  const [redraw, setRedraw] = useState(0), barRef = useRef(null);

  useEffect(() => {
    if (!run) return; let dead = false;
    setReady(false); setAspect('composite'); setFs(false);
    (async () => { await sleep(900 + BOOT.length * 22 + 500); if (!dead) setReady(true) })();
    return () => { dead = true };
  }, [run]);
  useEffect(() => { const k = setTimeout(() => setRedraw(x => x + 1), 700); return () => clearTimeout(k) }, [fs]);

  const A = ASP.find(a => a.id === aspect), comp = t ? compOf(t.id, w) : 0, ph = t && PH[t.body];
  const sc = t ? WIDS.map(a => score(t.id, a) / 100) : [], mean = sc.length ? sc.reduce((a, b) => a + b) / 5 : 0, sd = sc.length ? Math.sqrt(sc.reduce((a, b) => a + (b - mean) ** 2, 0) / 5) : 0;
  /* description is built when the aspect is selected, so dragging a slider does not retype it */
  const desc = useMemo(() => {
    if (!t) return '';
    if (aspect === 'composite') return `Composite match ${compOf(t.id, wRef.current).toFixed(0)}%. ${A.d}`;
    const r = rnd(hs(t.id + aspect + 'e')), e = (.1 + r() * .8).toFixed(2), m = (.1 + r() * .8).toFixed(2);
    return `Match ${score(t.id, aspect)}%. Earth channel mean ${e}, target ${m}, z-divergence ${((m - e) / .18).toFixed(2)}. ${A.d}`;
  }, [t, aspect, ready]); // eslint-disable-line
  const typed = useTypewriter(ready ? desc : BOOT, ready ? 14 : 22, ready ? 0 : 900);

  const flags = ready && ph ? [`Gravity scaling x${ph.g} (Earth 9.81 m/s2)`, `Pressure gap ${ph.p.toLocaleString()} Pa (${ph.n})`, `Radiation delta about +${ph.rad} mSv/yr`, `Mean thermal delta ${ph.th} K`, 'Biosphere overprint: Earth analog hosts life'] : [];
  const cls = 'side-' + (t && t.body === 'moon' ? 'l' : 'r');
  return (
    <section id="panel" className={[t ? cls : '', open ? 'open' : '', fs ? 'fs' : ''].join(' ').trim()} aria-label="Mission analysis window">
      <div className="pm-h"><div><small>MISSION</small><h2 id="pt">{t ? t.name : ''}</h2></div><div className="pm-st"><i></i>ANALYSIS ACTIVE</div>
        <div className="pm-t"><button id="fs" onClick={() => setFs(f => !f)}>{fs ? 'Exit fullscreen' : 'Fullscreen'}</button><button id="cl" onClick={onClose}>Close</button></div></div>
      <div className="pm-b">
        <nav id="asp" aria-label="Characteristics">
          {ASP.map(a => (
            <button key={a.id} className={'asp' + (ready && aspect === a.id ? ' on' : '')} onClick={() => ready && setAspect(a.id)}>
              <span className="ic"><Icon k={a.id} /></span><span className="nm">{a.n}</span>
              <span className="s">{ready && t ? (a.id === 'composite' ? comp.toFixed(0) : score(t.id, a.id)) : '--'}</span>
              {a.id !== 'composite' && <input type="range" min="0" max="100" value={w[a.id]} aria-label={a.n + ' weight'} style={{ '--v': w[a.id] + '%' }}
                onClick={e => e.stopPropagation()} onChange={e => setW({ ...w, [a.id]: +e.target.value })} />}
            </button>))}
        </nav>
        <Zones target={t} aspect={aspect} oct={oct} weights={w} redrawKey={redraw}>
          <div id="zt">{ready && <><Icon k={aspect} /><span>{A.n}</span></>}</div>
          <div id="oct">{OCT.map((m, i) => <button key={m} className={i === oct ? 'on' : ''} onClick={() => setOct(i)}>{m} m</button>)}</div>
          <div id="lg"><i></i><span><em>Low match</em><em>High match</em></span></div>
        </Zones>
        <aside className="det">
          <div className="card"><div className="big"><span id="cs">{ready ? comp.toFixed(0) : '--'}</span><small>COMPOSITE %</small></div>
            <div className="bar"><i id="cb" ref={barRef} style={{ '--bw': ((barRef.current && barRef.current.parentNode.clientWidth) || 300) + 'px', width: ready ? comp + '%' : 0 }}></i></div>
            <small id="sii" style={{ font: '12px var(--mono)', color: 'var(--dim)' }}>{ready ? `SCALE-INVARIANCE INDEX ${(1 - sd * (1 + oct * .12)).toFixed(2)}` : ''}</small></div>
          <div className="card"><div className="row"><div className="logo" id="lb">{ready && <Icon k={aspect} />}</div><b id="an" style={{ font: '400 14px var(--disp)', letterSpacing: '.1em' }}>{ready ? A.n : ''}</b></div>
            <div id="typed" style={{ marginTop: '12px' }}>{typed}</div></div>
          <div className="card"><ul id="flags">{flags.map(f => <li key={f}>{f}</li>)}</ul></div>
          <div className="card"><small style={{ font: '11px var(--mono)', letterSpacing: '.18em', color: 'var(--cy)' }}>MISSION TEST</small><div id="test">{t ? t.test : ''}</div></div>
        </aside>
      </div>
    </section>);
}
