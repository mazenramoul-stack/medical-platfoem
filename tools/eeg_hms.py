"""Shared Kaggle-HMS data helpers for the EEG train/eval harness.

The Kaggle "HMS — Harmful Brain Activity Classification" dataset is the public
IIIC task: each labelled window carries 6 expert *vote* columns that line up 1:1
with BIOT's IIIC classes. We reuse the deployed pipeline's preprocessing
(``apps.inference.eeg_preprocess``) so training sees byte-identical inputs to
inference.

Expected local layout (a subset is fine — see tools/train_eeg_head.py --download):
    <hms_dir>/train.csv
    <hms_dir>/train_eegs/<eeg_id>.parquet      (200 Hz monopolar 10-20 + EKG)

This module does no training and no Kaggle I/O; it only turns a local HMS dir
into (segment, label, votes) samples.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from apps.inference.eeg_preprocess import (  # noqa: E402
    HMS_VOTE_COLUMNS,
    IIIC_CLASSES,
    central_segment,
    hms_parquet_to_bipolar,
)


def load_index(hms_dir, limit=0, balanced=True, seed=0):
    """Read train.csv into a list of sample dicts (filtered to locally-present parquet).

    Each sample: {eeg_id, offset_seconds, votes (np.float32[6], normalised),
                  label (int argmax), patient_id}.
    """
    import pandas as pd

    hms_dir = Path(hms_dir)
    df = pd.read_csv(hms_dir / "train.csv")
    votes = df[HMS_VOTE_COLUMNS].to_numpy(dtype=np.float32)
    totals = votes.sum(axis=1, keepdims=True)
    df = df.assign(_label=votes.argmax(axis=1))
    df["_votes"] = list(votes / np.clip(totals, 1.0, None))

    eeg_dir = hms_dir / "train_eegs"
    present = {p.stem for p in eeg_dir.glob("*.parquet")} if eeg_dir.is_dir() else set()
    if present:
        df = df[df["eeg_id"].astype(str).isin(present)]

    rng = np.random.default_rng(seed)
    df = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)

    if limit and len(df) > limit:
        if balanced:
            per = max(1, limit // len(IIIC_CLASSES))
            parts = [g.head(per) for _, g in df.groupby("_label")]
            df = (
                pd.concat(parts)
                .sample(frac=1.0, random_state=seed)
                .head(limit)
                .reset_index(drop=True)
            )
        else:
            df = df.head(limit)

    samples = []
    for _, r in df.iterrows():
        samples.append({
            "eeg_id": int(r["eeg_id"]),
            "offset_seconds": float(r.get("eeg_label_offset_seconds", 0.0) or 0.0),
            "votes": np.asarray(r["_votes"], dtype=np.float32),
            "label": int(r["_label"]),
            "patient_id": int(r.get("patient_id", -1)),
        })
    return samples


def patient_split(samples, test_frac=0.2, seed=0):
    """Split by patient_id so no patient appears in both train and test."""
    rng = np.random.default_rng(seed)
    patients = sorted({s["patient_id"] for s in samples})
    rng.shuffle(patients)
    n_test = max(1, int(round(len(patients) * test_frac)))
    test_patients = set(patients[:n_test])
    train = [s for s in samples if s["patient_id"] not in test_patients]
    test = [s for s in samples if s["patient_id"] in test_patients]
    return train, test


def iter_segments(hms_dir, samples):
    """Yield (sample, (16, 2000) normalised float32 segment), caching each parquet."""
    import pandas as pd

    eeg_dir = Path(hms_dir) / "train_eegs"
    cache_id, cache_bip = None, None
    for s in samples:
        if s["eeg_id"] != cache_id:
            path = eeg_dir / f'{s["eeg_id"]}.parquet'
            if not path.exists():
                continue
            cache_bip = hms_parquet_to_bipolar(pd.read_parquet(path))
            cache_id = s["eeg_id"]
        seg = central_segment(cache_bip, s["offset_seconds"])
        yield s, seg
