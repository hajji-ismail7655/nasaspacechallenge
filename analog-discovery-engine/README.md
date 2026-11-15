# Analog Discovery Engine (v1.0, React)

    npm install && npm run dev      # also: npm test | npm run build

Flow: intro -> Earth hero -> Moon / Mars sections -> 3D or 2D -> selection workspace -> results.
Routes (hash): `#/`, `#/compare/:body`, `#/compare/:body/:mode`, `#/compare/:body/:mode/results` (body = moon|mars, mode = 3d|2d).

## Connect the datasets (only thing left)
Everything reads from `src/data/provider.js`: `getComparison({ body, selection })` must resolve to
`{ scores: {a..h: 0..100|null}, thermal: { earth: <equirect image URL>, target: <equirect image URL>, legend: [{code, meaning}] }, texts: {a..h: string} }`.
Characteristic names/units/descriptions: `src/data/characteristics.js`. Until connected, the results page shows "—" and no invented data.

## Notes
- Textures are mapped by UV, so a point on the globe equals the same point on the map.
- Background: `components/rays/SideRays.jsx` over a dimmed star image (`public/assets/textures/sky_dark.jpg`).
- Report: downloadable standalone HTML (`src/data/report.js`) plus browser print.
