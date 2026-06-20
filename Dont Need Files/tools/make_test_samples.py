"""Build a 'Test Samples' folder for demoing the four models to evaluators.

Per modality (10 each), written to <repo>/Test Samples/{mri,ecg,eeg,echo}/ with
the class/label in each filename:

  MRI  — REAL labeled brain-tumor images copied from data/brain-tumor-mri/Testing
         (glioma / meningioma / pituitary / notumor).
  EEG  — REAL labeled .edf cut from the Kaggle-HMS dataset (data/hms), written as
         referential 10-20 monopolar @200 Hz (what the BIOT pipeline needs).
  ECG  — REAL labeled 12-lead CSVs streamed from the Chapman-Shaoxing-Ningbo
         database (PhysioNet 'ecg-arrhythmia'), which is INDEPENDENT of PTB-XL —
         i.e. data the deployed ECG model never trained on. SNOMED-CT labelled.
  Echo — SYNTHETIC grayscale cine clips (no public A4C echo dataset is freely
         downloadable; EchoNet-Dynamic is registration-gated). These run end to
         end through the EchoNet pipeline so the modality demos, but the EF is
         NOT clinically meaningful — clearly flagged in the manifest.

Usage (from repo root, backend venv):
    backend/venv/Scripts/python.exe tools/make_test_samples.py --only mri
    backend/venv/Scripts/python.exe tools/make_test_samples.py --only ecg --stream 400
    backend/venv/Scripts/python.exe tools/make_test_samples.py --only eeg
    backend/venv/Scripts/python.exe tools/make_test_samples.py --only echo
    backend/venv/Scripts/python.exe tools/make_test_samples.py --verify        # run models, write README
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"
DATA = REPO_ROOT / "data"
OUT = REPO_ROOT / "Test Samples"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CANON_LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]


def _reset(modality):
    d = OUT / modality
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)
    return d


# --- MRI -------------------------------------------------------------------

def build_mri():
    src = DATA / "brain-tumor-mri" / "Testing"
    if not src.is_dir():
        print("MRI: dataset not found at", src)
        return []
    # 3 glioma, 3 meningioma, 2 pituitary, 2 notumor = 10, deterministic picks.
    plan = [("glioma", 3), ("meningioma", 3), ("pituitary", 2), ("notumor", 2)]
    out = _reset("mri")
    idx, manifest = 1, []
    for cls, k in plan:
        files = sorted((src / cls).glob("*"))
        # spread the picks across the (sorted) folder rather than the first few
        picks = [files[int(i * (len(files) - 1) / max(1, k))] for i in range(k)]
        for f in picks:
            ext = f.suffix.lower() or ".jpg"
            dst = out / f"mri_{idx:02d}_{cls}{ext}"
            shutil.copyfile(f, dst)
            manifest.append({"file": dst.name, "modality": "mri", "truth": cls})
            idx += 1
    print(f"MRI: wrote {len(manifest)} real labeled images -> {out}")
    return manifest


# --- EEG -------------------------------------------------------------------

def build_eeg(per_class=2):
    from tools.eeg_hms import load_index
    from apps.inference.eeg_preprocess import IIIC_CLASSES, IIIC_CLASS_NAMES

    if not (DATA / "hms" / "train.csv").exists():
        print("EEG: HMS dataset not found at", DATA / "hms")
        return []
    import pandas as pd

    samples = load_index(DATA / "hms", limit=0)  # all locally-present, with labels
    # bucket by IIIC label index, take up to per_class each, spread to 10
    buckets = {i: [] for i in range(len(IIIC_CLASSES))}
    for s in samples:
        if len(buckets[s["label"]]) < per_class:
            buckets[s["label"]].append(s)
    chosen = []
    for i in range(len(IIIC_CLASSES)):
        chosen.extend(buckets[i])
    # top up to 10 from whatever remains
    if len(chosen) < 10:
        seen = {(s["eeg_id"], s["offset_seconds"]) for s in chosen}
        for s in samples:
            if len(chosen) >= 10:
                break
            if (s["eeg_id"], s["offset_seconds"]) not in seen:
                chosen.append(s)
    chosen = chosen[:10]

    out = _reset("eeg")
    eeg_dir = DATA / "hms" / "train_eegs"
    manifest = []
    for idx, s in enumerate(chosen, 1):
        df = pd.read_parquet(eeg_dir / f'{s["eeg_id"]}.parquet')
        cls = IIIC_CLASSES[s["label"]]
        name = IIIC_CLASS_NAMES[cls].split(" /")[0].replace(" ", "")
        dst = out / f"eeg_{idx:02d}_{name}.edf"
        _write_eeg_edf(df, s["offset_seconds"], dst)
        manifest.append({"file": dst.name, "modality": "eeg",
                         "truth": IIIC_CLASS_NAMES[cls], "truth_code": cls})
    print(f"EEG: wrote {len(manifest)} real labeled .edf -> {out}")
    return manifest


def _write_eeg_edf(df, offset_seconds, dst, rate=200, window_s=50):
    """Write the labeled HMS window (monopolar 10-20 @200 Hz) as a referential EDF."""
    import mne

    # HMS labels the 50 s window starting at offset_seconds.
    start = int(round(offset_seconds * rate))
    seg = df.iloc[start:start + window_s * rate]
    if len(seg) < rate * 10:               # ensure at least one 10 s segment
        seg = df.iloc[:max(len(df), rate * 10)]
    ch_names = [str(c) for c in seg.columns]
    data = seg.to_numpy(dtype=np.float64).T  # (n_ch, n_samp), microvolts
    data = np.nan_to_num(data) * 1e-6        # mne EDF expects Volts for 'eeg'
    info = mne.create_info(ch_names=ch_names, sfreq=rate, ch_types="eeg")
    raw = mne.io.RawArray(data, info, verbose="ERROR")
    raw.export(str(dst), fmt="edf", overwrite=True, verbose="ERROR")


# --- ECG -------------------------------------------------------------------

# SNOMED -> ecglib 7 classes (from tools/eval_ecg_external.py) + sinus rhythm.
SNOMED_TO_CLASS = {
    "164889003": "AFIB", "270492004": "1AVB", "427084000": "STACH",
    "426177001": "SBRAD", "59118001": "RBBB", "713427006": "RBBB",
    "713426002": "RBBB", "164909002": "LBBB", "733534002": "LBBB",
    "251120003": "LBBB", "427172004": "PVC", "17338001": "PVC",
}
SINUS_RHYTHM = "426783006"
# target count per labelled class (sums to 10)
ECG_TARGETS = {"AFIB": 1, "1AVB": 1, "STACH": 2, "SBRAD": 2,
               "RBBB": 1, "LBBB": 1, "PVC": 1, "Normal": 1}


def _dx_codes(comments):
    codes = set()
    for line in comments or []:
        s = str(line)
        if "dx" in s.lower() and ":" in s:
            for c in s.split(":", 1)[1].replace(";", ",").split(","):
                codes.add(c.strip())
    return codes


def build_ecg(max_stream=500, seed=42):
    import wfdb
    from scipy.signal import resample

    out = _reset("ecg")
    buckets = {k: [] for k in ECG_TARGETS}
    db = "ecg-arrhythmia/1.0.0"
    print(f"ECG: streaming up to {max_stream} records from PhysioNet '{db}' ...")
    subdirs = [str(s).rstrip("/").replace("\\", "/") for s in wfdb.get_record_list(db)]
    rng = np.random.default_rng(seed)
    rng.shuffle(subdirs)
    pools, active, streamed = {}, list(subdirs), 0

    def _full():
        return all(len(buckets[k]) >= v for k, v in ECG_TARGETS.items())

    while active and streamed < max_stream and not _full():
        nxt = []
        for sub in active:
            if streamed >= max_stream or _full():
                break
            sub_db = f"{db}/{sub}"
            if sub not in pools:
                try:
                    pools[sub] = [Path(str(r)).name for r in wfdb.get_record_list(sub_db)]
                    rng.shuffle(pools[sub])
                except Exception:
                    pools[sub] = []
                    continue
            if not pools[sub]:
                continue
            name = pools[sub].pop()
            try:
                rec = wfdb.rdrecord(name, pn_dir=sub_db)
            except Exception:
                if pools[sub]:
                    nxt.append(sub)
                continue
            streamed += 1
            codes = _dx_codes(rec.comments)
            mapped = {SNOMED_TO_CLASS[c] for c in codes if c in SNOMED_TO_CLASS}
            target = None
            if not mapped and SINUS_RHYTHM in codes and len(buckets["Normal"]) < ECG_TARGETS["Normal"]:
                target = "Normal"
            elif len(mapped) == 1:
                c = next(iter(mapped))
                if len(buckets.get(c, [])) < ECG_TARGETS.get(c, 0):
                    target = c
            if target:
                buckets[target].append((name, rec))
            if streamed % 50 == 0:
                got = sum(len(v) for v in buckets.values())
                print(f"  ...{streamed} streamed, {got}/10 collected")
            if pools[sub]:
                nxt.append(sub)
        active = nxt

    manifest, idx = [], 1
    for cls, recs in buckets.items():
        for name, rec in recs:
            sig = np.asarray(rec.p_signal, dtype=float)  # (n, leads)
            if sig.shape[1] < 12:
                continue
            sig = sig[:, :12]
            if sig.shape[0] != 5000:
                sig = resample(sig, 5000, axis=0)
            cols = list(rec.sig_name[:12]) if rec.sig_name else CANON_LEADS
            cols = [c if c else CANON_LEADS[i] for i, c in enumerate(cols)]
            import pandas as pd
            dst = out / f"ecg_{idx:02d}_{cls}.csv"
            pd.DataFrame(sig, columns=cols).to_csv(dst, index=False)
            manifest.append({"file": dst.name, "modality": "ecg", "truth": cls,
                             "source_record": name})
            idx += 1
    print(f"ECG: wrote {len(manifest)} real labeled CSVs (streamed {streamed}) -> {out}")
    if len(manifest) < 10:
        print(f"ECG: NOTE only {len(manifest)}/10 found within {max_stream} records "
              f"(rare classes are sparse). Re-run with a larger --stream to fill.")
    return manifest


# --- Echo (synthetic pipeline demo) ---------------------------------------

def build_echo(n=10):
    import cv2

    out = _reset("echo")
    manifest = []
    H = W = 112
    n_frames = 64
    fps = 50
    rng = np.random.default_rng(0)
    for idx in range(1, n + 1):
        # vary the fractional area change so EF estimates span a range
        contraction = 0.25 + 0.55 * (idx - 1) / (n - 1)  # 0.25 .. 0.80
        dst = out / f"echo_{idx:02d}_synthetic.mp4"
        writer = cv2.VideoWriter(str(dst), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H), True)
        yy, xx = np.mgrid[0:H, 0:W]
        for t in range(n_frames):
            phase = 0.5 - 0.5 * np.cos(2 * np.pi * t / (n_frames / 2))  # systole/diastole
            scale = 1.0 - contraction * phase
            a = (W * 0.28) * scale
            b = (H * 0.40) * scale
            chamber = (((xx - W / 2) / a) ** 2 + ((yy - H / 2) / b) ** 2) < 1.0
            frame = np.full((H, W), 90, np.uint8)
            frame[chamber] = 20  # dark blood pool
            frame = (frame + rng.normal(0, 8, (H, W))).clip(0, 255).astype(np.uint8)
            writer.write(cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))
        writer.release()
        manifest.append({"file": dst.name, "modality": "echo", "truth": "synthetic"})
    print(f"Echo: wrote {len(manifest)} SYNTHETIC cine clips -> {out}")
    return manifest


# --- verification ----------------------------------------------------------

def verify(manifest):
    from apps.inference import analyze_mri, analyze_ecg, analyze_eeg, analyze_echo

    fns = {"mri": lambda p: analyze_mri(p, mode="classify"),
           "ecg": analyze_ecg, "eeg": analyze_eeg, "echo": analyze_echo}
    for m in manifest:
        path = str(OUT / m["modality"] / m["file"])
        try:
            r = fns[m["modality"]](path)
            if r.get("status") != "success":
                m["prediction"] = f"FAILED: {r.get('error_type')}"
                continue
            if m["modality"] == "mri":
                m["prediction"] = f"{r.get('tumor_type')} ({(r.get('tumor_type_confidence') or 0):.0%})"
            elif m["modality"] == "ecg":
                m["prediction"] = f"{r.get('diagnosis')} ({(r.get('diagnosis_confidence') or 0):.0%})"
            elif m["modality"] == "eeg":
                m["prediction"] = f"{r.get('dominant_pattern')} (harmful={r.get('harmful')})"
            elif m["modality"] == "echo":
                m["prediction"] = f"EF {r.get('ejection_fraction')}% ({r.get('ef_category')})"
        except Exception as e:  # noqa: BLE001
            m["prediction"] = f"ERROR: {type(e).__name__}: {e}"
        print(f"  [{m['modality']}] {m['file']}: truth={m.get('truth')} -> {m.get('prediction')}")
    return manifest


def write_readme(manifest):
    by = {}
    for m in manifest:
        by.setdefault(m["modality"], []).append(m)
    lines = ["# Test Samples\n",
             "Demo inputs for the four models. Filenames carry the ground-truth "
             "label (the model's own prediction is in the table below).\n"]
    titles = {
        "mri": "## MRI — REAL labeled brain-tumor images (data/brain-tumor-mri)",
        "ecg": "## ECG — REAL 12-lead CSVs, Chapman-Shaoxing-Ningbo (PhysioNet, "
               "independent of PTB-XL = unseen by the model)",
        "eeg": "## EEG — REAL labeled .edf from Kaggle-HMS (expert-consensus label)",
        "echo": "## Echo — SYNTHETIC cine clips (pipeline demo only — EF is NOT "
                "clinically meaningful; no public A4C echo set is freely downloadable)",
    }
    for mod in ("mri", "ecg", "eeg", "echo"):
        if mod not in by:
            continue
        lines.append("\n" + titles[mod] + "\n")
        lines.append("| File | Ground truth | Model prediction |")
        lines.append("|---|---|---|")
        for m in by[mod]:
            lines.append(f"| {m['file']} | {m.get('truth')} | {m.get('prediction', '(not run)')} |")
    (OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT / 'README.md'} and manifest.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["mri", "ecg", "eeg", "echo"], help="build one modality")
    ap.add_argument("--stream", type=int, default=500, help="max ECG records to stream")
    ap.add_argument("--verify", action="store_true", help="run models + (re)write README from manifest")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    mpath = OUT / "manifest.json"

    if args.verify and not args.only:
        manifest = json.loads(mpath.read_text()) if mpath.exists() else []
        verify(manifest)
        write_readme(manifest)
        return 0

    builders = {"mri": build_mri, "eeg": build_eeg,
                "ecg": lambda: build_ecg(max_stream=args.stream), "echo": build_echo}
    mods = [args.only] if args.only else ["mri", "eeg", "ecg", "echo"]

    manifest = json.loads(mpath.read_text()) if mpath.exists() else []
    manifest = [m for m in manifest if m["modality"] not in mods]  # replace rebuilt modalities
    for mod in mods:
        manifest.extend(builders[mod]())
    if args.verify:
        verify(manifest)
    mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_readme(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
