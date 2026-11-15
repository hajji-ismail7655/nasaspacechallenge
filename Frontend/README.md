# Analog Discovery Engine: React + Vite front end

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # static site in dist/ (base './', works from any sub-path)
```

Three.js is pinned to **0.128.0** on purpose: the shaders and encoding settings were tuned against r128.
Backend: set `window.ANALOG_API` (default `http://localhost:8000`). Without it the page runs on demo data.

## Layout
- `src/App.jsx`: page shell + state (targets, selection, credits, mission run)
- `src/components/`: `Dock`, `Panel` (mission window), `Zones` (match map), `Icon`
- `src/data.js`: aspects, targets, demo scoring and the single backend hook `loadTargets()` (GET `{API}/targets`)
- `src/styles.css`: all styles, unchanged
- `src/modules/util.js`, `noise.js`: helpers and procedural noise
- `src/modules/scene.js`: Three.js scene (planets, Earth GLB, thermal view, Moon orbit, stars)
- `src/modules/audio.js`: click sound and the endless music loop
- `src/modules/boot.js`: start-up
- `public/assets/`: models, textures, audio, logo (fetched at `assets/...`)
