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
  const OVERLAP = 4, TARGET = 0.3;
  let on = true, level = 0, running = false, timer = 0, P, Q;

  const make = () => {
    const a = new Audio(asset('audio/quiet-echoes.mp3'));
    a.preload = 'auto'; a.volume = on ? level : 0;
    a.onended = () => { if (a !== P) return; if (Q.paused) play(Q); swap(); };
    return a;
  };
  const ensure = () => { if (!P) { P = make(); Q = make(); } };
  const apply = () => { P.volume = Q.volume = on ? level : 0; };
  const play = (el) => el.play().catch(() => {});
  const swap = () => { const old = P; P = Q; Q = make(); old.onended = null; try { old.pause(); } catch {} };
  const tick = () => {
    if (!running) return;
    if (level < TARGET) { level = Math.min(TARGET, level + 0.008); apply(); }
    const d = P.duration;
    if (d && isFinite(d) && !P.paused && d - P.currentTime <= OVERLAP && Q.paused) play(Q);
  };

  return {
    prime() { ensure(); P.play().catch(() => {}); },
    start() {
      ensure(); level = 0; apply();
      if (P.currentTime > 0.05) { P.onended = null; P = make(); }
      play(P); running = true; clearInterval(timer); timer = setInterval(tick, 100);
    },
    toggle() { ensure(); on = !on; apply(); return on; },
    isOn: () => on,
  };
})();
