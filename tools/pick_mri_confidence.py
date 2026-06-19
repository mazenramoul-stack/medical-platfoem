"""Add MRI demo images the classifier predicts at MID confidence (default 50-80%).

The first 10 MRI samples are mostly 100%-confident; this finds harder cases so a
demo can show a realistic confidence spread. Scans data/brain-tumor-mri/Testing,
runs the deployed Swin classifier, keeps predictions whose top probability falls
in the target band (preferring CORRECT ones, spread across classes), copies them
into 'Test Samples/mri/' as mri_11.. with the confidence in the filename, and
updates the manifest + README.

Usage (repo root, backend venv):
    backend/venv/Scripts/python.exe tools/pick_mri_confidence.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.make_test_samples import OUT, write_readme  # noqa: E402

DATA = REPO_ROOT / "data" / "brain-tumor-mri" / "Testing"
LOW, HIGH = 0.45, 0.85
WANT = 5
MAX_PER_CLASS = 5     # mid-confidence cases cluster in glioma (the hardest class)
SCAN_PER_CLASS = 130  # images sampled per class before giving up


def _norm(label):
    return str(label).lower().replace("_", "").replace("-", "")


def main():
    import numpy as np
    from apps.inference import analyze_mri

    classes = ["glioma", "meningioma", "pituitary", "notumor"]
    # Mid-confidence cases live almost entirely in glioma, so scan it heavily and
    # FIRST (others get a small probe). No final shuffle => glioma hits come fast.
    scan_counts = {"glioma": 300, "meningioma": 40, "pituitary": 40, "notumor": 40}
    candidates = []
    rng = np.random.default_rng(11)
    for cls in classes:
        files = sorted((DATA / cls).glob("*"))
        idx = rng.permutation(len(files))[:scan_counts.get(cls, SCAN_PER_CLASS)]
        for i in idx:
            candidates.append((cls, files[int(i)]))

    picked, per_class = [], {c: 0 for c in classes}
    for cls, f in candidates:
        if len(picked) >= WANT:
            break
        if per_class[cls] >= MAX_PER_CLASS:
            continue
        r = analyze_mri(str(f), mode="classify")
        if r.get("status") != "success":
            continue
        pred, conf = r.get("tumor_type"), r.get("tumor_type_confidence") or 0.0
        if not (LOW <= conf <= HIGH):
            continue
        correct = _norm(pred) == _norm(cls)
        if not correct:
            continue  # prefer correct-but-uncertain cases for the demo
        picked.append({"cls": cls, "file": f, "pred": pred, "conf": conf})
        per_class[cls] += 1
        print(f"  candidate: {f.name}  truth={cls}  pred={pred} ({conf:.0%})")

    if not picked:
        print("No mid-confidence images found in band; widen LOW/HIGH or SCAN_PER_CLASS.")
        return 1

    out = OUT / "mri"
    out.mkdir(parents=True, exist_ok=True)
    mpath = OUT / "manifest.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else []
    # Idempotent: drop any previously-added mid-confidence samples so re-runs
    # don't accumulate duplicates.
    for old in out.glob("mri_*pct*"):
        old.unlink()
    manifest = [m for m in manifest
                if not (m["modality"] == "mri" and "pct" in m["file"])]
    start = 11
    for k, p in enumerate(picked):
        ext = p["file"].suffix.lower() or ".jpg"
        dst = out / f"mri_{start + k:02d}_{p['cls']}_{round(p['conf'] * 100)}pct{ext}"
        shutil.copyfile(p["file"], dst)
        manifest.append({
            "file": dst.name, "modality": "mri", "truth": p["cls"],
            "prediction": f"{p['pred']} ({p['conf']:.0%})",
        })
        print(f"  wrote {dst.name}")
    mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_readme(manifest)
    print(f"\nAdded {len(picked)} mid-confidence MRI samples. Updated README + manifest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
