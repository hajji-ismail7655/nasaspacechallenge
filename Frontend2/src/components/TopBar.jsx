import { useState } from 'react';
import { BRAND } from '../content.js';
import { music } from '../audio.js';

export default function TopBar() {
  const [on, setOn] = useState(music.isOn());
  return (
    <header className="topbar">
      <a className="topbar__brand" href="#/">{BRAND}</a>
      <button className="topbar__sound" aria-pressed={on} onClick={() => setOn(music.toggle())}>{on ? 'Sound on' : 'Sound off'}</button>
    </header>
  );
}
