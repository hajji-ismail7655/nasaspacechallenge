import { useEffect, useMemo, useRef, useState } from 'react';
import { SFX } from '../modules/audio.js';
import { sleep, rnd, hs } from '../modules/util.js';
import { ASP, PH, WIDS, OCT, score, compOf, loadDiscoveries, loadBreakdown } from '../data.js';
import Icon from './Icon.jsx';
import Zones from './Zones.jsx';

const BOOT = 'UPLINK ESTABLISHED. LOADING TILE PYRAMID 30-480 M. FUSING 5 DOMAINS...';
const init = () => Object.fromEntries(WIDS.map(a => [a, 50]));

function useTypewriter(text, speed, delay) {
  const [s, setS] = useState('');
  useEffect(() => {
    let dead = false; setS('');
    (async () => { if (delay) await sleep(delay); for (let i = 1; i <= text.length; i++) { if (dead) return; setS(text.slice(0, i)); if (text[i - 1] !== ' ') SFX.type(); await sleep(speed); } })();
    return () => { dead = true; };
  }, [text, speed, delay]);
  return s;
}

function formatFlag(flagObj) {
  if (typeof flagObj === 'string') return flagObj;
  const name = flagObj.flag || 'FLAG';
  if (flagObj.details) return `${name}: ${flagObj.details}`;
  if (flagObj.gravity_scaling_factor != null) return `Gravity scaling x${Number(flagObj.gravity_scaling_factor).toFixed(3)}`;
  if (flagObj.atmospheric_pressure_gap_pa != null) return `Pressure gap ${Number(flagObj.atmospheric_pressure_gap_pa).toLocaleString()} Pa`;
  if (flagObj.radiation_delta_msv_yr != null) return `Radiation delta ${Number(flagObj.radiation_delta_msv_yr).toFixed(1)} mSv/yr`;
  if (flagObj.thermal_floor_delta_k != null) return `Thermal floor delta ${Number(flagObj.thermal_floor_delta_k).toFixed(1)} K`;
  return name;
}

/* run = {t: target, n: counter}; a new run (even of the same target) restarts the boot sequence */
export default function Panel({ run, open, onClose }) {
  const t = run && run.t;
  const [aspect, setAspect] = useState('composite');
  const [oct, setOct] = useState(2);
  const [w, setW] = useState(init);
  const [ready, setReady] = useState(false);
  const [fs, setFs] = useState(false);
  const [noveltyMasked, setNoveltyMasked] = useState(true);
  const [sites, setSites] = useState([]);
  const [siteIdx, setSiteIdx] = useState(0);
  const [breakdown, setBreakdown] = useState(null);
  const wRef = useRef(w); wRef.current = w;
  const [redraw, setRedraw] = useState(0), barRef = useRef(null);

  useEffect(() => {
    if (!run) return;
    let dead = false;
    setReady(false); setAspect('composite'); setFs(false); setSiteIdx(0); setBreakdown(null);
    (async () => { await sleep(900 + BOOT.length * 22 + 500); if (!dead) setReady(true); })();
    return () => { dead = true; };
  }, [run]);

  useEffect(() => {
    if (!t) return;
    let dead = false;
    loadDiscoveries(t.id, noveltyMasked).then(({ sites: rows }) => {
      if (!dead) { setSites(rows); setSiteIdx(0); }
    });
    return () => { dead = true; };
  }, [t, noveltyMasked]);

  const activeSite = sites[siteIdx] || null;

  useEffect(() => {
    if (!t || !activeSite) { setBreakdown(null); return; }
    let dead = false;
    loadBreakdown(activeSite.site_id, t.id).then(({ breakdown: bd }) => {
      if (!dead) setBreakdown(bd);
    });
    return () => { dead = true; };
  }, [t, activeSite]);

  useEffect(() => { const k = setTimeout(() => setRedraw(x => x + 1), 700); return () => clearTimeout(k); }, [fs]);

  const liveScores = activeSite && activeSite.domain_scores ? activeSite.domain_scores : null;
  const domainPct = id => (liveScores && typeof liveScores[id] === 'number' ? Math.round(liveScores[id] * 100) : (t ? score(t.id, id) : 0));
  const A = ASP.find(a => a.id === aspect);
  const comp = t ? compOf(t.id, w, liveScores) : 0;
  const ph = t && PH[t.body];
  const sc = t ? WIDS.map(a => domainPct(a) / 100) : [];
  const mean = sc.length ? sc.reduce((a, b) => a + b) / 5 : 0;
  const sd = sc.length ? Math.sqrt(sc.reduce((a, b) => a + (b - mean) ** 2, 0) / 5) : 0;
  const sii = activeSite && activeSite.scale_invariance_index != null
    ? Number(activeSite.scale_invariance_index).toFixed(2)
    : (1 - sd * (1 + oct * .12)).toFixed(2);

  const desc = useMemo(() => {
    if (!t) return '';
    if (aspect === 'composite') {
      const prefix = activeSite ? `${activeSite.site_id}: ` : '';
      return `${prefix}Composite match ${compOf(t.id, wRef.current, liveScores).toFixed(0)}%. ${A.d}`;
    }
    const ch0 = breakdown && breakdown.channel_residuals && breakdown.channel_residuals.ch0;
    if (ch0) {
      return `Match ${domainPct(aspect)}%. Earth ch0 mean ${Number(ch0.earth_mean).toFixed(2)}, target ${Number(ch0.target_mean).toFixed(2)}, z-divergence ${Number(ch0.z_divergence).toFixed(2)}. ${A.d}`;
    }
    const r = rnd(hs(t.id + aspect + 'e')), e = (.1 + r() * .8).toFixed(2), m = (.1 + r() * .8).toFixed(2);
    return `Match ${domainPct(aspect)}%. Earth channel mean ${e}, target ${m}, z-divergence ${((m - e) / .18).toFixed(2)}. ${A.d}`;
  }, [t, aspect, ready, activeSite, breakdown]); // eslint-disable-line
  const typed = useTypewriter(ready ? desc : BOOT, ready ? 14 : 22, ready ? 0 : 900);

  const flags = ready
    ? (breakdown && Array.isArray(breakdown.physical_breakdown_flags) && breakdown.physical_breakdown_flags.length
        ? breakdown.physical_breakdown_flags.map(formatFlag)
        : (ph ? [`Gravity scaling x${ph.g} (Earth 9.81 m/s2)`, `Pressure gap ${ph.p.toLocaleString()} Pa (${ph.n})`, `Radiation delta about +${ph.rad} mSv/yr`, `Mean thermal delta ${ph.th} K`, 'Biosphere overprint: Earth analog hosts life'] : []))
    : [];
  const cls = 'side-' + (t && t.body === 'moon' ? 'l' : 'r');
  return (
    <section id="panel" className={[t ? cls : '', open ? 'open' : '', fs ? 'fs' : ''].join(' ').trim()} aria-label="Mission analysis window">
      <div className="pm-h"><div><small>MISSION</small><h2 id="pt">{t ? t.name : ''}</h2></div><div className="pm-st"><i></i>{activeSite ? `LIVE: ${activeSite.site_id}` : 'ANALYSIS ACTIVE'}</div>
        <div className="pm-t"><button id="fs" onClick={() => setFs(f => !f)}>{fs ? 'Exit fullscreen' : 'Fullscreen'}</button><button id="cl" onClick={onClose}>Close</button></div></div>
      <div className="pm-b">
        <nav id="asp" aria-label="Characteristics">
          {ASP.map(a => (
            <button key={a.id} className={'asp' + (ready && aspect === a.id ? ' on' : '')} onClick={() => ready && setAspect(a.id)}>
              <span className="ic"><Icon k={a.id} /></span><span className="nm">{a.n}</span>
              <span className="s">{ready && t ? (a.id === 'composite' ? comp.toFixed(0) : domainPct(a.id)) : '--'}</span>
              {a.id !== 'composite' && <input type="range" min="0" max="100" value={w[a.id]} aria-label={a.n + ' weight'} style={{ '--v': w[a.id] + '%' }}
                onClick={e => e.stopPropagation()} onChange={e => setW({ ...w, [a.id]: +e.target.value })} />}
            </button>))}
        </nav>
        <Zones target={t} site={activeSite} aspect={aspect} oct={oct} weights={w} redrawKey={redraw}>
          <div id="zt">{ready && <><Icon k={aspect} /><span>{A.n}</span></>}</div>
          <div id="oct">{OCT.map((m, i) => <button key={m} className={i === oct ? 'on' : ''} onClick={() => setOct(i)}>{m} m</button>)}</div>
          <div id="lg"><i></i><span><em>Low match</em><em>High match</em></span></div>
        </Zones>
        <aside className="det">
          {sites.length > 0 && (
            <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', font: '11px var(--mono)', color: 'var(--cy)' }}>
                <span>EARTH ANALOG ({sites.length})</span>
                <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', cursor: 'pointer', color: 'var(--tx)' }}>
                  <input type="checkbox" checked={noveltyMasked} onChange={e => setNoveltyMasked(e.target.checked)} />
                  150 km Mask
                </label>
              </div>
              <select
                aria-label="Ranked Earth analog site"
                value={siteIdx}
                onChange={e => setSiteIdx(Number(e.target.value))}
                style={{ width: '100%', padding: '6px 8px', background: '#040a18', color: 'var(--tx)', border: '1px solid var(--ln)', borderRadius: '6px', font: '12px var(--mono)' }}
              >
                {sites.map((s, idx) => (
                  <option key={s.site_id} value={idx}>
                    #{idx + 1} {s.site_id} ({(Number(s.composite_score || 0) * 100).toFixed(1)}%)
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="card"><div className="big"><span id="cs">{ready ? comp.toFixed(0) : '--'}</span><small>COMPOSITE %</small></div>
            <div className="bar"><i id="cb" ref={barRef} style={{ '--bw': ((barRef.current && barRef.current.parentNode.clientWidth) || 300) + 'px', width: ready ? comp + '%' : 0 }}></i></div>
            <small id="sii" style={{ font: '12px var(--mono)', color: 'var(--dim)' }}>{ready ? `SCALE-INVARIANCE INDEX ${sii}` : ''}</small></div>
          <div className="card"><div className="row"><div className="logo" id="lb">{ready && <Icon k={aspect} />}</div><b id="an" style={{ font: '400 14px var(--disp)', letterSpacing: '.1em' }}>{ready ? A.n : ''}</b></div>
            <div id="typed" style={{ marginTop: '12px' }}>{typed}</div></div>
          <div className="card"><ul id="flags">{flags.map(f => <li key={f}>{f}</li>)}</ul></div>
          <div className="card"><small style={{ font: '11px var(--mono)', letterSpacing: '.18em', color: 'var(--cy)' }}>MISSION TEST</small><div id="test">{(activeSite && activeSite.operational_test_protocol) || (t ? t.test : '')}</div></div>
        </aside>
      </div>
    </section>);
}
