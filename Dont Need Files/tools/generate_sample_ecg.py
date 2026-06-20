"""Generate realistic 12-lead ECG sample CSVs for testing the platform.

Runs four scenarios:
    normal.csv         — sinus rhythm, HR ≈ 75 bpm
    tachycardia.csv    — sinus tachycardia, HR ≈ 120 bpm
    bradycardia.csv    — sinus bradycardia, HR ≈ 45 bpm
    afib.csv           — irregular-rhythm approximation (concatenated segments
                         at varying heart rates + baseline wander). Not a true
                         AFib generator — synthesises an irregular-rhythm trace
                         that gives downstream pathology classifiers something
                         non-normal to react to.

Output: <repo_root>/samples/ecg/

Usage (from anywhere — the script resolves its own paths):
    python tools/generate_sample_ecg.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Force UTF-8 stdout — Windows cp1252 cannot encode the `→` glyph below.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        try: _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception: pass

import numpy as np
import pandas as pd

try:
    import neurokit2 as nk
except ImportError:
    sys.stderr.write(
        "neurokit2 is not installed. Activate the backend venv first:\n"
        "    cd backend && venv\\Scripts\\activate          (Windows)\n"
        "    cd backend && source venv/bin/activate         (Linux/macOS)\n"
    )
    sys.exit(2)

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SAMPLES_DIR = PROJECT_ROOT / "samples" / "ecg"

SAMPLING_RATE = 500     # Hz
DURATION_SEC = 10
TARGET_SAMPLES = SAMPLING_RATE * DURATION_SEC
LEAD_NAMES = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']


def _build_12_lead(per_lead_signal_fn) -> np.ndarray:
    """Run per_lead_signal_fn() 12 times with a small per-lead amplitude jitter.

    Returns: (samples, 12) array.
    """
    rng = np.random.default_rng(42)
    leads = []
    for _ in range(12):
        sig = per_lead_signal_fn()
        # Trim / pad to TARGET_SAMPLES
        if len(sig) < TARGET_SAMPLES:
            sig = np.pad(sig, (0, TARGET_SAMPLES - len(sig)), mode='constant')
        else:
            sig = sig[:TARGET_SAMPLES]
        # 0.9–1.1 per-lead amplitude jitter
        sig = sig * (0.9 + 0.2 * rng.random())
        leads.append(sig)
    return np.array(leads).T  # (samples, 12)


def _save_csv(arr_2d: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(arr_2d, columns=LEAD_NAMES).to_csv(path, index=False)


def generate_normal_ecg(output_path: Path) -> None:
    """Sinus rhythm, ~75 bpm."""
    arr = _build_12_lead(lambda: nk.ecg_simulate(
        duration=DURATION_SEC, sampling_rate=SAMPLING_RATE, heart_rate=75,
    ))
    _save_csv(arr, output_path)


def generate_tachycardia_ecg(output_path: Path) -> None:
    """Sinus tachycardia, ~120 bpm."""
    arr = _build_12_lead(lambda: nk.ecg_simulate(
        duration=DURATION_SEC, sampling_rate=SAMPLING_RATE, heart_rate=120,
    ))
    _save_csv(arr, output_path)


def generate_bradycardia_ecg(output_path: Path) -> None:
    """Sinus bradycardia, ~45 bpm."""
    arr = _build_12_lead(lambda: nk.ecg_simulate(
        duration=DURATION_SEC, sampling_rate=SAMPLING_RATE, heart_rate=45,
    ))
    _save_csv(arr, output_path)


def generate_afib_ecg(output_path: Path) -> None:
    """Irregular-rhythm approximation.

    Generates a single sinus rhythm at moderate HR, then layers on baseline
    wander, additional noise, and an irregularly-spaced "stutter" — produces
    a non-clean trace that the pathology classifiers can react to. Not a
    clinically accurate AFib simulation; just useful test material.

    (Earlier versions used `method='ecgsyn'` with per-segment varying HR, but
    neurokit2 1.x has a slice-int bug in that path — see issue #469 — so we
    avoid it here.)
    """
    rng = np.random.default_rng(7)

    def per_lead():
        sig = nk.ecg_simulate(
            duration=DURATION_SEC, sampling_rate=SAMPLING_RATE,
            heart_rate=85, noise=0.15,
        )
        n = len(sig)
        t = np.arange(n) / SAMPLING_RATE
        # 0.3 Hz baseline wander + low-frequency drift + small white noise
        wander = (
            0.18 * np.sin(2 * np.pi * 0.3 * t)
            + 0.08 * np.sin(2 * np.pi * 0.07 * t)
            + 0.04 * rng.standard_normal(n)
        )
        # "Stutter" — drop a short window every ~1.5 s to imitate irregular R-R
        stutter_at = np.arange(int(0.7 * SAMPLING_RATE), n, int(1.5 * SAMPLING_RATE))
        for idx in stutter_at:
            sig[idx:idx + 20] *= 0.2
        return sig + wander

    arr = _build_12_lead(per_lead)
    _save_csv(arr, output_path)


def main() -> int:
    print(f"Writing samples to: {SAMPLES_DIR}")
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    scenarios = [
        ("normal.csv",      generate_normal_ecg,      "Sinus rhythm, HR ~75 bpm"),
        ("tachycardia.csv", generate_tachycardia_ecg, "Sinus tachycardia, HR ~120 bpm"),
        ("bradycardia.csv", generate_bradycardia_ecg, "Sinus bradycardia, HR ~45 bpm"),
        ("afib.csv",        generate_afib_ecg,        "Irregular-rhythm approximation"),
    ]

    for filename, fn, desc in scenarios:
        path = SAMPLES_DIR / filename
        print(f"  {filename:18s}  {desc}")
        fn(path)
        size_kb = os.path.getsize(path) / 1024
        print(f"    → {path.relative_to(PROJECT_ROOT)}  ({size_kb:.0f} KB)")

    print(f"\nDone. {len(scenarios)} sample ECG files generated.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
