import { HERO } from '../content.js';
import PlanetSphere from './PlanetSphere.jsx';

export default function Hero() {
  return (
    <section className="screen hero" id="earth" aria-label="Earth">
      <div className="screen__col screen__col--left rise rise-1">
        <p className="eyebrow">{HERO.eyebrow}</p>
        <h1 className="display">{HERO.title}</h1>
        {HERO.left.map((t) => <p className="copy" key={t}>{t}</p>)}
      </div>
      <div className="stage stage--hero rise rise-0"><PlanetSphere planet="earth" /></div>
      <div className="screen__col screen__col--right rise rise-2">
        <h2 className="display display--sm">{HERO.rightTitle}</h2>
        {HERO.right.map((t) => <p className="copy" key={t}>{t}</p>)}
      </div>
      <a className="cue rise rise-3" href="#moon" onClick={(e) => { e.preventDefault(); document.getElementById('moon')?.scrollIntoView({ behavior: 'smooth' }); }}>
        <span>{HERO.cue}</span><i aria-hidden="true" />
      </a>
    </section>
  );
}
