"""Independent ECG evaluation on an EXTERNAL dataset (leakage check).

WHY THIS EXISTS
---------------
The headline ECG numbers in VALIDATION.md are measured on PTB-XL fold 10. But the
ecglib DenseNet-1D models *may* have been trained on PTB-XL (their exact training
corpus is not published), so that "held-out" set might not be truly unseen — which
would make the AUC optimistic. The only clean way to rule that out is to test on a
dataset ecglib's authors are far less likely to have trained on.

This script does exactly that against the **Chapman-Shaoxing-Ningbo** 12-lead ECG
database (PhysioNet "ecg-arrhythmia"), which is independent of PTB-XL and uses
SNOMED-CT diagnosis codes. The model weights are FROZEN and used exactly as
deployed — this measures the existing models on new data, it does not retrain.

DISK-SAFE BY DEFAULT
--------------------
Streaming mode pulls each record from PhysioNet over HTTP, runs inference, and
discards it immediately — nothing is written to disk. This works even with a
near-full drive (peak footprint is one record in RAM, ~150 KB). Requires internet.

USAGE
-----
    # Disk-safe streaming sample (recommended on a full drive):
    python tools/eval_ecg_external.py --stream 400

    # Reproducible: same 400 records every run (seeded sampling):
    python tools/eval_ecg_external.py --stream 400 --seed 42

    # If you later download the dataset locally (WFDB .dat/.hea pairs):
    python tools/eval_ecg_external.py --local path/to/ecg-arrhythmia

WHAT IT REPORTS
---------------
Per-pathology AUC + precision/recall/F1 at the SAME tuned DETECTION_THRESHOLDS the
app deploys (imported live from apps.inference.ecg_pipeline), plus macro/micro/
weighted aggregates and balanced accuracy. AUC is threshold-independent — it is the
number to quote for "does the model generalise to an independent dataset".

Faithful to deployment: replicates ecg_pipeline preprocessing (0.5-40 Hz band-pass +
per-lead z-score) and the same _scalar_probability read-out.

CAVEATS (read before quoting a number)
--------------------------------------
1. The SNOMED->ecglib map below is the standard PhysioNet-2021 mapping but you MUST
   sanity-check it against the dataset's own ConditionNames_SNOMED-CT.csv — code
   sets drift between dataset versions. A wrong code silently mislabels a pathology.
2. A streamed *sample* (e.g. 400 records) gives an indicative number with real
   confidence only for pathologies that have enough positives in the sample. Watch
   the 'support' column — AUC on <30 positives is noisy. For a report-grade number,
   run the full set locally (option 2) once disk allows.
3. Chapman-Shaoxing is 500 Hz x 10 s = 5000 samples, 12 leads in standard order —
   matches the deployed model input. Records off that shape are resampled/!skipped.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Reuse the existing harness's metric/reporting code — single source of truth.
from eval_ecg_classifier import (  # noqa: E402
    PATHOLOGIES,
    collect_scores,
    report_comprehensive,
    report_metrics,
)

# PhysioNet slug for Chapman-Shaoxing-Ningbo 12-lead ECG database.
PHYSIONET_DB = "ecg-arrhythmia/1.0.0"
TARGET_SAMPLES = 5000   # deployed model input width (12 x 5000 @ 500 Hz, 10 s)

# --- SNOMED-CT -> ecglib's 7 pathologies -------------------------------------
# Standard PhysioNet/CinC-2021 SNOMED codes. ecglib's RBBB/LBBB are GENERAL
# (complete OR incomplete), so both variants map to the same ecglib code.
# VERIFY against the dataset's ConditionNames_SNOMED-CT.csv before trusting numbers.
SNOMED_TO_ECGLIB = {
    "164889003": "AFIB",   # atrial fibrillation
    "270492004": "1AVB",   # first-degree AV block
    "427084000": "STACH",  # sinus tachycardia
    "426177001": "SBRAD",  # sinus bradycardia
    "59118001":  "RBBB",   # right bundle branch block
    "713427006": "RBBB",   # complete RBBB
    "713426002": "RBBB",   # incomplete RBBB (IRBBB)
    "164909002": "LBBB",   # left bundle branch block
    "733534002": "LBBB",   # complete LBBB
    "251120003": "LBBB",   # incomplete LBBB
    "427172004": "PVC",    # premature ventricular contractions
    "17338001":  "PVC",    # ventricular premature beats
}


def parse_dx_codes(comments) -> set[str]:
    """Extract positive ecglib codes from a WFDB record's header comments.

    Chapman/PhysioNet headers carry a 'Dx: <snomed>,<snomed>,...' comment line.
    """
    positives: set[str] = set()
    for line in comments or []:
        low = str(line).lower()
        if low.startswith("dx:") or "dx:" in low:
            raw = str(line).split(":", 1)[1] if ":" in str(line) else ""
            for code in raw.replace(";", ",").split(","):
                code = code.strip()
                if code in SNOMED_TO_ECGLIB:
                    positives.add(SNOMED_TO_ECGLIB[code])
    return positives


def signal_to_model_input(sig, fs, np):
    """(n_samples, 12) raw signal -> (12, 5000) float32 array, deployment-faithful.

    Mirrors apps.inference.ecg_pipeline: 0.5-40 Hz Butterworth band-pass +
    per-lead z-score. Resamples to 5000 samples if the record is a different length.
    """
    from scipy.signal import butter, filtfilt, resample

    x = np.asarray(sig, dtype=float).T            # -> (12, n)
    if x.shape[0] < 12:
        return None                               # not a 12-lead record
    x = x[:12]
    if x.shape[1] != TARGET_SAMPLES:
        x = resample(x, TARGET_SAMPLES, axis=1)
        fs = TARGET_SAMPLES / 10.0                # now 500 Hz-equivalent
    b, a = butter(4, [0.5, 40], btype="bandpass", fs=fs)
    x = filtfilt(b, a, x, axis=1)
    x = (x - x.mean(axis=1, keepdims=True)) / (x.std(axis=1, keepdims=True) + 1e-8)
    return x.astype("float32")


def predict_from_array(arr, loader, np, torch) -> dict:
    """{pathology: probability} for one (12, 5000) array — deployed read-out."""
    from apps.inference.ecg_pipeline import _scalar_probability

    tensor = torch.from_numpy(arr).float().unsqueeze(0).to(loader.get_device())
    out = {}
    for code, model in loader.get_ecg_models().items():
        with torch.no_grad():
            out[code] = _scalar_probability(model(tensor))
    return out


def iter_stream(n: int, seed: int, np, torch, loader, wfdb):
    """Yield (probs, positives) by streaming up to n records from PhysioNet.

    Disk-safe: each record is read into RAM and discarded. Sampling is seeded so a
    given (n, seed) is reproducible.
    """
    print(f"Fetching record list from PhysioNet '{PHYSIONET_DB}' ...")
    records = wfdb.get_record_list(PHYSIONET_DB)
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(records))[: n * 3]   # oversample; some get skipped
    done = 0
    for i in idx:
        if done >= n:
            break
        rec_path = records[int(i)]                 # e.g. WFDBRecords/01/010/JS00001
        sub = str(Path(rec_path).parent).replace("\\", "/")
        name = Path(rec_path).name
        try:
            rec = wfdb.rdrecord(name, pn_dir=f"{PHYSIONET_DB}/{sub}")
        except Exception as e:                     # network / parse hiccup -> skip
            print(f"  ! {name}: {type(e).__name__}: {e}")
            continue
        arr = signal_to_model_input(rec.p_signal, rec.fs, np)
        if arr is None:
            continue
        positives = parse_dx_codes(rec.comments)
        yield predict_from_array(arr, loader, np, torch), positives
        done += 1
        if done % 50 == 0:
            print(f"  ...{done}/{n} streamed")
    print(f"Streamed {done} usable records.")


def collect_stream(n, seed, loader, np, torch, wfdb):
    """Run streaming inference; return (scores, truths, total) like collect_scores."""
    scores = {c: [] for c in PATHOLOGIES}
    truths = {c: [] for c in PATHOLOGIES}
    total = 0
    for probs, positives in iter_stream(n, seed, np, torch, loader, wfdb):
        total += 1
        for c in PATHOLOGIES:
            scores[c].append(probs.get(c, 0.0))
            truths[c].append(1 if c in positives else 0)
    return scores, truths, total


def iter_local(root: Path, parse_dx_codes, wfdb):
    """Yield (record_path, positive_codes) from a locally downloaded WFDB tree."""
    for hea in sorted(root.rglob("*.hea")):
        try:
            header = wfdb.rdheader(str(hea.with_suffix("")))
        except Exception:
            continue
        yield hea.with_suffix(""), parse_dx_codes(header.comments)


def main() -> int:
    ap = argparse.ArgumentParser(description="Independent ECG eval (leakage check).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--stream", type=int, metavar="N",
                   help="stream N records from PhysioNet (disk-safe, needs internet)")
    g.add_argument("--local", metavar="PATH",
                   help="path to a downloaded ecg-arrhythmia WFDB tree")
    ap.add_argument("--seed", type=int, default=0, help="sampling seed for --stream")
    args = ap.parse_args()

    import numpy as np
    import torch
    import wfdb

    from apps.inference.ecg_pipeline import DETECTION_THRESHOLDS, DEFAULT_DETECTION_THRESHOLD
    from apps.inference.model_loader import ModelLoader

    loader = ModelLoader()
    print(f"Device: {loader.get_device()}  (first run loads 7 ecglib models)\n")

    thresholds = {c: DETECTION_THRESHOLDS.get(c, DEFAULT_DETECTION_THRESHOLD) for c in PATHOLOGIES}

    if args.stream:
        scores, truths, total = collect_stream(args.stream, args.seed, loader, np, torch, wfdb)
        title = f"Chapman-Shaoxing stream (n={total}, seed={args.seed}) @ deployed thresholds"
    else:
        root = Path(args.local)
        if not root.exists():
            print(f"ERROR: path not found: {root}", file=sys.stderr)
            return 2
        items = ((p, pos) for p, pos in iter_local(root, parse_dx_codes, wfdb))
        # collect_scores expects (path, positives) and reads via load_ecg_signal —
        # but Chapman is plain WFDB, so reuse the same array path as streaming:
        scores = {c: [] for c in PATHOLOGIES}
        truths = {c: [] for c in PATHOLOGIES}
        total = 0
        for path, positives in items:
            try:
                rec = wfdb.rdrecord(str(path))
                arr = signal_to_model_input(rec.p_signal, rec.fs, np)
                if arr is None:
                    continue
                probs = predict_from_array(arr, loader, np, torch)
            except Exception as e:
                print(f"  ! {path.name}: {type(e).__name__}: {e}")
                continue
            total += 1
            for c in PATHOLOGIES:
                scores[c].append(probs.get(c, 0.0))
                truths[c].append(1 if c in positives else 0)
            if total % 200 == 0:
                print(f"  ...{total} records")
        title = f"Chapman-Shaoxing local (n={total}) @ deployed thresholds"

    if total == 0:
        print("\nNo records evaluated — check internet/path and the SNOMED map.")
        return 1

    report_metrics(scores, truths, total, thresholds, np, title)
    report_comprehensive(scores, truths, total, thresholds, np,
                         "FULL SUITE — INDEPENDENT DATASET @ deployed thresholds")
    print("\nQuote the macro AUC: it is threshold-independent and is the honest")
    print("'does it generalise beyond PTB-XL' number. Watch 'support' — low-support")
    print("pathologies have noisy AUC; stream more records to firm them up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
