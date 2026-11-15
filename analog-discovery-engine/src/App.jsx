import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { asset, SKY } from './assets.js';
import SideRays from './components/rays/SideRays.jsx';
import { BODIES, MODES } from './content.js';
import { sfx } from './audio.js';
import { useRoute } from './router.js';
import Intro from './components/Intro.jsx';
import TopBar from './components/TopBar.jsx';
import Home from './pages/Home.jsx';
import ModePage from './pages/ModePage.jsx';
import WorkspacePage from './pages/WorkspacePage.jsx';
import ResultsPage from './pages/ResultsPage.jsx';

export default function App() {
  const [revealed, setRevealed] = useState(false);
  const [introGone, setIntroGone] = useState(false);
  const seg = useRoute();
  const homeScroll = useRef(0);

  useEffect(() => { document.documentElement.classList.toggle('locked', !revealed); }, [revealed]);

  useEffect(() => {
    const on = (e) => { if (e.target.closest && e.target.closest('button, a')) sfx.click(); };
    document.addEventListener('pointerdown', on);
    return () => document.removeEventListener('pointerdown', on);
  }, []);

  const [a, body, mode, step] = seg;
  let page = 'home';
  if (a === 'compare' && BODIES[body]) page = mode ? (MODES[mode] ? (step === 'results' ? 'results' : 'workspace') : 'home') : 'mode';

  const prev = useRef('home');
  useEffect(() => {
    const save = () => { if (prev.current === 'home') homeScroll.current = window.scrollY; };
    window.addEventListener('scroll', save, { passive: true });
    return () => window.removeEventListener('scroll', save);
  }, []);
  useLayoutEffect(() => {
    const cameBack = page === 'home' && prev.current !== 'home';
    prev.current = page;
    window.scrollTo({ top: cameBack ? homeScroll.current : 0, behavior: 'instant' });
  }, [page, body, mode]);

  return (
    <div className={`app${revealed ? ' is-revealed' : ''}`}>
      <div className="sky" aria-hidden="true" style={{ backgroundImage: `url(${asset(SKY)})` }} />
      <div className="rays" aria-hidden="true">
        <SideRays rayColor1="#ffffff" rayColor2="#9db4d8" origin="top-right" speed={1.4} intensity={1.1} spread={2} density={5} glow={0.7} saturation={0.5} falloff={1.8} followMouse opacity={0.75} />
      </div>
      {!introGone && <Intro onReveal={() => setRevealed(true)} onDone={() => setIntroGone(true)} />}
      <TopBar />
      <main key={page === 'home' ? 'home' : seg.join('/')} className="page">
        {page === 'home' && <Home />}
        {page === 'mode' && <ModePage body={body} />}
        {page === 'workspace' && <WorkspacePage body={body} mode={mode} />}
        {page === 'results' && <ResultsPage body={body} mode={mode} />}
      </main>
    </div>
  );
}
