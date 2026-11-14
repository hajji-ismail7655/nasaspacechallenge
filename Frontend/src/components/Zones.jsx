import { useEffect, useRef } from 'react';
import { lerp, cl, hs } from '../modules/util.js';
import { fbm } from '../modules/noise.js';
import { OCT, score } from '../data.js';

const ramp = v => v < .5 ? [255, lerp(59, 194, v / .5), lerp(77, 51, v / .5)] : [lerp(255, 53, (v - .5) / .5), lerp(194, 208, (v - .5) / .5), lerp(51, 127, (v - .5) / .5)];

/* Demo match map (procedural). Replace the score/noise source with real tiles when the backend is ready. */
function paint(c, t, aspect, oct, w8) {
  const p = c.parentNode, d = Math.min(devicePixelRatio || 1, 2), w = p.clientWidth, h = p.clientHeight;
  if (!w || !t) return;
  c.width = w * d; c.height = h * d; const x = c.getContext('2d'); x.scale(d, d);
  const gw = 84, gh = Math.max(20, Math.round(gw * h / w)), T = document.createElement('canvas'), H = document.createElement('canvas');
  T.width = H.width = gw; T.height = H.height = gh;
  const ti = T.getContext('2d').createImageData(gw, gh), hi = H.getContext('2d').createImageData(gw, gh), id = t.id, fr = 3.2 - oct * .45,
    ids = aspect === 'composite' ? Object.keys(w8) : [aspect], sd = hs(id) % 97;
  for (let j = 0; j < gh; j++) for (let i = 0; i < gw; i++) {
    const u = i / gw, v = j / gw, k = (j * gw + i) * 4, tg = fbm(u * 8 + sd, v * 8, sd * .3, 5);
    ti.data.set([26 + tg * 66, 30 + tg * 72, 48 + tg * 92, 255], k);
    let n = 0, ws = 0;
    for (const a of ids) { const o = hs(id + a) % 100, wt = aspect === 'composite' ? w8[a] + 1 : 1; n += cl(score(id, a) / 100 + (fbm(u * fr + o, v * fr, o * .3, 4) - .45) * 1.15) * wt; ws += wt }
    const q = ramp(n / ws); hi.data.set([q[0], q[1], q[2], 255], k);
  }
  T.getContext('2d').putImageData(ti, 0, 0); H.getContext('2d').putImageData(hi, 0, 0);
  x.fillStyle = '#040a18'; x.fillRect(0, 0, w, h); x.imageSmoothingEnabled = true; x.imageSmoothingQuality = 'high';
  x.globalAlpha = .55; x.drawImage(T, 0, 0, w, h); x.globalAlpha = .7; if ('filter' in x) x.filter = `blur(${3 + oct * 3}px)`; x.drawImage(H, -8, -8, w + 16, h + 16); x.filter = 'none'; x.globalAlpha = 1;
  x.strokeStyle = 'rgba(125,167,217,.1)'; x.lineWidth = 1; for (let i = 1; i < 8; i++) { x.beginPath(); x.moveTo(w * i / 8, 0); x.lineTo(w * i / 8, h); x.moveTo(0, h * i / 8); x.lineTo(w, h * i / 8); x.stroke() }
  x.strokeStyle = 'rgba(255,255,255,.75)'; x.setLineDash([5, 5]); x.beginPath(); x.arc(w / 2, h / 2, Math.min(w, h) * .07, 0, 6.2832);
  x.moveTo(w / 2 - 14, h / 2); x.lineTo(w / 2 + 14, h / 2); x.moveTo(w / 2, h / 2 - 14); x.lineTo(w / 2, h / 2 + 14); x.stroke(); x.setLineDash([]);
  x.fillStyle = '#e8edf4'; x.font = '12px "IBM Plex Mono",monospace'; x.textAlign = 'right'; x.fillText(`${t.lat}, ${t.lon}   ${OCT[oct]} m/px`, w - 14, h - 14);
}

export default function Zones({ target, aspect, oct, weights, redrawKey, children }) {
  const ref = useRef(null);
  useEffect(() => { if (target) paint(ref.current, target, aspect, oct, weights) }, [target, aspect, oct, weights, redrawKey]);
  useEffect(() => { const ro = new ResizeObserver(() => ref.current && target && paint(ref.current, target, aspect, oct, weights)); ro.observe(ref.current.parentNode); return () => ro.disconnect() }, [target, aspect, oct, weights]);
  return <div className="zone"><canvas id="zones" ref={ref} />{children}</div>;
}
