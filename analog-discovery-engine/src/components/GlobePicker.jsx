import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import * as THREE from 'three';
import { asset } from '../assets.js';
import { PLANETS } from '../content.js';
import { toVec, angleDeg, makeCap } from '../data/selection.js';

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const DIST = 4.9, MIN = 1.5, MAX = 8;

const ringPoints = (lat, lon, radiusDeg, n = 128, lift = 1.004) => {
  const c = new THREE.Vector3(...toVec(lat, lon)).normalize();
  const up = Math.abs(c.y) > 0.95 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0);
  const e1 = new THREE.Vector3().crossVectors(c, up).normalize();
  const e2 = new THREE.Vector3().crossVectors(c, e1);
  const r = (radiusDeg * Math.PI) / 180;
  return { c, pts: Array.from({ length: n }, (_, i) => {
    const a = (i / n) * Math.PI * 2;
    return c.clone().multiplyScalar(Math.cos(r)).add(e1.clone().multiplyScalar(Math.cos(a) * Math.sin(r))).add(e2.clone().multiplyScalar(Math.sin(a) * Math.sin(r))).normalize().multiplyScalar(lift);
  }) };
};

const disposeGroup = (g) => g.traverse((o) => { o.geometry?.dispose(); o.material?.dispose(); });

const buildOverlay = ({ point, area, dwell }) => {
  const g = new THREE.Group();
  const line = (pts, opacity = 1) => {
    const l = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity, depthTest: false }));
    l.renderOrder = 5; return l;
  };
  if (area?.shape === 'cap') {
    const { c, pts } = ringPoints(area.center.lat, area.center.lon, area.radiusDeg);
    g.add(line(pts));
    const fan = [c.clone().multiplyScalar(1.002), ...pts.map((p) => p.clone().multiplyScalar(1.002 / 1.004))];
    const geo = new THREE.BufferGeometry().setFromPoints(fan);
    const idx = []; for (let i = 1; i <= pts.length; i++) idx.push(0, i, i === pts.length ? 1 : i + 1);
    geo.setIndex(idx);
    g.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.14, side: THREE.DoubleSide, depthWrite: false })));
  }
  if (dwell) {
    const { c, pts } = ringPoints(dwell.lat, dwell.lon, 3.2, 64, 1.003);
    const fan = [c.clone().multiplyScalar(1.003), ...pts.map((p) => p.clone().multiplyScalar(1.003 / 1.003))];
    const geo = new THREE.BufferGeometry().setFromPoints(fan);
    const idx = []; for (let i = 1; i <= pts.length; i++) idx.push(0, i, i === pts.length ? 1 : i + 1);
    geo.setIndex(idx);
    g.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: new THREE.Color(dwell.color), side: THREE.DoubleSide, transparent: true, opacity: 0.92, depthWrite: false })));
    g.add(line(pts, 0.9));
  }
  if (point) {
    const v = new THREE.Vector3(...toVec(point.lat, point.lon)).normalize();
    const dot = new THREE.Mesh(new THREE.SphereGeometry(0.014, 16, 16), new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: false }));
    dot.position.copy(v.clone().multiplyScalar(1.006)); dot.renderOrder = 6; g.add(dot);
    g.add(line(ringPoints(point.lat, point.lon, 2.6, 48, 1.006).pts));
  }
  return g;
};

const GlobePicker = forwardRef(function GlobePicker({ planet, tools, selection, onSelect, dwell, onDwell }, ref) {
  const rootRef = useRef(null), canvasRef = useRef(null);
  const live = useRef({}); live.current = { tools, selection, onSelect, dwell, onDwell };
  const api = useRef({});
  useImperativeHandle(ref, () => ({ zoomBy: (f) => api.current.zoomBy?.(f), reset: () => api.current.reset?.() }), []);
  const cfg = PLANETS[planet];

  useEffect(() => { api.current.overlay?.(selection, dwell); }, [selection, dwell]);
  useEffect(() => { if (canvasRef.current) canvasRef.current.style.cursor = tools.area ? 'crosshair' : 'grab'; }, [tools]);

  useEffect(() => {
    const root = rootRef.current, canvas = canvasRef.current;
    if (!root || !canvas || !cfg) return;
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 50);
    camera.position.set(0, 0, DIST);
    const sun = new THREE.DirectionalLight(0xffffff, 2.8); sun.position.set(-2.5, 1.6, 4);
    scene.add(sun, new THREE.AmbientLight(0xffffff, 0.45));

    const globe = new THREE.Object3D(); globe.rotation.order = 'YXZ'; scene.add(globe);
    const geometry = new THREE.SphereGeometry(1, 128, 128);
    const material = new THREE.MeshStandardMaterial({ roughness: 1, metalness: 0, color: 0x000000 });
    const mesh = new THREE.Mesh(geometry, material); globe.add(mesh);

    let disposed = false, texture = null, overlay = null;
    new THREE.TextureLoader().load(asset(cfg.texture), (t) => {
      if (disposed) { t.dispose(); return; }
      t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = renderer.capabilities.getMaxAnisotropy();
      texture = t; material.map = t; material.color.set(0xffffff); material.needsUpdate = true; root.dataset.ready = 'true';
    });

    const st = { yaw: -1.2, pitch: 0.25, vy: 0, vp: 0, dist: DIST, target: DIST };
    const ray = new THREE.Raycaster();
    const hit = (cx, cy) => {
      const r = canvas.getBoundingClientRect();
      ray.setFromCamera(new THREE.Vector2(((cx - r.left) / r.width) * 2 - 1, -(((cy - r.top) / r.height) * 2 - 1)), camera);
      const h = ray.intersectObject(mesh)[0];
      return h?.uv ? { lat: h.uv.y * 180 - 90, lon: h.uv.x * 360 - 180 } : null;
    };

    const ptrs = new Map(); let pinch = 0;
    const pdist = () => { const [a, b] = [...ptrs.values()]; return Math.hypot(a[0] - b[0], a[1] - b[1]); };
    let drag = null, shown = false, timer = 0, hx = -99, hy = -99;
    const stopDwell = () => { clearTimeout(timer); if (shown) { shown = false; live.current.onDwell?.(null); } };
    const startDwell = (x, y) => {
      stopDwell(); hx = x; hy = y;
      timer = setTimeout(() => { const h = hit(x, y); if (h) { shown = true; live.current.onDwell?.({ ...h, x, y }); } }, 3000);
    };
    const down = (e) => {
      canvas.setPointerCapture(e.pointerId); stopDwell(); ptrs.set(e.pointerId, [e.clientX, e.clientY]);
      if (ptrs.size === 2) { pinch = pdist(); drag = null; return; }
      const t = live.current.tools, h = hit(e.clientX, e.clientY);
      /* movement is always free: Area only takes the plain left-drag; right-drag or Shift-drag always rolls the planet */
      drag = { x: e.clientX, y: e.clientY, lx: e.clientX, ly: e.clientY, moved: false, start: h, button: e.button, mode: t.area && e.button === 0 && !e.shiftKey ? 'area' : 'rotate' };
      st.vy = st.vp = 0;
    };
    const move = (e) => {
      if (ptrs.has(e.pointerId)) ptrs.set(e.pointerId, [e.clientX, e.clientY]);
      if (ptrs.size === 2) { const d = pdist(); if (pinch) api.current.zoomBy(d / pinch); pinch = d; return; }
      if (!drag) { if (Math.hypot(e.clientX - hx, e.clientY - hy) > 4) startDwell(e.clientX, e.clientY); return; }
      if (Math.hypot(e.clientX - drag.x, e.clientY - drag.y) > 5) drag.moved = true;
      if (drag.mode === 'rotate' && drag.moved) {
        const k = 0.0052 * (st.dist / DIST);
        st.vy = (e.clientX - drag.lx) * k; st.vp = (e.clientY - drag.ly) * k;
        st.yaw += st.vy; st.pitch = clamp(st.pitch + st.vp, -1.4, 1.4);
      } else if (drag.mode === 'area' && drag.moved && drag.start) {
        const h = hit(e.clientX, e.clientY);
        if (h) live.current.onSelect({ area: makeCap(drag.start, Math.max(0.5, angleDeg(toVec(drag.start.lat, drag.start.lon), toVec(h.lat, h.lon)))) });
      }
      drag.lx = e.clientX; drag.ly = e.clientY;
    };
    const up = (e) => {
      ptrs.delete(e.pointerId); if (ptrs.size < 2) pinch = 0;
      if (drag && !drag.moved && drag.button === 0 && live.current.tools.pointer && drag.start) live.current.onSelect({ point: drag.start });
      drag = null; if (e?.clientX != null) { hx = e.clientX; hy = e.clientY; }
    };
    const wheel = (e) => { e.preventDefault(); stopDwell(); api.current.zoomBy(e.deltaY < 0 ? 1.12 : 1 / 1.12); };
    const keys = (e) => {
      if (/INPUT|TEXTAREA/.test(e.target.tagName)) return;
      const k = 0.06 * (st.dist / DIST), m = { ArrowLeft: [k, 0], ArrowRight: [-k, 0], ArrowUp: [0, k], ArrowDown: [0, -k] }[e.key];
      if (m) { e.preventDefault(); stopDwell(); st.yaw += m[0]; st.pitch = clamp(st.pitch + m[1], -1.4, 1.4); }
    };
    const menu = (e) => e.preventDefault();
    canvas.addEventListener('pointerdown', down); canvas.addEventListener('pointermove', move);
    canvas.addEventListener('pointerup', up); canvas.addEventListener('pointercancel', up); canvas.addEventListener('pointerleave', stopDwell);
    canvas.addEventListener('wheel', wheel, { passive: false }); canvas.addEventListener('contextmenu', menu); window.addEventListener('keydown', keys);

    api.current = {
      zoomBy: (f) => { st.target = clamp(st.target / f, MIN, MAX); },
      reset: () => { st.target = DIST; st.pitch = 0.25; },
      overlay: (sel, dw) => {
        if (overlay) { globe.remove(overlay); disposeGroup(overlay); overlay = null; }
        if ((sel && (sel.point || sel.area)) || dw) { overlay = buildOverlay({ point: sel?.point, area: sel?.area, dwell: dw }); globe.add(overlay); }
      },
    };
    api.current.overlay(live.current.selection, live.current.dwell);

    const resize = () => {
      const w = Math.max(1, root.clientWidth), h = Math.max(1, root.clientHeight);
      renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize); ro.observe(root); resize();

    let raf = 0, last = performance.now();
    const loop = (now) => {
      raf = requestAnimationFrame(loop);
      const dt = Math.min(0.05, (now - last) / 1000); last = now;
      if (!drag) {
        st.yaw += st.vy; st.pitch = clamp(st.pitch + st.vp, -1.4, 1.4); st.vy *= 0.94; st.vp *= 0.94;
      }
      st.dist += (st.target - st.dist) * (1 - Math.exp(-dt * 8));
      camera.position.z = st.dist;
      globe.rotation.set(st.pitch, st.yaw, 0);
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(loop);

    return () => {
      disposed = true; cancelAnimationFrame(raf); ro.disconnect(); clearTimeout(timer);
      canvas.removeEventListener('pointerdown', down); canvas.removeEventListener('pointermove', move);
      canvas.removeEventListener('pointerup', up); canvas.removeEventListener('pointercancel', up);
      canvas.removeEventListener('wheel', wheel); canvas.removeEventListener('pointerleave', stopDwell); canvas.removeEventListener('contextmenu', menu); window.removeEventListener('keydown', keys);
      if (overlay) disposeGroup(overlay);
      geometry.dispose(); material.dispose(); texture?.dispose(); renderer.dispose(); renderer.forceContextLoss();
      api.current = {};
    };
  }, [planet]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div ref={rootRef} className="picker picker--globe" data-ready="false">
      <canvas ref={canvasRef} />
    </div>
  );
});

export default GlobePicker;
