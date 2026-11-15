"""Combine disjoint discovery-sweep chunks into the backend results directory."""
import argparse
import json
import os
import shutil


def read_rows(chunk_dirs, filename):
    rows = []
    backends = {}
    seen = set()
    for chunk_dir in chunk_dirs:
        path = os.path.join(chunk_dir, filename)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        backends.update(data.get("backends_used", {}))
        for row in data.get("sites", []):
            key = (row.get("site_id"), row.get("target_id"))
            if key in seen:
                raise ValueError(f"Duplicate discovery pair: {key}")
            seen.add(key)
            rows.append(row)
    return rows, backends


def merge_chunks(chunk_dirs, out_dir, expected_pairs=112):
    os.makedirs(out_dir, exist_ok=True)
    novel, backends = read_rows(chunk_dirs, "ranked_novel_discoveries.json")
    unmasked, _ = read_rows(chunk_dirs, "ranked_unmasked_calibration.json")
    if len(novel) != expected_pairs or len(unmasked) != expected_pairs:
        raise ValueError(
            f"Expected {expected_pairs} pairs in each result set; got "
            f"{len(novel)} novel and {len(unmasked)} unmasked"
        )

    for chunk_dir in chunk_dirs:
        for name in os.listdir(chunk_dir):
            if name.endswith(".hmap") or name.endswith("_breakdown.json"):
                shutil.copy2(os.path.join(chunk_dir, name), os.path.join(out_dir, name))

    for rows, score_key, filename, masked in (
        (novel, "novel_composite_score", "ranked_novel_discoveries.json", True),
        (unmasked, "unmasked_composite_score", "ranked_unmasked_calibration.json", False),
    ):
        for row in rows:
            site = row["site_id"]
            target = row["target_id"]
            row["breakdown_path"] = os.path.abspath(os.path.join(out_dir, f"{site}_{target}_breakdown.json"))
            row["composite_hmap_path"] = os.path.abspath(os.path.join(out_dir, f"{site}_{target}_composite.hmap"))
            row["composite_score"] = row[score_key]
        rows.sort(key=lambda row: (row[score_key], row.get("scale_invariance_index", 0.0)), reverse=True)
        with open(os.path.join(out_dir, filename), "w", encoding="utf-8") as f:
            json.dump({
                "backend": "cpp",
                "backends_used": backends,
                "novelty_masked": masked,
                "count": len(rows),
                "sites": rows,
            }, f, indent=2)

    return {"pairs_evaluated": len(novel), "backends_used": backends, "out_dir": os.path.abspath(out_dir)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chunks", nargs="+", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--expected-pairs", type=int, default=112)
    args = ap.parse_args()
    print(json.dumps(merge_chunks(args.chunks, args.out_dir, args.expected_pairs), indent=2))


if __name__ == "__main__":
    main()
