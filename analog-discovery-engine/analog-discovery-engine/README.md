# Analog Discovery Engine (v1.0, React)

    npm install && npm run dev      # also: npm test | npm run build

Flow: intro -> Earth hero -> Moon / Mars sections -> 3D or 2D -> selection workspace -> results.
Routes (hash): `#/`, `#/compare/:body`, `#/compare/:body/:mode`, `#/compare/:body/:mode/results` (body = moon|mars, mode = 3d|2d).

## Connect the datasets (only thing left)
Everything reads from `src/data/provider.js`: `getComparison({ body, selection })` must resolve to
`{ scores: {a..h: 0..100|null}, thermal: { earth: <equirect image URL>, target: <equirect image URL>, legend: [{code, meaning}] }, texts: {a..h: string} }`.
Characteristic names/units/descriptions: `src/data/characteristics.js`. Until the backend is connected the results page uses clearly labelled preview values (see v6 notes).

## Notes
- Textures are mapped by UV, so a point on the globe equals the same point on the map.
- Background: `components/rays/SideRays.jsx` over a dimmed star image (`public/assets/textures/sky_dark.jpg`).
- Report: downloadable standalone HTML (`src/data/report.js`) plus browser print.


## v6 notes (frontend)
- Thermal engine: `src/data/thermal.js`. Thermal colour = accuracy, weighted by the user's sliders. Moon white, Mars red, Earth blue; codes T1-T5.
- PREVIEW DATA: `fieldAt()` in thermal.js generates placeholder values. Replace it (and the `getComparison` call in ResultsPage) with real per-characteristic data when the backend is merged.
- Movement is always free. Area tool: plain drag draws, right-drag or Shift-drag moves; two-finger pinch zooms.
- Hover 3 s without clicking shows the thermal colour and code at that spot.
