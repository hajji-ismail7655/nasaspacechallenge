/* ALL visible copy and per-planet visual settings live here. Copy is PLACEHOLDER wording: no numbers, no measurements. */

export const BRAND = 'Analog Discovery Engine';

export const HERO = {
  eyebrow: 'Humanity has always discovered',
  title: 'We have always gone beyond the horizon.',
  left: [
    'We crossed oceans, climbed mountains and mapped the sky long before we knew what waited there. Discovery is the thread that runs through our whole story.',
    'It is time to move on to other planets. Before we do, we look for the places on Earth that come closest to the ground we are about to walk on.',
  ],
  rightTitle: 'Earth is where it begins.',
  right: ['Every comparison here is anchored to the one planet we know completely.', 'Scroll to meet the two worlds we measure it against.'],
  cue: 'Scroll',
};

export const BODIES = {
  moon: {
    key: 'moon', name: 'The Moon', short: 'Moon', kicker: 'First neighbour',
    title: 'The first world we ever looked up at.',
    text: 'The Moon was the first thing humans watched, and the first place we reached. It shows horizons that collide with Earth. Which places here come closest to it?',
    cta: 'Compare with Moon',
  },
  mars: {
    key: 'mars', name: 'Mars', short: 'Mars', kicker: 'Next horizon',
    title: 'The next horizon.',
    text: 'Mars is where the next horizon sits: far away, yet not unfamiliar. Which places on Earth come closest to it?',
    cta: 'Compare with Mars',
  },
};

/* Visual settings only. tilt = axial tilt (deg), spin = rad/s, atmosphere = thin rim glow (null = none). */
export const PLANETS = {
  earth: { name: 'Earth', texture: 'textures/earth.jpg', tilt: 23.4, spin: 0.1, atmosphere: { color: [0.32, 0.56, 1.0], strength: 1.1, power: 2.6, scale: 1.1 } },
  moon: { name: 'Moon', texture: 'textures/moon.jpg', tilt: 6.7, spin: 0.06, atmosphere: null },
  mars: { name: 'Mars', texture: 'textures/mars.jpg', tilt: 25.2, spin: 0.08, atmosphere: { color: [0.86, 0.5, 0.32], strength: 0.3, power: 3.2, scale: 1.06 } },
};

export const MODES = {
  '3d': { key: '3d', label: '3D globe', text: 'Spin the planet and choose a point or an area on its surface.' },
  '2d': { key: '2d', label: '2D map', text: 'Work on the flat map: choose a point or an area, zoom, and move across it.' },
};

/* Interface wording only (instructions, no science). */
export const UI = {
  hintNone: 'Click to select. Rest the cursor 3 seconds to see the thermal accuracy.',
  hintRoll: 'Drag to roll the planet, scroll to zoom.',
  hintPan: 'Drag to move the map, scroll to zoom.',
  hintPointer: 'Click to place a point.',
  hintArea3d: 'Area on: drag from a centre outward to draw a circle. Right-drag or Shift-drag to roll.',
  hintArea2d: 'Area on: drag to draw a rectangle. Right-drag or Shift-drag to move.',
  noSelection: 'Nothing selected yet.',
  compare: 'Compare this selection',
  clear: 'Clear',
};

export const CREDITS = 'BlackOpps · Contributors: Mohammed-Amine Bouaafia | Ilyass Amine | Taha Hamam | Ismail Haji | Mohammed Ilyass Gannouni · All rights reserved 2026 · NASA Space Apps Challenge · Music "Quiet Echoes" by Brioso.';
