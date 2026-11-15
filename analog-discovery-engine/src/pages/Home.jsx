import Hero from '../components/Hero.jsx';
import BodySection from '../components/BodySection.jsx';
import { CREDITS } from '../content.js';

export default function Home() {
  return (
    <>
      <Hero />
      <BodySection body="moon" />
      <BodySection body="mars" />
      <footer className="credits">{CREDITS}</footer>
    </>
  );
}
