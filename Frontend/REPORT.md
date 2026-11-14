# Report: React port

Status: the port is done. Visuals and behaviour are unchanged from the HTML version (about 50% of the original job, 3D thermal view done).

## What was done
- The 400-line index.html was split into ES modules by script, copied rather than retyped, and wrapped in init functions.
- The markup is now a React component (`App.jsx`). The CSS is untouched.
- Three.js comes from npm (0.128.0); `GLTFLoader` is imported from `three/examples/jsm`.
- Vite config with relative base, so the build runs from any folder.

## Honest limits
- It is a faithful port, not a rewrite into React state. Scene, audio and mission window still drive the DOM directly (React renders the shell once, and there is no StrictMode on purpose). Turning the mission panel and controls into real components is the next step, and the right moment is when the panel rebuild happens.
- I could not run `npm install` or `vite build` (no network). Instead I bundled the project with esbuild, with Three.js stubbed, and ran it in headless Chromium: no page errors, targets render, panel opens, credits and mute work, no undefined references in any module. The real Three.js scene is still unseen on a real GPU.
- First `npm install && npm run dev` is the true test. Send me a screenshot or the console output if anything fails.

## Still not done (unchanged)
- 2D mode (Moon-Earth, Mars-Earth flat maps); mobile layout; full mission panel rebuild; real backend data; GPU tuning.
- Thermal colours are modelled from albedo, sun angle and latitude, not measured data.
- Earth model is 21 MB.

## Update: look and feel pass
- Fonts: Michroma / Rajdhani / Share Tech Mono replaced with IBM Plex Sans + IBM Plex Mono (plain, technical, NASA-style). Display tracking reduced.
- Colours: neon cyan (#5b9dff) muted to a steel blue (#7da7d9); background near-black; green accent toned down. NASA blue (#0b3d91) kept for fills.
- Glow effects (text/box glows on panel, map frame, switches, scrollbars, status dot) removed; only subtle inset depth remains.
- Thermal legend was already a vertical jet-style bar like your reference image (purple to red, kelvin ticks), so it is unchanged.
- Earth atmosphere rim slightly dimmer.

## Not verified
- Realism of Earth/Moon/Mars still cannot be judged without a real GPU render. Nothing visual about the planets was changed this round except the atmosphere rim brightness. Send a screenshot of the planet view.
- Stopped at about 50% of the original job plus the 3D thermal view. 2D mode, mobile layout, panel rebuild, real data: not started.

## Update: 2D mode (done)
- New "DIMENSION: 3D | 2D map" switch. In 2D the planets are hidden and two flat equirectangular maps appear side by side, with a "COMPARE: Moon - Earth | Mars - Earth" switch.
- Visual: the surface textures with a 30-degree grid. Earth's map was extracted from the Earth model (`assets/textures/earth_map.jpg`).
- Thermal: the same modelled-temperature physics as the 3D shader, computed per pixel for a Sun over the map centre. The Visual/Thermal switch, the kelvin legend and the Shared/Each-planet scale all drive the 2D maps too.
- Code: `src/modules/flat.js`. Its temperature constants are a copy of those in `scene.js`; change both together.
- Tested: headless Chromium, no page errors; screenshots of both pairs in thermal mode look right. Earth ocean/land detection uses the map's fill colour, so a few coast pixels may be misclassified.
- Limits: Earth clouds are not modelled in 2D; mobile layout skipped as you asked; Mars thermal is smooth because the Mars texture has low contrast; still modelled, not measured.

## Progress
About 55% overall. Remaining: mission panel rebuild, real data hookup, real-GPU tuning of the 3D planets, optional real thermal datasets.

## Update: mission panel rebuilt as React components (done)
- Targets dock, mission window, match map, credits popover and the link status are now real React components with state (no more DOM poking). `mission.js` is gone.
- Same behaviour as before: boot typing sequence, composite and per-aspect scores, weight sliders, scale buttons (30-480 m), fullscreen, Esc to close, click a planet in 3D to open its targets.
- Layout: panel widened (up to 1320 px) so the match map is no longer cramped; scale buttons moved to the bottom of the map so they stop covering its title.
- Backend hook: `src/data.js` -> `loadTargets()`. Scores and the map are still DEMO data generated from the target id. When the backend schema exists, replace `score()` and the noise in `Zones.jsx`.
- Tested in headless Chromium (3D stubbed): chips, run button state, panel open, slider and aspect changes, fullscreen, Esc, planet-click path, no page errors. Visually checked a screenshot.
- Not done: real data, real-GPU tuning, mobile layout (skipped by request).

## Progress: about 60% overall. Stopping here.

## Update: visual polish (layout)
- Laptop screens (1366x768): headline, the three control switches, the temperature legend and the targets dock no longer overlap. Headline is capped to 36% of the width; switch icons are hidden below 1600 px; the legend note hides on short screens.
- Checked with screenshots at 1366x768 (and 1920x1080 / 1440x900 earlier). 3D planets are not visible in my tests (no Three.js offline), so planet size, position vs the legend, Earth realism and labels remain UNVERIFIED. Send a screenshot of the planet view to tune them.

## Update: small polish
- Intro shows a loading percentage while the 21 MB Earth model downloads (only when the server reports the file size; otherwise it keeps the plain text).
- Visible keyboard focus ring on all buttons, sliders and switches.
- Credits: "Moon model" and "Mars model" are listed, but the zip only contains Moon and Mars textures. Confirm the real sources and correct the Credits text (in App.jsx).
