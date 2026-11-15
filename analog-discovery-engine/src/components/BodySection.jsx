import { BODIES } from '../content.js';
import { navigate } from '../router.js';
import PlanetSphere from './PlanetSphere.jsx';
import useReveal from './useReveal.js';

export default function BodySection({ body }) {
  const b = BODIES[body];
  const ref = useReveal();
  return (
    <section ref={ref} className="screen body reveal" id={body} aria-label={b.name}>
      <div className="screen__col screen__col--left">
        <p className="eyebrow">{b.kicker}</p>
        <h2 className="display">{b.title}</h2>
      </div>
      <div className="stage stage--body"><PlanetSphere planet={body} /></div>
      <div className="screen__col screen__col--right">
        <p className="copy">{b.text}</p>
        <button className="cta" onClick={() => navigate(`compare/${body}`)}>{b.cta}<span aria-hidden="true"> &rarr;</span></button>
      </div>
    </section>
  );
}
