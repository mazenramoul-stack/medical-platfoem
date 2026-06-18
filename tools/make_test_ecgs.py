"""Export a few REAL, labeled PTB-XL records as platform-ready 12-lead CSVs.

Writes one CSV per common pathology (plus a normal record) so you can upload them
to the platform and confirm the model predicts the right thing. Each CSV has a
header row of the 12 standard lead names and one row per sample — exactly the
format `backend/apps/inference/utils.load_ecg_signal` reads (12 numeric columns,
interpreted as leads). Single-label records are preferred so each test is
unambiguous.

Usage:
    python tools/make_test_ecgs.py --ptbxl-dir <PTB-XL root> [--out-dir sample_ecgs]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))
sys.path.insert(0, str(_ROOT / "tools"))

import pandas as pd  # noqa: E402

from apps.inference.utils import load_ecg_signal  # noqa: E402
from eval_ecg_classifier import iter_ptbxl  # noqa: E402

LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
TARGETS = ["AFIB", "1AVB", "STACH", "SBRAD", "RBBB", "LBBB", "PVC"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ptbxl-dir", required=True, help="PTB-XL root (has ptbxl_database.csv)")
    ap.add_argument("--out-dir", default=str(_ROOT / "sample_ecgs"))
    ap.add_argument("--fold", type=int, default=10, help="PTB-XL strat_fold to pull from")
    args = ap.parse_args()

    ptb = Path(args.ptbxl_dir)
    assert (ptb / "ptbxl_database.csv").exists(), f"PTB-XL not found at {ptb}"
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    records = list(iter_ptbxl(ptb, 0.0, args.fold))
    picks: dict = {}
    normal = None
    # pass 1: single-label records (cleanest test cases)
    for path, positives in records:
        if not positives and normal is None:
            normal = (path, [])
        if len(positives) == 1:
            only = next(iter(positives))
            if only in TARGETS and only not in picks:
                picks[only] = (path, positives)
    # pass 2: fill any still-missing target with its first (multi-label) occurrence
    for path, positives in records:
        for p in positives:
            if p in TARGETS and p not in picks:
                picks[p] = (path, positives)

    items = list(picks.items())
    if normal is not None:
        items.append(("NORMAL", normal))

    print(f"PTB-XL fold {args.fold}: {len(records)} records scanned\n")
    for label, (path, pos) in items:
        sig, fs, _ = load_ecg_signal(str(path))      # (12, 5000) @ 500 Hz, canonical lead order
        fn = out / f"ecg_{label}.csv"
        pd.DataFrame(sig.T, columns=LEADS).to_csv(fn, index=False)
        print(f"  {label:7} -> {fn.name:16} shape={sig.shape}  true labels={pos or ['(normal)']}")
    print(f"\nWrote {len(items)} CSV(s) to {out}")
    print("Upload any of these on the ECG page; the model should flag the listed label.")


if __name__ == "__main__":
    main()
