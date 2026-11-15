import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { asset } from '../assets.js';
import { PLANETS } from '../content.js';

const FOV = 28, CAM_Z = 4.8;
const SUN = new THREE.Vector3(-0.75, 0.28, 1).normalize();

const GLOW_VERT = `
varying vec3 vN; varying vec3 vW;
void main(){
  vN = normalize(normalMatrix * normal);
  vW = normalize(mat3(modelMatrix) * normal);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;
const GLOW_FRAG = `
uniform vec3 uColor; uniform float uPower; uniform float uStrength; uniform float uLimb; uniform vec3 uSun;
varying vec3 vN; varying vec3 vW;
void main(){
  float c = clamp(abs(vN.z) / uLimb, 0.0, 1.0);
  float day = smoothstep(-0.35, 0.55, dot(normalize(vW), uSun));
  float a = pow(c, uPower) * day * uStrength;
  gl_FragColor = vec4(uColor, a);
}`;

export default function PlanetSphere({ planet, className = '', onReady, textureUrl }) {
  const rootRef = useRef(null);
  const canvasRef = useRef(null);
  const cfg = PLANETS[planet];

  useEffect(() => {
    const root = rootRef.current, canvas = canvasRef.current;
    if (!root || !canvas || !cfg) return;

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setClearColor(0x000000, 0);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 50);
    camera.position.set(0, 0, CAM_Z);

    const sun = new THREE.DirectionalLight(0xffffff, Math.PI);
    sun.position.copy(SUN).multiplyScalar(10);
    scene.add(sun, new THREE.AmbientLight(0xffffff, 0.05));

    const tilt = new THREE.Group();
    tilt.rotation.z = -THREE.MathUtils.degToRad(cfg.tilt);
    scene.add(tilt);

    const geometry = new THREE.SphereGeometry(1, 128, 128);
    const material = new THREE.MeshStandardMaterial({ roughness: 1, metalness: 0, color: 0x000000 });
    const globe = new THREE.Mesh(geometry, material);
    globe.rotation.y = -Math.PI / 2;
    tilt.add(globe);

    let glow = null;
    if (cfg.atmosphere) {
      const a = cfg.atmosphere;
      glow = new THREE.Mesh(
        new THREE.SphereGeometry(a.scale, 96, 96),
        new THREE.ShaderMaterial({
          vertexShader: GLOW_VERT, fragmentShader: GLOW_FRAG, side: THREE.BackSide, transparent: true, depthWrite: false,
          blending: THREE.AdditiveBlending,
          uniforms: {
            uColor: { value: new THREE.Color(a.color[0], a.color[1], a.color[2]) },
            uPower: { value: a.power }, uStrength: { value: a.strength },
            uLimb: { value: Math.sqrt(1 - 1 / (a.scale * a.scale)) }, uSun: { value: SUN.clone() },
          },
        }),
      );
      tilt.add(glow);
    }

    let texture = null, disposed = false;
    new THREE.TextureLoader().load(
      textureUrl || asset(cfg.texture),
      (t) => {
        if (disposed) { t.dispose(); return; }
        t.colorSpace = THREE.SRGBColorSpace;
        t.anisotropy = renderer.capabilities.getMaxAnisotropy();
        texture = t;
        material.map = t; material.color.set(0xffffff); material.needsUpdate = true;
        root.dataset.ready = 'true';
        onReady && onReady();
        wake();
      },
      undefined,
      () => { root.dataset.ready = 'error'; },
    );

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let raf = 0, last = 0, visible = true, pageVisible = document.visibilityState !== 'hidden';

    const resize = () => {
      const w = Math.max(1, root.clientWidth), h = Math.max(1, root.clientHeight);
      renderer.setSize(w, h, false);
      camera.aspect = w / h; camera.updateProjectionMatrix();
    };
    const frame = (now) => {
      raf = 0;
      const dt = Math.min(0.05, (now - last) / 1000 || 0); last = now;
      globe.rotation.y += dt * cfg.spin * (reduced ? 0.3 : 1);
      renderer.render(scene, camera);
      if (visible && pageVisible) raf = requestAnimationFrame(frame);
    };
    function wake() {
      if (raf || disposed || !visible || !pageVisible) return;
      last = performance.now(); raf = requestAnimationFrame(frame);
    }

    const ro = new ResizeObserver(() => { resize(); wake(); });
    ro.observe(root);
    const io = new IntersectionObserver((e) => { visible = e.some((x) => x.isIntersecting); wake(); });
    io.observe(root);
    const onVis = () => { pageVisible = document.visibilityState !== 'hidden'; wake(); };
    document.addEventListener('visibilitychange', onVis);
    resize(); wake();

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      ro.disconnect(); io.disconnect();
      document.removeEventListener('visibilitychange', onVis);
      geometry.dispose(); material.dispose();
      if (glow) { glow.geometry.dispose(); glow.material.dispose(); }
      if (texture) texture.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
    };
  }, [planet, textureUrl]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div ref={rootRef} className={`planet ${className}`} data-planet={planet} data-ready="false">
      <canvas ref={canvasRef} aria-hidden="true" />
    </div>
  );
}
