import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState } from 'react';
import { asset } from '../assets.js';
import { PLANETS } from '../content.js';
import { makeRect } from '../data/selection.js';

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const RATIO = 3 / 2; // texture is 2304x1536
const MAX_K = 10;

const MapPicker = forwardRef(function MapPicker({ planet, tools, selection, onSelect }, ref) {
  const boxRef = useRef(null);
  const [box, setBox] = useState({ w: 1, h: 1 });
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const live = useRef({}); live.current = { tools, onSelect };
  const drag = useRef(null);

  const fit = box.w / box.h > RATIO ? { w: box.h * RATIO, h: box.h } : { w: box.w, h: box.w / RATIO };

  const bound = (v) => {
    const cw = fit.w * v.k, ch = fit.h * v.k;
    const x = cw > box.w ? clamp(v.x, box.w - cw, 0) : (box.w - cw) / 2;
    const y = ch > box.h ? clamp(v.y, box.h - ch, 0) : (box.h - ch) / 2;
    return { k: v.k, x, y };
  };
  const zoomAt = (f, cx = box.w / 2, cy = box.h / 2) => setView((v) => {
    const k = clamp(v.k * f, 1, MAX_K), r = k / v.k;
    return bound({ k, x: cx - (cx - v.x) * r, y: cy - (cy - v.y) * r });
  });

  useImperativeHandle(ref, () => ({ zoomBy: (f) => zoomAt(f), reset: () => setView(bound({ k: 1, x: 0, y: 0 })) }));

  useLayoutEffect(() => {
    const el = boxRef.current;
    const ro = new ResizeObserver(() => setBox({ w: Math.max(1, el.clientWidth), h: Math.max(1, el.clientHeight) }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  useEffect(() => { setView((v) => bound(v)); }, [box.w, box.h]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const el = boxRef.current;
    const wheel = (e) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top);
    };
    el.addEventListener('wheel', wheel, { passive: false });
    return () => el.removeEventListener('wheel', wheel);
  });

  const toLatLon = (cx, cy) => {
    const r = boxRef.current.getBoundingClientRect();
    const fx = clamp((cx - r.left - view.x) / (fit.w * view.k), 0, 1);
    const fy = clamp((cy - r.top - view.y) / (fit.h * view.k), 0, 1);
    return { lat: 90 - fy * 180, lon: fx * 360 - 180 };
  };

  const down = (e) => {
    boxRef.current.setPointerCapture(e.pointerId);
    const t = live.current.tools;
    drag.current = { x: e.clientX, y: e.clientY, lx: e.clientX, ly: e.clientY, moved: false, start: toLatLon(e.clientX, e.clientY), mode: t.area && !t.pan ? 'area' : t.pan ? 'pan' : 'none' };
  };
  const move = (e) => {
    const d = drag.current; if (!d) return;
    if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 5) d.moved = true;
    if (d.moved && d.mode === 'pan') setView((v) => bound({ ...v, x: v.x + e.clientX - d.lx, y: v.y + e.clientY - d.ly }));
    if (d.moved && d.mode === 'area') live.current.onSelect({ area: makeRect(d.start, toLatLon(e.clientX, e.clientY)) });
    d.lx = e.clientX; d.ly = e.clientY;
  };
  const up = () => {
    const d = drag.current; drag.current = null;
    if (d && !d.moved && live.current.tools.pointer) live.current.onSelect({ point: d.start });
  };

  const px = (lon) => ((lon + 180) / 360) * 100, py = (lat) => ((90 - lat) / 180) * 100;
  const { point, area } = selection;
  const b = area?.bounds;
  const cursor = tools.pan ? 'grab' : tools.pointer || tools.area ? 'crosshair' : 'default';

  return (
    <div ref={boxRef} className="picker picker--map" style={{ cursor }} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
      <div className="map" style={{ width: fit.w, height: fit.h, transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})`, '--k': view.k }}>
        <img src={asset(PLANETS[planet].texture)} alt="" draggable="false" />
        <svg viewBox="0 0 360 180" preserveAspectRatio="none" aria-hidden="true">
          {[...Array(11)].map((_, i) => <line key={`m${i}`} x1={(i + 1) * 30} x2={(i + 1) * 30} y1="0" y2="180" />)}
          {[...Array(5)].map((_, i) => <line key={`p${i}`} y1={(i + 1) * 30} y2={(i + 1) * 30} x1="0" x2="360" />)}
          {b && b.west <= b.east && <rect className="sel" x={b.west + 180} y={90 - b.north} width={b.east - b.west} height={b.north - b.south} />}
          {b && b.west > b.east && <>
            <rect className="sel" x={b.west + 180} y={90 - b.north} width={180 - b.west} height={b.north - b.south} />
            <rect className="sel" x="0" y={90 - b.north} width={b.east + 180} height={b.north - b.south} />
          </>}
        </svg>
        {point && <i className="map__pin" style={{ left: `${px(point.lon)}%`, top: `${py(point.lat)}%` }} />}
      </div>
    </div>
  );
});

export default MapPicker;
