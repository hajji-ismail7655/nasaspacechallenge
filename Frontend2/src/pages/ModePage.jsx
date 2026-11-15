import { BODIES, MODES, PLANETS } from '../content.js';
import { asset } from '../assets.js';
import PlanetSphere from '../components/PlanetSphere.jsx';

export default function ModePage({ body }) {
  const b = BODIES[body];
  return (
    <section className="page-pad modepage">
      <a className="back" href="#/">&larr; Back</a>
      <p className="eyebrow">Compare Earth with</p>
      <h1 className="display">{b.name}</h1>
      <p className="copy copy--center">How do you want to work?</p>
      <div className="mode-grid">
        <a className="mode-card" href={`#/compare/${body}/3d`}>
          <div className="mode-card__art mode-card__art--3d"><PlanetSphere planet={body} /></div>
          <h2 className="display display--sm">{MODES['3d'].label}</h2>
          <p className="copy">{MODES['3d'].text}</p>
        </a>
        <a className="mode-card" href={`#/compare/${body}/2d`}>
          <div className="mode-card__art mode-card__art--2d">
            <img src={asset(PLANETS[body].texture)} alt="" />
            <i className="graticule" aria-hidden="true" />
          </div>
          <h2 className="display display--sm">{MODES['2d'].label}</h2>
          <p className="copy">{MODES['2d'].text}</p>
        </a>
      </div>
    </section>
  );
}
