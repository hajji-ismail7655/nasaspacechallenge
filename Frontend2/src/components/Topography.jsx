import { useEffect, useRef } from 'react';

/* Slow drifting contour lines. Own light implementation of the Topography background:
   a low-res field is drawn as band edges and scaled up. Page background only, never on the planets. */
export default function Topography({ lineColor = '#9db4d8', opacity = 0.22, speed = 0.25, scale = 1, step = 0.16 }) {
  const ref = useRef(null);
  useEffect(() => {
    const cv = ref.current, ctx = cv.getContext('2d');
    const w = 200, h = 112; cv.width = w; cv.height = h;
    const rgb = lineColor.replace('#', '').match(/../g).map((x) => parseInt(x, 16));
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const img = ctx.createImageData(w, h), f = new Float32Array(w * h);
    let raf = 0, last = 0, t = 0, alive = true;
    const draw = () => {
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
        const u = (x / w) * 3.2 * scale, v = (y / h) * 1.8 * scale;
        f[y * w + x] = Math.sin(u * 2.1 + t) + Math.sin(v * 2.7 - t * 0.8) + Math.sin((u + v) * 1.7 + t * 0.6) + 0.6 * Math.sin(Math.hypot(u - 1.6, v - 0.9) * 3.4 - t);
      }
      for (let i = 0; i < f.length; i++) {
        const a = Math.floor(f[i] / step), e = (i % w < w - 1 && a !== Math.floor(f[i + 1] / step)) || (i + w < f.length && a !== Math.floor(f[i + w] / step));
        img.data[i * 4] = rgb[0]; img.data[i * 4 + 1] = rgb[1]; img.data[i * 4 + 2] = rgb[2]; img.data[i * 4 + 3] = e ? 255 : 0;
      }
      ctx.putImageData(img, 0, 0);
    };
    const loop = (now) => {
      if (!alive) return; raf = requestAnimationFrame(loop);
      if (document.hidden || now - last < 66) return; // about 15 fps
      t += (now - last) / 1000 * speed; last = now; draw();
    };
    draw(); if (!reduced) raf = requestAnimationFrame(loop);
    return () => { alive = false; cancelAnimationFrame(raf); };
  }, [lineColor, speed, scale, step]);
  return <canvas ref={ref} className="topo" aria-hidden="true" style={{ opacity }} />;
}
