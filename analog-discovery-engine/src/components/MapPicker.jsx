import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState } from 'react';
import { asset } from '../assets.js';
import { PLANETS } from '../content.js';
import { makeRect } from '../data/selection.js';

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const RATIO = 2; // textures are 2:1 equirectangular (3072x1536)
const MAX_K = 16;

const MapPicker = forwardRef(function MapPicker({ planet, tools, selection, onSelect, dwell, onDwell, mapSrc }, ref) {
  const boxRef = useRef(null);
  const [box, setBox] = useState({ w: 1, h: 1 });
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const live = useRef({}); live.current = { tools, onSelect, onDwell };
  const drag = useRef(null);
  const ptrs = useRef(new Map()), pinch = useRef(0);
  const dw = useRef({ timer: 0, shown: false, x: -99, y: -99 });
  const stopDwell = () => { clearTimeout(dw.current.timer); if (dw.current.shown) { dw.current.shown = false; live.current.onDwell?.(null); } };
  useEffect(() => () => clearTimeout(dw.current.timer), []);

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

  /* movement is always free: Area takes the plain left-drag; right-drag or Shift-drag always moves the map */
  const down = (e) => {
    boxRef.current.setPointerCapture(e.pointerId); stopDwell(); ptrs.current.set(e.pointerId, [e.clientX, e.clientY]);
    if (ptrs.current.size === 2) { const [a, b] = [...ptrs.current.values()]; pinch.current = Math.hypot(a[0] - b[0], a[1] - b[1]); drag.current = null; return; }
    const t = live.current.tools;
    drag.current = { x: e.clientX, y: e.clientY, lx: e.clientX, ly: e.clientY, moved: false, start: toLatLon(e.clientX, e.clientY), button: e.button, mode: t.area && e.button === 0 && !e.shiftKey ? 'area' : 'pan' };
  };
  const move = (e) => {
    if (ptrs.current.has(e.pointerId)) ptrs.current.set(e.pointerId, [e.clientX, e.clientY]);
    if (ptrs.current.size === 2) {
      const [a, b] = [...ptrs.current.values()], dist = Math.hypot(a[0] - b[0], a[1] - b[1]), r = boxRef.current.getBoundingClientRect();
      if (pinch.current) zoomAt(dist / pinch.current, (a[0] + b[0]) / 2 - r.left, (a[1] + b[1]) / 2 - r.top);
      pinch.current = dist; return;
    }
    const d = drag.current;
    if (!d) {
      const w = dw.current;
      if (Math.hypot(e.clientX - w.x, e.clientY - w.y) > 4) {
        stopDwell(); w.x = e.clientX; w.y = e.clientY;
        const cx = e.clientX, cy = e.clientY;
        w.timer = setTimeout(() => { w.shown = true; live.current.onDwell?.({ ...toLatLon(cx, cy), x: cx, y: cy }); }, 3000);
      }
      return;
    }
    if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 5) d.moved = true;
    if (d.moved && d.mode === 'pan') setView((v) => bound({ ...v, x: v.x + e.clientX - d.lx, y: v.y + e.clientY - d.ly }));
    if (d.moved && d.mode === 'area') live.current.onSelect({ area: makeRect(d.start, toLatLon(e.clientX, e.clientY)) });
    d.lx = e.clientX; d.ly = e.clientY;
  };
  const up = (e) => {
    ptrs.current.delete(e.pointerId); if (ptrs.current.size < 2) pinch.current = 0;
    const d = drag.current; drag.current = null;
    if (d && !d.moved && d.button === 0 && live.current.tools.pointer) live.current.onSelect({ point: d.start });
    if (e?.clientX != null) { dw.current.x = e.clientX; dw.current.y = e.clientY; }
  };

  const px = (lon) => ((lon + 180) / 360) * 100, py = (lat) => ((90 - lat) / 180) * 100;
  const { point, area } = selection;
  const b = area?.bounds;
  const cursor = tools.area ? 'crosshair' : 'grab';

  return (
    <div ref={boxRef} className="picker picker--map" style={{ cursor }} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onPointerLeave={stopDwell} onContextMenu={(e) => e.preventDefault()}>
      <div className="map" style={{ width: fit.w, height: fit.h, transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})`, '--k': view.k }}>
        <img src={mapSrc || asset(PLANETS[planet].texture)} alt="" draggable="false" />
        <svg viewBox="0 0 360 180" preserveAspectRatio="none" aria-hidden="true">
          {[...Array(11)].map((_, i) => <line key={`m${i}`} x1={(i + 1) * 30} x2={(i + 1) * 30} y1="0" y2="180" />)}
          {[...Array(5)].map((_, i) => <line key={`p${i}`} y1={(i + 1) * 30} y2={(i + 1) * 30} x1="0" x2="360" />)}
          {b && b.west <= b.east && <rect className="sel" x={b.west + 180} y={90 - b.north} width={b.east - b.west} height={b.north - b.south} />}
          {b && b.west > b.east && <>
            <rect className="sel" x={b.west + 180} y={90 - b.north} width={180 - b.west} height={b.north - b.south} />
            <rect className="sel" x="0" y={90 - b.north} width={b.east + 180} height={b.north - b.south} />
          </>}
        </svg>
        {dwell && <i className="map__dwell" style={{ left: `${px(dwell.lon)}%`, top: `${py(dwell.lat)}%`, background: dwell.color }} />}
        {point && <i className="map__pin" style={{ left: `${px(point.lon)}%`, top: `${py(point.lat)}%` }} />}
      </div>
    </div>
  );
});

export default MapPicker;
