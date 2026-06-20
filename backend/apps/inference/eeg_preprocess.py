"""Shared EEG preprocessing for BIOT — imported by BOTH the inference pipeline and
the train/eval harness so training and inference see *identical* inputs.

Replicates BIOT's IIIC/TUEV pipeline exactly (github.com/ycq091044/BIOT). Do NOT
"tidy" these constants — they are what the pretrained encoder expects, and changing
them silently wrecks accuracy:

  * 16-channel longitudinal-bipolar montage ("double banana"), in BIOT's own order
    (``datasets/TUEV/process.py::convert_signals``).
  * every channel resampled to 200 Hz.
  * 10-second segments = 2000 samples (the PREST-16 encoder was pretrained on
    "16 montages x 2000 time points").
  * per-channel 95th-percentile amplitude normalisation, ``x / (q95(|x|) + 1e-8)``
    (``utils.py`` loaders). This is scale-invariant, so V-vs-µV EDF scaling is moot.

The 6 IIIC classes line up 1:1 with the Kaggle HMS vote columns.
"""

from __future__ import annotations

import re

import numpy as np

# ---- BIOT / IIIC constants (do not change without re-validating) -------------

TARGET_RATE = 200
SEGMENT_SECONDS = 10
SEGMENT_SAMPLES = TARGET_RATE * SEGMENT_SECONDS  # 2000
N_FFT = 200
HOP_LENGTH = 100
N_CHANNELS = 16

# IIIC / Kaggle-HMS 6-class scheme, in the canonical column order.
IIIC_CLASSES = ["SZ", "LPD", "GPD", "LRDA", "GRDA", "Other"]
IIIC_CLASS_NAMES = {
    "SZ": "Seizure",
    "LPD": "Lateralized Periodic Discharges",
    "GPD": "Generalized Periodic Discharges",
    "LRDA": "Lateralized Rhythmic Delta Activity",
    "GRDA": "Generalized Rhythmic Delta Activity",
    "Other": "Other / background",
}
# "Harmful brain activity" flag = any ictal/periodic-discharge pattern.
HARMFUL_CLASSES = ("SZ", "LPD", "GPD")
# Kaggle-HMS train.csv vote columns, aligned to IIIC_CLASSES order.
HMS_VOTE_COLUMNS = [
    "seizure_vote", "lpd_vote", "gpd_vote", "lrda_vote", "grda_vote", "other_vote",
]

# 16 bipolar derivations, in BIOT's convert_signals() order.
BIPOLAR_PAIRS = [
    ("FP1", "F7"), ("F7", "T7"), ("T7", "P7"), ("P7", "O1"),
    ("FP2", "F8"), ("F8", "T8"), ("T8", "P8"), ("P8", "O2"),
    ("FP1", "F3"), ("F3", "C3"), ("C3", "P3"), ("P3", "O1"),
    ("FP2", "F4"), ("F4", "C4"), ("C4", "P4"), ("P4", "O2"),
]

# Human-readable channel labels for the 16 bipolar rows above (e.g. "FP1-F7"),
# in the same row order — used by the EEG SHAP explainer's per-channel importance.
BIPOLAR_CHANNEL_NAMES = [f"{a}-{b}" for a, b in BIPOLAR_PAIRS]

# Old (10-20) -> new (10-10) electrode aliases so either nomenclature resolves.
_ELECTRODE_ALIASES = {"T3": "T7", "T4": "T8", "T5": "P7", "T6": "P8"}

_REQUIRED_ELECTRODES = sorted({e for pair in BIPOLAR_PAIRS for e in pair})


def _canon_electrode(name: str) -> str:
    """Canonicalise an EDF/parquet channel name to a bare 10-20 electrode label.

    Handles 'EEG Fp1-REF', 'Fp1', 'EEG FP1-LE', 'T3' (-> 'T7'), etc.
    """
    s = name.upper()
    s = re.sub(r"^\s*EEG\s*", "", s)        # drop a leading 'EEG'
    s = re.split(r"[-_ ]", s, maxsplit=1)[0]  # token before reference/dash
    s = re.sub(r"[^A-Z0-9]", "", s)
    return _ELECTRODE_ALIASES.get(s, s)


def _index_channels(ch_names) -> dict:
    """Map canonical electrode -> column index (first occurrence wins)."""
    idx: dict[str, int] = {}
    for i, nm in enumerate(ch_names):
        c = _canon_electrode(nm)
        if c not in idx:
            idx[c] = i
    return idx


def _missing_electrodes(index: dict) -> list:
    return [e for e in _REQUIRED_ELECTRODES if e not in index]


_KNOWN_ELECTRODES = set(_REQUIRED_ELECTRODES) | set(_ELECTRODE_ALIASES) | {
    "FZ", "CZ", "PZ", "FPZ", "OZ", "A1", "A2"}


def _looks_bipolar(ch_names) -> bool:
    """True if the channels already form a bipolar montage (e.g. 'FP1-F7').

    The BIOT montage builder assumes a REFERENTIAL (monopolar) input and computes
    differences itself. Feeding it an already-bipolar EDF re-references into
    physiological nonsense, so the pipeline must refuse rather than guess. We flag
    a file as bipolar when several channel names carry two recognised electrode
    tokens separated by a dash.
    """
    bipolar_like = 0
    for nm in ch_names:
        s = re.sub(r"^\s*EEG\s*", "", str(nm).upper())
        parts = re.split(r"[-]", s)
        if len(parts) < 2:
            continue
        a = _ELECTRODE_ALIASES.get(re.sub(r"[^A-Z0-9]", "", parts[0]),
                                   re.sub(r"[^A-Z0-9]", "", parts[0]))
        b = _ELECTRODE_ALIASES.get(re.sub(r"[^A-Z0-9]", "", parts[1]),
                                   re.sub(r"[^A-Z0-9]", "", parts[1]))
        # A referential channel's second token is a reference label (REF/LE/M1…),
        # NOT another scalp electrode — so requiring BOTH sides to be electrodes
        # distinguishes 'FP1-F7' (bipolar) from 'FP1-REF' (referential).
        if a in _KNOWN_ELECTRODES and b in _KNOWN_ELECTRODES:
            bipolar_like += 1
    return bipolar_like >= 4


def _to_bipolar(data: np.ndarray, index: dict) -> np.ndarray:
    """Build the (16, n_samples) bipolar montage from monopolar rows + name index."""
    data = np.nan_to_num(np.asarray(data, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    rows = [data[index[a]] - data[index[b]] for a, b in BIPOLAR_PAIRS]
    return np.asarray(rows, dtype=np.float32)


def edf_to_bipolar(file_path: str) -> np.ndarray:
    """Read an EDF, resample to 200 Hz, return a (16, n_samples) bipolar array.

    Raises ValueError (caught by the pipeline envelope) listing the missing
    electrodes if the referential 10-20 set required for the montage is incomplete.
    """
    import mne

    raw = mne.io.read_raw_edf(file_path, preload=True, verbose="ERROR")
    if _looks_bipolar(raw.ch_names):
        raise ValueError(
            "EDF appears to already be a bipolar/longitudinal montage "
            f"(channels like {list(raw.ch_names)[:4]}). The BIOT pipeline needs a "
            "REFERENTIAL (monopolar) 10-20 EDF and builds the bipolar montage "
            "itself; re-referencing an already-bipolar file would produce invalid "
            "results. Please upload a referential recording."
        )
    if round(float(raw.info["sfreq"])) != TARGET_RATE:
        raw.resample(TARGET_RATE, verbose="ERROR")
    data = raw.get_data()  # (n_channels, n_samples)
    index = _index_channels(raw.ch_names)
    missing = _missing_electrodes(index)
    if missing:
        raise ValueError(
            "EDF is missing referential 10-20 electrodes required for the BIOT "
            f"bipolar montage: {missing}. Channels present: {sorted(index)}"
        )
    return _to_bipolar(data, index)


def hms_parquet_to_bipolar(df) -> np.ndarray:
    """Kaggle-HMS train_eegs parquet (200 Hz monopolar columns) -> (16, n) bipolar."""
    index = _index_channels(list(df.columns))
    missing = _missing_electrodes(index)
    if missing:
        raise ValueError(f"HMS parquet missing electrodes: {missing}")
    data = df.to_numpy(dtype=np.float32).T  # (n_channels, n_samples)
    return _to_bipolar(data, index)


def normalize_segment(seg: np.ndarray) -> np.ndarray:
    """Per-channel 95th-percentile amplitude normalisation — BIOT parity.

    seg: (16, SEGMENT_SAMPLES) -> same shape, amplitude-normalised.
    """
    q = np.quantile(np.abs(seg), 0.95, axis=-1, keepdims=True)
    return (seg / (q + 1e-8)).astype(np.float32)


def _fit_to_segment(seg: np.ndarray, n: int = SEGMENT_SAMPLES) -> np.ndarray:
    """Pad (by tiling) or trim a short clip to exactly n samples."""
    if seg.shape[1] == n:
        return seg
    if seg.shape[1] > n:
        return seg[:, :n]
    reps = int(np.ceil(n / max(1, seg.shape[1])))
    return np.tile(seg, (1, reps))[:, :n]


def central_segment(bipolar: np.ndarray, offset_seconds: float = 0.0) -> np.ndarray:
    """Extract + normalise the scored central 10 s of an HMS 50 s window.

    HMS scores the central 10 s of the 50 s window that begins at
    ``eeg_label_offset_seconds`` -> samples [offset+20s, offset+30s].
    """
    start = int(round((offset_seconds + 20.0) * TARGET_RATE))
    start = max(0, min(start, max(0, bipolar.shape[1] - SEGMENT_SAMPLES)))
    seg = bipolar[:, start:start + SEGMENT_SAMPLES]
    return normalize_segment(_fit_to_segment(seg))


def segment_recording(bipolar: np.ndarray) -> list:
    """Split a (16, T) recording into consecutive normalised (16, 2000) segments.

    Recordings shorter than one 10 s window yield a single tiled+normalised segment,
    so there is always at least one segment to classify.
    """
    t = bipolar.shape[1]
    if t < SEGMENT_SAMPLES:
        return [normalize_segment(_fit_to_segment(bipolar))]
    n = t // SEGMENT_SAMPLES
    return [
        normalize_segment(bipolar[:, i * SEGMENT_SAMPLES:(i + 1) * SEGMENT_SAMPLES])
        for i in range(n)
    ]


def stack_segments(segments: list):
    """List of (16, 2000) arrays -> a single (n, 16, 2000) float32 torch tensor."""
    import torch

    return torch.from_numpy(np.stack(segments, axis=0).astype(np.float32))
