# Cross-Planetary Terrestrial Analog Discovery Engine

This project ranks 14 Earth sites against eight fixed Moon and Mars targets.
Python prepares tiles and serves the API, five C++20 modules compute similarity,
and two React frontends present the ranked results.

## Project layout

| Directory | Purpose |
| --- | --- |
| pipelines/ | Stage raw channel grids and record data provenance. |
| processor/ | Standardize grids into five-octave PTILE files. |
| OptiAlgo/ and BestAlgo/ | Five C++ scoring modules and Python references. |
| fusion/ | Score Earth/target pairs and produce rankings. |
| app/ | FastAPI service for discoveries, heatmaps, and breakdowns. |
| analog-discovery-engine/ | Frontend1, the primary guided UI. |
| Frontend2/ | Alternate UI with 2D maps and 3D globes. |

Generated inputs and results live in data_lake/, which Git ignores. A fresh
clone has no scored results until you run the data pipeline below.

## Requirements and setup

Use a Linux or WSL Bash terminal for Python and C++. On Windows, open the
repository in WSL; a Windows path beginning with C:\ appears under /mnt/c/.
Install Python 3 with venv and pip, g++ with C++20 and OpenMP support, and
Node.js with npm. Ingestion needs internet access for supported Earth COG data.

~~~bash
git clone --branch main https://github.com/hajji-ismail7655/nasaspacechallenge.git
cd nasaspacechallenge
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
~~~

Run the commands below from the repository root unless a step says otherwise.
Activate the virtual environment again in each new Python terminal.

## 1. Prepare the 110 data tiles

~~~bash
python pipelines/phase2_real_ingest.py --shape 512 --out data_lake/phase2
python processor/cli.py \
  --manifest data_lake/phase2/phase2_processor_manifest.json \
  --out-dir data_lake/standardized --shape 512 --split-by-body
~~~

The first command stages raw arrays and channel provenance. The second writes
512 x 512, five-octave PTILEs to data_lake/standardized/earth/ and
data_lake/standardized/targets/. Earth channels use Copernicus DEM and
MODIS/Aqua COGs where supported. Other Earth channels and current Moon/Mars
channels are calibrated fallbacks. Inspect each tile's JSON sidecar for its
source_type and coverage before treating a score as measured data.

## 2. Build the five C++ modules

~~~bash
for module in topography mineralogy thermal_illumination granular_aeolian volatiles_subsurface; do
  (cd "OptiAlgo/$module" && bash build.sh)
done
~~~

The build scripts produce ignored .so files and use -march=native, so build on
the machine where you will run the sweep.

## 3. Compute the 112 Earth/target comparisons

The simplest option is one sweep process:

~~~bash
python fusion/run_discovery_sweep.py --backend cpp \
  --earth-dir data_lake/standardized/earth \
  --target-dir data_lake/standardized/targets \
  --out-dir data_lake/results
~~~

For a machine with at least 12 logical CPU threads, use four processes. Start
each command below in a separate Bash terminal from the repository root, with
the virtual environment active:

~~~bash
OMP_NUM_THREADS=3 python fusion/run_discovery_sweep.py --backend cpp --out-dir data_lake/chunks/part1 \
  --sites earth_anti_atlas,earth_mistastin,earth_qaidam,earth_afar
~~~

~~~bash
OMP_NUM_THREADS=3 python fusion/run_discovery_sweep.py --backend cpp --out-dir data_lake/chunks/part2 \
  --sites earth_undara,earth_lut_desert,earth_tanezrouft,earth_yakutia
~~~

~~~bash
OMP_NUM_THREADS=3 python fusion/run_discovery_sweep.py --backend cpp --out-dir data_lake/chunks/part3 \
  --sites earth_kumtagh,earth_jebel_saghro,earth_atacama_core
~~~

~~~bash
OMP_NUM_THREADS=3 python fusion/run_discovery_sweep.py --backend cpp --out-dir data_lake/chunks/part4 \
  --sites earth_haughton,earth_iceland,earth_mojave
~~~

Wait for all four commands to finish successfully, then merge their outputs:

~~~bash
python scripts/merge_sweep_chunks.py \
  --chunks data_lake/chunks/part1 data_lake/chunks/part2 data_lake/chunks/part3 data_lake/chunks/part4 \
  --out-dir data_lake/results --expected-pairs 112
~~~

The result directory contains ranked_novel_discoveries.json,
ranked_unmasked_calibration.json, domain and composite HMAPs, and breakdown
JSON files. The four-process run took about 84 minutes on the tested machine;
runtime depends on CPU and storage speed.

## 4. Start the backend

In a new terminal at the repository root:

~~~bash
source .venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
~~~

Open http://127.0.0.1:8000/health and expect {"status":"ok"}.
The /targets route lists eight targets. The /api/discoveries route reads
data_lake/results/ and returns an empty list until the sweep is complete.

## 5. Start Frontend2 or Frontend1

The frontends default to http://localhost:8000 for API requests. Open a new
terminal for each frontend.

Frontend2 on port 5173:

~~~bash
cd Frontend2
npm ci
npm run dev -- --host 0.0.0.0 --port 5173 --strictPort
~~~

Open http://127.0.0.1:5173/. Its 2D map and 3D globe lead to the comparison
page. From a separate repository-root terminal, you can start Frontend1 too:

~~~bash
cd analog-discovery-engine
npm ci
npm run dev -- --host 0.0.0.0 --port 5174 --strictPort
~~~

Open http://127.0.0.1:5174/. If you run only Frontend1, you may use Vite's
default port 5173. To point either app at another API address, set
VITE_API_BASE_URL before npm run dev, for example:

~~~bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev -- --host 0.0.0.0
~~~

Both apps show scores for fixed Moon/Mars targets. Picker coordinates provide
visual context; the sweep does not score arbitrary planetary points or areas.
Frontend2's thermal colors and markers are illustrative preview data because
the API does not serve thermal grids.

## Checks and common issues

~~~bash
python -m unittest discover -s tests -v
(cd Frontend2 && npm test && npm run build)
(cd analog-discovery-engine && npm test && npm run build)
~~~

- Blank map or globe: reload the frontend and check its texture URL under
  http://localhost:5173/assets/textures/. Frontend2's workspace needs the
  viewport height defined in Frontend2/src/styles.css.
- No scores: check /health and confirm
  data_lake/results/ranked_novel_discoveries.json exists.
- Missing C++ library: rebuild all five modules in Linux or WSL.
  The --fallback-python switch is available for a diagnostic sweep and the
  output records which backend ran.
- A fresh clone must regenerate data_lake/ and compiled libraries. Git also
  ignores node_modules/ and dist/.
