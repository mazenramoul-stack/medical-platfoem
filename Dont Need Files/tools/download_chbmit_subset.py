"""Download a SUBSET of the CHB-MIT Scalp EEG Database (PhysioNet, open access).

Pulls only the chosen patient folders (each ~1-2 GB) plus the seizure-annotation
summaries, so you avoid the full 42.6 GB. No registration, no wget/aws needed
(uses Python's stdlib urllib). Resumable: already-downloaded files are skipped.

Usage (put it next to your PTB-XL, e.g. data/chbmit/):
    python tools/download_chbmit_subset.py \
        --out "C:/Users/MAZEN/Downloads/data/chbmit" \
        --patients chb01 chb02 chb03 chb04 chb05 chb06 chb07 chb08

Each patient folder gets its .edf recordings + chbXX-summary.txt (seizure
start/end times). ~8 patients is roughly 12-18 GB. Keep it under ~15 GB if you'll
put it on a free Google Drive.
"""

from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

BASE = "https://physionet.org/files/chbmit/1.0.0"


def fetch(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  skip (exists): {dest.relative_to(dest.parents[1])}")
        return
    print(f"  downloading: {dest.name}")
    urllib.request.urlretrieve(url, dest)  # resumes via the skip-check above


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="output dir, e.g. .../data/chbmit")
    ap.add_argument("--patients", nargs="+", required=True,
                    help="e.g. chb01 chb02 ... chb08")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    chosen = set(args.patients)

    # 1. metadata (tiny) — RECORDS lists every .edf; RECORDS-WITH-SEIZURES the seizure ones
    for meta in ("RECORDS", "RECORDS-WITH-SEIZURES", "SUBJECT-INFO"):
        try:
            fetch(f"{BASE}/{meta}", out / meta)
        except Exception as e:
            print(f"  (could not get {meta}: {e})")

    # 2. resolve which .edf files belong to the chosen patients
    recs_txt = urllib.request.urlopen(f"{BASE}/RECORDS").read().decode()
    all_recs = [l.strip() for l in recs_txt.splitlines() if l.strip().endswith(".edf")]

    def patient_of(rec: str) -> str:
        return rec.split("/")[-1].split("_")[0]   # 'chb01/chb01_03.edf' -> 'chb01'

    recs = [r for r in all_recs if patient_of(r) in chosen]
    if not recs:
        raise SystemExit(f"No .edf files found for patients {sorted(chosen)} — "
                         f"check the names (chb01..chb24).")
    print(f"\n{len(recs)} .edf files across {len(chosen)} patient(s): {sorted(chosen)}\n")

    # 3. per-patient summary (seizure times) + the .edf recordings
    for p in sorted(chosen):
        try:
            fetch(f"{BASE}/{p}/{p}-summary.txt", out / p / f"{p}-summary.txt")
        except Exception as e:
            print(f"  (could not get {p}-summary.txt: {e})")
    for r in recs:
        fname = r.split("/")[-1]
        fetch(f"{BASE}/{patient_of(r)}/{fname}", out / patient_of(r) / fname)

    print(f"\nDone. Subset is in: {out}")
    print("Zip it and upload to Google Drive for Colab, or point the notebook at it.")


if __name__ == "__main__":
    main()
