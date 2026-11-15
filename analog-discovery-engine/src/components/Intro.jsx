import { useEffect, useRef, useState } from 'react';
import { asset, SKY, LOGO } from '../assets.js';
import { PLANETS } from '../content.js';
import { sfx, music } from '../audio.js';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const preload = (urls, onProgress) => {
  let done = 0;
  return Promise.all(urls.map((u) => new Promise((res) => {
    const img = new Image();
    const fin = () => { onProgress(Math.round((++done / urls.length) * 100)); res(); };
    img.onload = fin; img.onerror = fin; img.src = asset(u);
  })));
};

export default function Intro({ onReveal, onDone }) {
  const [phase, setPhase] = useState('loading');
  const [pct, setPct] = useState(0);
  const [logoOn, setLogoOn] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    preload([...Object.values(PLANETS).map((p) => p.texture), SKY, LOGO], setPct).then(() => setPhase('ready'));
  }, []);

  const begin = async () => {
    if (phase !== 'ready' || started.current) return;
    started.current = true;
    sfx.init(); music.prime();
    const f = reduced() ? 0.3 : 1;
    setPhase('logo');
    await sleep(700 * f); setLogoOn(true);
    await sleep(4000 * f); setLogoOn(false);
    music.start();
    await sleep(2600 * f);
    setPhase('out'); onReveal();
    await sleep(1700 * f); onDone();
  };

  return (
    <div className={`intro${phase === 'out' ? ' is-out' : ''}`}>
      <img className={`intro__logo${logoOn ? ' is-on' : ''}`} src={asset(LOGO)} alt="Black Ops astronaut crew" />
      <button className="intro__begin" onClick={begin} disabled={phase !== 'ready'} style={{ opacity: phase === 'logo' || phase === 'out' ? 0 : undefined }}>
        {phase === 'loading' ? `Initializing surfaces ${pct}%` : 'Click to begin'}
      </button>
    </div>
  );
}
