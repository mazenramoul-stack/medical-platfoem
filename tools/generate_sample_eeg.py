"""Generate a small synthetic scalp-EEG .edf for smoke-testing the EEG pipeline.

This is a *plumbing* fixture, not clinical data: it writes a standard 19-electrode
10-20 referential montage (+ EKG) at 200 Hz so ``analyze_eeg`` can be exercised
end-to-end (EDF read -> bipolar montage -> 200 Hz -> 10 s segments -> BIOT). The
signal is band-limited noise plus a few sinusoids; it carries no real pathology,
so the class output on it is meaningless by construction — use ``tools/eval_eeg.py``
on the HMS test set for real metrics.

Usage:
    python tools/generate_sample_eeg.py [--seconds 60] [--out data/samples/sample_eeg.edf]
"""

import argparse
import os

import numpy as np


# Standard 19-electrode 10-20 set used by Kaggle-HMS (+ EKG), names MNE-friendly.
ELECTRODES = [
    "Fp1", "F3", "C3", "P3", "F7", "T3", "T5", "O1", "Fz", "Cz",
    "Pz", "Fp2", "F4", "C4", "P4", "F8", "T4", "T6", "O2",
]


def _synth_eeg(n_ch: int, n_samples: int, sfreq: int, rng) -> np.ndarray:
    """Return (n_ch, n_samples) volts of band-limited, mildly-correlated noise."""
    t = np.arange(n_samples) / sfreq
    # shared rhythms (delta/theta/alpha) so channels are plausibly correlated
    base = (
        18e-6 * np.sin(2 * np.pi * 2.0 * t)
        + 12e-6 * np.sin(2 * np.pi * 6.0 * t)
        + 10e-6 * np.sin(2 * np.pi * 10.0 * t)
    )
    out = np.empty((n_ch, n_samples), dtype=np.float64)
    for i in range(n_ch):
        phase = rng.uniform(0, 2 * np.pi)
        amp = rng.uniform(0.6, 1.4)
        noise = rng.normal(0, 8e-6, n_samples)
        out[i] = amp * np.roll(base, int(phase)) + noise
    return out


def main():
    ap = argparse.ArgumentParser(description="Generate a synthetic sample EEG .edf")
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--sfreq", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument(
        "--out",
        default=os.path.join("data", "samples", "sample_eeg.edf"),
        help="output .edf path (relative to project root)",
    )
    args = ap.parse_args()

    import mne

    rng = np.random.default_rng(args.seed)
    ch_names = ELECTRODES + ["EKG"]
    n_samples = args.seconds * args.sfreq
    eeg = _synth_eeg(len(ELECTRODES), n_samples, args.sfreq, rng)
    ekg = 3e-4 * np.sin(2 * np.pi * 1.2 * np.arange(n_samples) / args.sfreq)
    data = np.vstack([eeg, ekg[None, :]])

    info = mne.create_info(ch_names, sfreq=args.sfreq, ch_types=["eeg"] * len(ELECTRODES) + ["ecg"])
    raw = mne.io.RawArray(data, info, verbose="ERROR")

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    mne.export.export_raw(out_path, raw, fmt="edf", overwrite=True, verbose="ERROR")
    print(f"Wrote {out_path}  ({len(ch_names)} ch, {args.seconds}s @ {args.sfreq}Hz)")


if __name__ == "__main__":
    main()
