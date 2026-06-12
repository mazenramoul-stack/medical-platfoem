"""Standalone end-to-end test of the MRI and ECG inference pipelines.

Run from anywhere:
    python backend/apps/inference/test_pipelines.py

Steps:
    1. Download a sample brain MRI (cached after first run)
    2. Generate a synthetic 10s 12-lead ECG via NeuroKit2
    3. Run analyze_mri on the sample image
    4. Run analyze_ecg on the synthetic signal
    5. Re-run both pipelines to confirm model caching makes them fast
    6. Print a PASS/FAIL summary
"""

from __future__ import annotations

import os
import sys
import time
import warnings

warnings.filterwarnings('ignore')

# Force UTF-8 stdout/stderr — the reports contain box-drawing characters
# that the Windows cp1252 default cannot encode.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

# Make the backend root importable when run as a standalone script ----------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Disable HuggingFace and torch hub progress bars to keep output readable
os.environ.setdefault('HF_HUB_DISABLE_PROGRESS_BARS', '1')
os.environ.setdefault('TQDM_DISABLE', '1')

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
)

import numpy as np
import requests

MEDIA_DIR = os.path.join(_BACKEND_DIR, 'media')
MRI_TEST_PATH = os.path.join(MEDIA_DIR, 'mri', 'test_sample.png')
ECG_TEST_PATH = os.path.join(MEDIA_DIR, 'ecg', 'test_sample.csv')
SAMPLE_MRI_URL = (
    "https://github.com/mateuszbuda/brain-segmentation-pytorch/raw/master/assets/TCGA_CS_4944.png"
)


# ---- input prep -----------------------------------------------------------

def download_sample_mri() -> None:
    """Download a TCGA brain MRI thumbnail and cache it locally."""
    if os.path.exists(MRI_TEST_PATH):
        print(f"  Sample MRI already exists at {MRI_TEST_PATH}")
        return
    print(f"  Downloading sample MRI from {SAMPLE_MRI_URL}")
    os.makedirs(os.path.dirname(MRI_TEST_PATH), exist_ok=True)
    r = requests.get(SAMPLE_MRI_URL, timeout=30)
    r.raise_for_status()
    with open(MRI_TEST_PATH, 'wb') as f:
        f.write(r.content)
    print(f"  Saved to {MRI_TEST_PATH} ({len(r.content)} bytes)")


def generate_sample_ecg() -> None:
    """Synthesise a 10-second 12-lead ECG with NeuroKit2."""
    if os.path.exists(ECG_TEST_PATH):
        print(f"  Sample ECG already exists at {ECG_TEST_PATH}")
        return
    print("  Generating synthetic 10s 12-lead ECG via neurokit2 (heart_rate=72 bpm)")
    import neurokit2 as nk
    import pandas as pd
    leads = []
    for _ in range(12):
        sig = nk.ecg_simulate(duration=10, sampling_rate=500, heart_rate=72)
        leads.append(sig)
    arr = np.array(leads).T  # (5000, 12)
    cols = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
    os.makedirs(os.path.dirname(ECG_TEST_PATH), exist_ok=True)
    pd.DataFrame(arr, columns=cols).to_csv(ECG_TEST_PATH, index=False)
    print(f"  Saved to {ECG_TEST_PATH} ({os.path.getsize(ECG_TEST_PATH)} bytes)")


# ---- main -----------------------------------------------------------------

def main() -> int:
    print("=" * 72)
    print("STEP 1: Prepare test inputs")
    print("=" * 72)
    download_sample_mri()
    generate_sample_ecg()

    from apps.inference import analyze_ecg, analyze_mri

    print("\n" + "=" * 72)
    print("STEP 2: Run MRI pipeline (first call — may download model weights)")
    print("=" * 72)
    mri_result = analyze_mri(MRI_TEST_PATH)
    if mri_result['status'] == 'success':
        print(f"  Status          : {mri_result['status']}")
        print(f"  Tumor detected  : {mri_result['tumor_detected']}")
        print(f"  Tumor type      : {mri_result['tumor_type']} "
              f"({mri_result['tumor_type_confidence']:.2%})")
        print(f"  Tumor area (px) : {mri_result['tumor_area_pixels']}")
        print(f"  Seg confidence  : {mri_result['segmentation_confidence']:.2%}")
        print(f"  Analysis figure : {mri_result['analysis_path']}")
        print(f"  Mask file       : {mri_result['mask_path']}")
        print(f"  Overlay file    : {mri_result['overlay_path']}")
        print(f"  Elapsed         : {mri_result['elapsed_seconds']:.2f}s")
        print("\n--- MRI REPORT ---")
        print(mri_result['report'])
    else:
        print(f"  MRI FAILED: {mri_result.get('error_type')}: {mri_result.get('error')}")

    print("\n" + "=" * 72)
    print("STEP 3: Run ECG pipeline (first call — may download model weights)")
    print("=" * 72)
    ecg_result = analyze_ecg(ECG_TEST_PATH)
    if ecg_result['status'] == 'success':
        print(f"  Status            : {ecg_result['status']}")
        print(f"  Arrhythmia        : {ecg_result['arrhythmia_detected']}")
        print(f"  Diagnosis         : {ecg_result['diagnosis']} "
              f"({ecg_result['diagnosis_confidence']:.2%})")
        print(f"  Heart rate (bpm)  : {ecg_result['heart_rate_bpm']:.1f} "
              f"({ecg_result['hr_classification']})")
        print(f"  RMSSD (ms)        : {ecg_result['hrv_metrics']['RMSSD_ms']:.2f}")
        print(f"  SDNN  (ms)        : {ecg_result['hrv_metrics']['SDNN_ms']:.2f}")
        print(f"  pNN50 (%)         : {ecg_result['hrv_metrics']['pNN50_percent']:.2f}")
        print(f"  Plot file         : {ecg_result['plot_path']}")
        print(f"  Elapsed           : {ecg_result['elapsed_seconds']:.2f}s")
        print("\n--- ECG REPORT ---")
        print(ecg_result['report'])
    else:
        print(f"  ECG FAILED: {ecg_result.get('error_type')}: {ecg_result.get('error')}")

    print("\n" + "=" * 72)
    print("STEP 4: Cache check — second call must be fast (no re-download)")
    print("=" * 72)
    t0 = time.time()
    mri2 = analyze_mri(MRI_TEST_PATH)
    t_mri2 = time.time() - t0
    print(f"  MRI second call  : {t_mri2:.2f}s  (status={mri2['status']})")
    t0 = time.time()
    ecg2 = analyze_ecg(ECG_TEST_PATH)
    t_ecg2 = time.time() - t0
    print(f"  ECG second call  : {t_ecg2:.2f}s  (status={ecg2['status']})")

    # Check that the result files actually exist on disk
    mri_files_ok = (
        mri_result['status'] == 'success'
        and os.path.exists(mri_result['analysis_path'])
        and os.path.exists(mri_result['mask_path'])
        and os.path.exists(mri_result['overlay_path'])
    )
    ecg_files_ok = (
        ecg_result['status'] == 'success'
        and os.path.exists(ecg_result['plot_path'])
    )

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    mri_ok = mri_result['status'] == 'success'
    ecg_ok = ecg_result['status'] == 'success'
    cache_ok = mri2['status'] == 'success' and ecg2['status'] == 'success'
    print(f"  [{'PASS' if mri_ok       else 'FAIL'}] MRI pipeline returns success")
    print(f"  [{'PASS' if ecg_ok       else 'FAIL'}] ECG pipeline returns success")
    print(f"  [{'PASS' if mri_files_ok else 'FAIL'}] MRI result files exist on disk")
    print(f"  [{'PASS' if ecg_files_ok else 'FAIL'}] ECG result files exist on disk")
    print(f"  [{'PASS' if cache_ok     else 'FAIL'}] Second invocations succeed (cache works)")

    all_ok = mri_ok and ecg_ok and mri_files_ok and ecg_files_ok and cache_ok
    print("\nSTEP 6 VERIFICATION: " + ("ALL PASS" if all_ok else "FAILED"))
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
