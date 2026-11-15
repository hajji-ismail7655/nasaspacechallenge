import { asset } from './assets.js';

export const sfx = (() => {
  let ctx, buf;
  return {
    init() {
      if (!ctx) {
        ctx = new (window.AudioContext || window.webkitAudioContext)();
        fetch(asset('audio/click.mp3'))
          .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject()))
          .then((b) => ctx.decodeAudioData(b))
          .then((b) => (buf = b))
          .catch(() => {});
      }
      ctx.resume();
    },
    click() {
      if (!ctx) return;
      const t = ctx.currentTime, g = ctx.createGain();
      if (buf) {
        const s = ctx.createBufferSource();
        s.buffer = buf; g.gain.value = 0.5; s.connect(g).connect(ctx.destination); s.start();
        return;
      }
      const o = ctx.createOscillator();
      o.frequency.setValueAtTime(1500, t); o.frequency.exponentialRampToValueAtTime(700, t + 0.05);
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.07, t + 0.004); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.07);
      o.connect(g).connect(ctx.destination); o.start(t); o.stop(t + 0.08);
    },
  };
})();

 export const music = (() => {
  const TARGET = 0.3;
  let on = true, level = 0, timer = 0, started = false, a;

  const ensure = () => {
    if (a) return;
    a = new Audio(asset('audio/quiet-echoes.mp3'));
    a.loop = true; a.preload = 'auto'; a.volume = 0;
    a.addEventListener('ended', () => { a.currentTime = 0; a.play().catch(() => {}); });
    document.addEventListener('visibilitychange', () => {
      if (started && document.visibilityState === 'visible' && a.paused) a.play().catch(() => {});
    });
  };
  const apply = () => { a.volume = on ? level : 0; };
  const fadeIn = () => {
    if (level >= TARGET) { clearInterval(timer); return; }
    level = Math.min(TARGET, level + 0.008); apply();
  };

  return {
    prime() { ensure(); a.play().catch(() => {}); },
    start() {
      ensure(); started = true; level = 0; apply();
      a.currentTime = 0; a.play().catch(() => {});
      clearInterval(timer); timer = setInterval(fadeIn, 100);
    },
    toggle() { ensure(); on = !on; apply(); return on; },
    isOn: () => on,
  };
})();