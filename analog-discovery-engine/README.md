# Analog Discovery Engine (v1.0, React)

    npm install && npm run dev      # also: npm test | npm run build

Flow: intro -> Earth hero -> Moon / Mars sections -> 3D or 2D -> selection workspace -> results.
Routes (hash): `#/`, `#/compare/:body`, `#/compare/:body/:mode`, `#/compare/:body/:mode/results` (body = moon|mars, mode = 3d|2d).

## Backend
Start the FastAPI service from the repository root with `uvicorn app.main:app
--host 0.0.0.0 --port 8000`. Set `VITE_API_BASE_URL` when it is hosted at a
different address; the default is `http://localhost:8000`.

The frontend reads five domain scores for the selected body's fixed targets.
Picker coordinates are visual context; arbitrary points and areas are not
scored by the current precomputed sweep. The API does not serve thermal grids,
so the frontend leaves thermal overlays disabled and reports that limitation.

## Notes
- Textures are mapped by UV, so a point on the globe equals the same point on the map.
- Background: `components/rays/SideRays.jsx` over a dimmed star image (`public/assets/textures/sky_dark.jpg`).
- Report: downloadable standalone HTML (`src/data/report.js`) plus browser print.
