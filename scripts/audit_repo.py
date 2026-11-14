"""Pure-stdlib repository invariant auditor across all 12 canonical branches.

Verifies:
1. schema/tile_contract.h SHA-256 matches canonical e6d368f5a1881a161b6ed2bfa05bd002262bd6cfb5e89eedb07709f37d18aac7
   across all 12 canonical branches (plus LF-normalized working-tree check).
2. Datasets branch tracked blob size is strictly < 50 MB (50,000,000 bytes).
3. Zero forbidden raw rasters, compiled binaries, or data_lake/ files tracked across all 12 branches.
4. All tracked Python files across all 12 branches pass ast.parse syntax validation.
5. Main pipeline defaults use C++20 (OptiAlgo / --backend cpp), not BestAlgo.
6. Datasets pipelines/manifests align with official NASA/ESA/CSA/JAXA/PDS hackathon resources
   and support 512x512 output + per-channel REAL_ORBITAL_COG vs CALIBRATED_FALLBACK provenance.
"""
import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys

EXPECTED_TILE_CONTRACT_SHA256 = "e6d368f5a1881a161b6ed2bfa05bd002262bd6cfb5e89eedb07709f37d18aac7"
DATASETS_MAX_BYTES = 50_000_000

CANONICAL_BRANCHES = [
    "main",
    "Datasets",
    "BestAlgo/topography",
    "BestAlgo/mineralogy",
    "BestAlgo/thermal_illumination",
    "BestAlgo/granular_aeolian",
    "BestAlgo/volatiles_subsurface",
    "OptiAlgo/topography",
    "OptiAlgo/mineralogy",
    "OptiAlgo/thermal_illumination",
    "OptiAlgo/granular_aeolian",
    "OptiAlgo/volatiles_subsurface",
]

FORBIDDEN_EXTENSIONS = (
    ".tif", ".tiff", ".img", ".cub", ".lbl",
    ".h5", ".hdf", ".hdf5", ".nc",
    ".so", ".dll", ".dylib", ".o", ".a", ".exe",
)

OFFICIAL_RESOURCE_URLS = [
    "https://search.earthdata.nasa.gov/",
    "https://worldview.earthdata.nasa.gov/",
    "https://dataspace.copernicus.eu/",
    "https://opensciencedata.esa.int/",
    "https://donnees-data.asc-csa.gc.ca/en/dataset/radarsat1",
    "https://donnees-data.asc-csa.gc.ca/en/dataset/rcm",
    "https://gportal.jaxa.jp/gpr/index/index",
    "https://pds.nasa.gov/",
    "https://pds-geosciences.wustl.edu/missions/lro/",
    "https://pds-geosciences.wustl.edu/missions/lro/diviner.htm",
]


def _git(repo_root, args, text=True):
    cmd = ["git", "-C", repo_root] + args
    return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=text)


def _ref_exists(repo_root, ref):
    res = subprocess.run(
        ["git", "-C", repo_root, "rev-parse", "--verify", ref],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return res.returncode == 0


def resolve_branch_ref(repo_root, branch, prefer_origin=False):
    """Resolve canonical branch name to a valid git ref in repo_root."""
    if prefer_origin:
        candidates = [f"origin/{branch}", branch]
    else:
        current = _git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
        if current == branch:
            candidates = ["HEAD", f"origin/{branch}", branch]
        elif _ref_exists(repo_root, f"refs/heads/{branch}"):
            candidates = [f"refs/heads/{branch}", f"origin/{branch}"]
        else:
            candidates = [f"origin/{branch}", branch]
    for cand in candidates:
        if _ref_exists(repo_root, cand):
            return cand
    return None


def _is_forbidden_path(path):
    low = path.lower()
    return low.startswith("data_lake/") or any(low.endswith(ext) for ext in FORBIDDEN_EXTENSIONS)


def check_tile_contract(repo_root, refs_map):
    """Check schema/tile_contract.h SHA-256 across all 12 branches and working tree."""
    branch_hashes = {}
    mismatches = []
    for branch, ref in refs_map.items():
        if ref is None:
            mismatches.append(f"{branch}: missing branch ref")
            continue
        try:
            raw = _git(repo_root, ["cat-file", "blob", f"{ref}:schema/tile_contract.h"], text=False)
            sha = hashlib.sha256(raw).hexdigest()
            branch_hashes[branch] = {"ref": ref, "sha256": sha, "bytes": len(raw)}
            if sha != EXPECTED_TILE_CONTRACT_SHA256:
                mismatches.append(f"{branch} ({ref}): {sha}")
        except subprocess.CalledProcessError:
            mismatches.append(f"{branch} ({ref}): missing schema/tile_contract.h")

    wt_path = os.path.join(repo_root, "schema", "tile_contract.h")
    wt_sha = None
    if os.path.exists(wt_path):
        with open(wt_path, "rb") as f:
            wt_lf = f.read().replace(b"\r\n", b"\n")
        wt_sha = hashlib.sha256(wt_lf).hexdigest()
        if wt_sha != EXPECTED_TILE_CONTRACT_SHA256:
            mismatches.append(f"working_tree: {wt_sha}")

    return {
        "pass": len(mismatches) == 0 and len(branch_hashes) == len(CANONICAL_BRANCHES),
        "expected_sha256": EXPECTED_TILE_CONTRACT_SHA256,
        "branches_checked": len(branch_hashes),
        "working_tree_lf_sha256": wt_sha,
        "branch_hashes": branch_hashes,
        "mismatches": mismatches,
    }


def check_forbidden_and_syntax(repo_root, refs_map):
    """Check zero forbidden files and valid Python AST across all 12 branches."""
    forbidden = []
    syntax_errors = []
    py_count = 0
    for branch, ref in refs_map.items():
        if ref is None:
            continue
        names = [line.strip() for line in _git(repo_root, ["ls-tree", "-r", "--name-only", ref]).splitlines() if line.strip()]
        for path in names:
            if _is_forbidden_path(path):
                forbidden.append(f"{branch}:{path}")
            if path.endswith(".py"):
                py_count += 1
                try:
                    raw = _git(repo_root, ["cat-file", "blob", f"{ref}:{path}"], text=False)
                    ast.parse(raw.decode("utf-8"), filename=f"{branch}:{path}")
                except (SyntaxError, UnicodeDecodeError, subprocess.CalledProcessError) as exc:
                    syntax_errors.append(f"{branch}:{path}: {exc}")

    return {
        "forbidden_pass": len(forbidden) == 0,
        "forbidden_files": forbidden,
        "python_syntax_pass": len(syntax_errors) == 0,
        "python_files_checked": py_count,
        "python_syntax_errors": syntax_errors,
    }


def check_datasets_branch(repo_root, datasets_ref):
    """Check Datasets size < 50 MB, official resources, 512x512 support, and provenance tags."""
    if datasets_ref is None:
        return {"pass": False, "error": "Datasets ref not found"}

    total_bytes = 0
    file_count = 0
    for line in _git(repo_root, ["ls-tree", "-r", "-l", datasets_ref]).splitlines():
        parts = line.split(None, 4)
        if len(parts) >= 4 and parts[1] == "blob" and parts[3].isdigit():
            total_bytes += int(parts[3])
            file_count += 1

    corpus_parts = []
    for rel in (
        "pipelines/_tile_utils.py",
        "pipelines/earth_ingest.py",
        "pipelines/moon_mars_ingest.py",
        "manifests/earth_candidates.json",
        "reference_targets/targets.json",
    ):
        try:
            corpus_parts.append(_git(repo_root, ["show", f"{datasets_ref}:{rel}"]))
        except subprocess.CalledProcessError:
            pass
    corpus = "\n".join(corpus_parts)

    missing_urls = [u for u in OFFICIAL_RESOURCE_URLS if u not in corpus]
    has_512 = ("512, 512" in corpus) or ("default=512" in corpus)
    has_provenance = ("REAL_ORBITAL_COG" in corpus) and ("CALIBRATED_FALLBACK" in corpus)

    return {
        "pass": (
            total_bytes < DATASETS_MAX_BYTES
            and not missing_urls
            and has_512
            and has_provenance
        ),
        "ref": datasets_ref,
        "tracked_files": file_count,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / 1e6, 3),
        "limit_bytes": DATASETS_MAX_BYTES,
        "missing_official_urls": missing_urls,
        "supports_512x512": has_512,
        "supports_channel_provenance": has_provenance,
    }


def check_cpp_pipeline_defaults(repo_root, main_ref):
    """Check main pipeline defaults target C++20 (OptiAlgo / --backend cpp)."""
    sweep_path = os.path.join(repo_root, "fusion", "run_discovery_sweep.py")
    if os.path.exists(sweep_path):
        with open(sweep_path, encoding="utf-8") as f:
            sweep_src = f.read()
    elif main_ref is not None:
        sweep_src = _git(repo_root, ["show", f"{main_ref}:fusion/run_discovery_sweep.py"])
    else:
        return {"pass": False, "error": "fusion/run_discovery_sweep.py not found"}

    tree = ast.parse(sweep_src, filename="fusion/run_discovery_sweep.py")
    run_sweep_default = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_sweep":
            args = node.args.args
            defaults = node.args.defaults
            offset = len(args) - len(defaults)
            for idx, arg in enumerate(args):
                if arg.arg == "backend" and idx >= offset:
                    val = defaults[idx - offset]
                    if isinstance(val, ast.Constant):
                        run_sweep_default = val.value

    cli_cpp_default = ('default="cpp"' in sweep_src) or ("default='cpp'" in sweep_src)
    optialgo_mapping = 'folder = "OptiAlgo" if backend == "cpp"' in sweep_src
    readme_path = os.path.join(repo_root, "README.md")
    readme_cpp = False
    if os.path.exists(readme_path):
        with open(readme_path, encoding="utf-8") as f:
            readme_cpp = "run_discovery_sweep.py --backend cpp" in f.read()

    passed = (run_sweep_default == "cpp") and cli_cpp_default and optialgo_mapping and readme_cpp
    return {
        "pass": passed,
        "run_sweep_default_backend": run_sweep_default,
        "cli_default_cpp": cli_cpp_default,
        "optialgo_dispatch": optialgo_mapping,
        "readme_uses_backend_cpp": readme_cpp,
    }


def run_audit(repo_root=None, prefer_origin=False):
    """Execute full cross-branch audit and return structured JSON-ready dict."""
    if repo_root is None:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    refs_map = {b: resolve_branch_ref(repo_root, b, prefer_origin=prefer_origin) for b in CANONICAL_BRANCHES}
    contract_res = check_tile_contract(repo_root, refs_map)
    files_res = check_forbidden_and_syntax(repo_root, refs_map)
    datasets_res = check_datasets_branch(repo_root, refs_map.get("Datasets"))
    cpp_res = check_cpp_pipeline_defaults(repo_root, refs_map.get("main"))

    all_pass = (
        contract_res["pass"]
        and files_res["forbidden_pass"]
        and files_res["python_syntax_pass"]
        and datasets_res["pass"]
        and cpp_res["pass"]
    )
    return {
        "status": "PASS" if all_pass else "FAIL",
        "repo_root": os.path.abspath(repo_root),
        "tile_contract": contract_res,
        "files_and_syntax": files_res,
        "datasets": datasets_res,
        "cpp_defaults": cpp_res,
    }


def main():
    ap = argparse.ArgumentParser(description="Verify repository invariants across all 12 canonical branches.")
    ap.add_argument("--repo", default="", help="Path to git repository root (defaults to parent of scripts/)")
    ap.add_argument("--origin", action="store_true", help="Prefer origin/* refs over local branch heads")
    args = ap.parse_args()

    repo_root = args.repo or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    report = run_audit(repo_root=repo_root, prefer_origin=args.origin)
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
