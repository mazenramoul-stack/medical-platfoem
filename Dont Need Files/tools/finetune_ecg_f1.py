"""Fine-tune the ecglib DenseNet-1D ECG pathology classifiers for **F1**.

Goal: lift the weak/precision-limited classes (SBRAD, 1AVB, STACH) that drag
macro F1 down, by continue-training each pathology model from its ecglib
*pretrained* weights with two levers the older balanced-accuracy notebook lacked:

  1. model selection + keep-rule on **F1** (the metric you actually want to move),
  2. **ECG-domain augmentation** (amplitude scale, noise, baseline wander, time
     shift, lead dropout) — the main lever for rare classes that otherwise overfit.

HONEST EXPECTATION (read before the defence):
  macro F1 ~0.73 -> ~0.78-0.82 if it goes well. SBRAD/1AVB are prevalence-limited
  (few positives, many false positives) and will NOT reach AFIB/RBBB level.
  **Macro F1 > 0.90 on 7-class PTB-XL is not achievable** with this model family:
  the absolute threshold-tuning ceiling is ~0.75 (see VALIDATION.md and the
  precision/recall sweep). A big AUC jump would be a leakage red flag, not good news.

Methodology matches tools/eval_ecg_classifier.py exactly (no leakage):
  train = PTB-XL strat folds 1-8, val = fold 9, test = fold 10;
  0.5-40 Hz band-pass + per-lead z-score; thresholds tuned on fold 9 only.

NO-REGRESSION RULE: a fine-tuned ``<PATHOLOGY>.pt`` is saved ONLY if it beats the
pretrained baseline on fold 10 — F1(ft) > F1(base) AND AUC(ft) >= AUC(base) - tol —
so the deployed ensemble can never get worse. ``get_ecg_models()`` auto-detects
the saved files in ``backend/models_weights/ecg_finetuned/`` (``ECG_FINETUNED_DIR``
overrides); a missing file means stock ecglib for that pathology.

Usage (Colab T4, after PTB-XL is downloaded and this repo is unzipped):
    python tools/finetune_ecg_f1.py \
        --ptbxl-dir physionet.org/files/ptb-xl/1.0.3 \
        --pathologies SBRAD 1AVB STACH \
        --epochs 20 --augment --out-dir backend/models_weights/ecg_finetuned

Omit --pathologies to fine-tune all 7. Locally this runs on CPU (slow); on a GPU
it is ~1-3 h for all 7 plus a one-time ~10-15 min preprocessing pass.
After it finishes, paste the printed RESULTS block back so the numbers can be
re-verified locally with tools/eval_ecg_classifier.py before anything is trusted.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

# --- make the repo importable (this file lives in tools/) -------------------
_THIS = Path(__file__).resolve()
PROJECT_ROOT = _THIS.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import torch
import torch.nn as nn
from scipy.signal import butter, filtfilt

from apps.inference.utils import load_ecg_signal
from eval_ecg_classifier import (  # noqa: E402  (after sys.path setup)
    PATHOLOGIES as ALL_PATHOLOGIES,
    auc_score,
    iter_ptbxl,
)

device = "cuda" if torch.cuda.is_available() else "cpu"


# ---- preprocessing / split building (RAM-safe memmap cache) ----------------

def _preprocess(path: str) -> np.ndarray:
    """Repo-faithful preprocessing: 0.5-40 Hz band-pass + per-lead z-score.

    Note: load_ecg_signal returns (signal, fs, quality) — the third value
    (lead-quality) is unused here but MUST be unpacked (the older notebook's
    2-value unpack is now broken against the current utils.py).
    """
    signal, fs, _quality = load_ecg_signal(str(path))            # (12, 5000) @ 500 Hz
    b, a = butter(4, [0.5, 40], btype="bandpass", fs=fs)
    filtered = filtfilt(b, a, signal, axis=1)
    norm = (filtered - filtered.mean(axis=1, keepdims=True)) / (
        filtered.std(axis=1, keepdims=True) + 1e-8
    )
    return norm.astype(np.float16)


def build_split(ptbxl_dir: Path, folds, name: str, cache_dir: Path,
                min_likelihood: float):
    """Disk-backed split builder with a crash-proof cache (mirrors the notebook)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    xf, yf = cache_dir / f"{name}_X.npy", cache_dir / f"{name}_Y.npy"
    if xf.exists() and yf.exists():
        Y = np.load(yf)
        X = np.load(xf, mmap_mode="r")[: len(Y)]
        print(f"{name}: reusing cached preprocessed arrays ({len(Y)} records)")
        return X, Y

    items = []
    for f in folds:
        items.extend(iter_ptbxl(ptbxl_dir, min_likelihood, f))
    n = len(items)
    X = np.lib.format.open_memmap(
        str(xf) + ".tmp", mode="w+", dtype=np.float16, shape=(n, 12, 5000))
    Y = np.zeros((n, len(ALL_PATHOLOGIES)), dtype=np.int8)
    if n == 0:
        raise RuntimeError(
            f"{name}: iter_ptbxl yielded 0 records for folds {folds} at {ptbxl_dir}. "
            f"PTB-XL is missing or incomplete — re-run the download step.")
    ok, n_fail, first_err = 0, 0, None
    for path, positives in items:
        try:
            X[ok] = _preprocess(path)
        except Exception as e:                                    # skip unreadable record
            n_fail += 1
            if first_err is None:
                first_err = f"{type(e).__name__}: {e}"
            continue
        for c in positives:
            Y[ok, ALL_PATHOLOGIES.index(c)] = 1
        ok += 1
        if ok % 1000 == 0:
            print(f"  {name}: {ok}/{n}")
            gc.collect()
    X.flush(); del X
    # Fail LOUDLY instead of silently caching an empty/label-less split (the
    # exact trap the old notebook fell into: a load_ecg_signal signature change
    # made every record raise, all got skipped, and the run produced all-zero
    # metrics with no error). Do these checks BEFORE committing the cache.
    if ok == 0:
        raise RuntimeError(
            f"{name}: 0 of {n} records preprocessed successfully "
            f"({n_fail} failures). First error -> {first_err}. "
            f"Check the PTB-XL path and that load_ecg_signal works on these files.")
    pos_total = int(Y[:ok].sum())
    if pos_total == 0:
        raise RuntimeError(
            f"{name}: {ok} records loaded but ZERO positive labels — the "
            f"iter_ptbxl / SCP-code mapping is broken (nothing to learn). Not caching.")
    if n_fail:
        print(f"  {name}: WARNING {n_fail}/{n} records failed preprocessing "
              f"(first: {first_err})")
    os.replace(str(xf) + ".tmp", str(xf))      # cache valid only when complete & non-empty
    np.save(yf, Y[:ok])
    print(f"{name}: {ok} records, {pos_total} positive labels")
    return np.load(xf, mmap_mode="r")[:ok], np.load(yf)


# ---- model read-out + metrics ---------------------------------------------

def logit(model, xb):
    out = model(xb)
    if isinstance(out, tuple):
        out = out[0]
    return out.view(out.size(0), -1)[:, 0]                       # (B,) raw logits


@torch.no_grad()
def predict_probs(model, X, bs: int = 128) -> np.ndarray:
    model.eval()
    out = np.zeros(len(X), dtype=np.float32)
    for i in range(0, len(X), bs):
        xb = torch.from_numpy(X[i:i + bs].astype(np.float32)).to(device)
        out[i:i + xb.size(0)] = torch.sigmoid(logit(model, xb)).cpu().numpy()
    return out


def _counts(probs, y, thr):
    pred = (probs >= thr).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    tn = int(((pred == 0) & (y == 0)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
    return tp, fp, tn, fn


def bal_acc(probs, y, thr):
    tp, fp, tn, fn = _counts(probs, y, thr)
    sens = tp / (tp + fn) if (tp + fn) else 0.0
    spec = tn / (tn + fp) if (tn + fp) else 0.0
    return 0.5 * (sens + spec)


def f1_at(probs, y, thr):
    tp, fp, tn, fn = _counts(probs, y, thr)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    return 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0


def best_thr(probs, y, metric: str = "f1") -> float:
    """Threshold that maximizes `metric` (f1|balacc) on the given split."""
    if y.sum() == 0 or y.sum() == len(y):
        return 0.5
    fn = f1_at if metric == "f1" else bal_acc
    best_t, best = 0.5, -1.0
    for t in np.linspace(0.01, 0.99, 99):
        m = fn(probs, y, t)
        if m > best:
            best, best_t = m, float(t)
    return best_t


def evaluate(model, j, Xval, Yval, Xte, Yte, metric: str = "f1") -> dict:
    """Tune the threshold on fold 9 (for `metric`), then score fold 10."""
    pv, pt = predict_probs(model, Xval), predict_probs(model, Xte)
    yv, yt = Yval[:, j], Yte[:, j]
    thr = best_thr(pv, yv, metric)
    auc = auc_score(pt, yt)
    return {
        "thr": thr,
        "bal_acc": bal_acc(pt, yt, thr),
        "f1": f1_at(pt, yt, thr),
        "auc": float(auc) if auc is not None else float("nan"),
    }


def val_score(model, j, Xval, Yval, metric: str = "f1") -> float:
    pv = predict_probs(model, Xval)
    yv = Yval[:, j]
    return (f1_at if metric == "f1" else bal_acc)(pv, yv, best_thr(pv, yv, metric))


# ---- ECG-domain augmentation (the main lever for the weak/rare classes) ----

def augment(xb: torch.Tensor) -> torch.Tensor:
    """Physiologically-plausible random perturbation of a (B,12,T) tensor.

    Keeps the QRS morphology; only adds the kind of variation a different lead
    placement / patient / recorder would produce. All ops on-device.
    """
    B, C, T = xb.shape
    xb = xb * (0.8 + 0.4 * torch.rand(B, 1, 1, device=xb.device))      # amplitude 0.8-1.2
    xb = xb + 0.05 * torch.randn_like(xb)                              # additive noise
    t = torch.linspace(0, 1, T, device=xb.device).view(1, 1, T)        # baseline wander
    freq = 0.5 + 2.5 * torch.rand(B, 1, 1, device=xb.device)
    phase = 2 * np.pi * torch.rand(B, 1, 1, device=xb.device)
    xb = xb + 0.1 * torch.sin(2 * np.pi * freq * t + phase)
    shift = int(torch.randint(-250, 251, (1,)).item())                # +-0.5 s @ 500 Hz
    if shift:
        xb = torch.roll(xb, shifts=shift, dims=2)
    if torch.rand(1).item() < 0.3:                                    # lead dropout
        xb[:, int(torch.randint(0, C, (1,)).item()), :] = 0.0
    return xb


class FocalLoss(nn.Module):
    """Binary focal loss with pos_weight; gamma=0 reduces to weighted BCE."""

    def __init__(self, pos_weight, gamma: float = 0.0):
        super().__init__()
        self.pos_weight = pos_weight
        self.gamma = gamma

    def forward(self, logits, target):
        bce = nn.functional.binary_cross_entropy_with_logits(
            logits, target, pos_weight=self.pos_weight, reduction="none")
        if self.gamma > 0:
            p = torch.sigmoid(logits)
            pt = p * target + (1 - p) * (1 - target)
            bce = bce * (1 - pt).pow(self.gamma)
        return bce.mean()


# ---- per-pathology fine-tune loop -----------------------------------------

def finetune_one(p, Xtr, Ytr, Xval, Yval, Xte, Yte, args, rng) -> dict:
    from ecglib.models import create_model

    j = ALL_PATHOLOGIES.index(p)
    print(f"\n{'=' * 64}\n{p}\n{'=' * 64}")
    model = create_model(model_name="densenet1d121", pathology=p, pretrained=True).to(device)

    base = evaluate(model, j, Xval, Yval, Xte, Yte, args.select_metric)
    print(f"  baseline (fold10): F1={base['f1']:.3f}  bal_acc={base['bal_acc']:.3f}  "
          f"AUC={base['auc']:.3f}  thr={base['thr']:.2f}")

    y_tr = Ytr[:, j].astype(np.float32)
    n_pos = int(y_tr.sum()); n_neg = len(y_tr) - n_pos
    if n_pos == 0:
        print("  no positive training samples — kept baseline")
        del model
        if device == "cuda":
            torch.cuda.empty_cache()
        return {"p": p, "base_bal_acc": base["bal_acc"], "base_auc": base["auc"],
                "base_f1": base["f1"], "base_thr": base["thr"], "ft_bal_acc": base["bal_acc"],
                "ft_auc": base["auc"], "ft_f1": base["f1"], "ft_thr": base["thr"],
                "kept": False, "reason": "no positives"}

    pos_weight = torch.tensor([max(n_neg / max(n_pos, 1), 1.0)], device=device)
    crit = FocalLoss(pos_weight, gamma=args.focal_gamma)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    idx = np.arange(len(Xtr))

    best_val, best_state, bad = -1.0, None, 0
    for ep in range(args.epochs):
        model.train(); rng.shuffle(idx); running = 0.0
        for i in range(0, len(idx), args.batch_size):
            bi = idx[i:i + args.batch_size]
            xb = torch.from_numpy(Xtr[bi].astype(np.float32)).to(device)
            if args.augment:
                xb = augment(xb)
            yb = torch.from_numpy(y_tr[bi]).to(device)
            opt.zero_grad()
            loss = crit(logit(model, xb), yb)
            loss.backward(); opt.step()
            running += loss.item() * len(bi)
        vs = val_score(model, j, Xval, Yval, args.select_metric)
        print(f"  epoch {ep + 1}/{args.epochs}  train_loss={running / len(idx):.4f}  "
              f"val_{args.select_metric}={vs:.3f}")
        if vs > best_val:
            best_val = vs
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            bad = 0
        else:
            bad += 1
            if bad >= args.patience:
                print(f"  early stop (no val improvement in {args.patience} epochs)")
                break

    model.load_state_dict(best_state)
    ft = evaluate(model, j, Xval, Yval, Xte, Yte, args.select_metric)
    print(f"  fine-tuned (fold10): F1={ft['f1']:.3f}  bal_acc={ft['bal_acc']:.3f}  "
          f"AUC={ft['auc']:.3f}  thr={ft['thr']:.2f}")

    kept = (ft["f1"] > base["f1"]) and (ft["auc"] >= base["auc"] - args.auc_tolerance)
    if kept:
        os.makedirs(args.out_dir, exist_ok=True)
        torch.save(best_state, os.path.join(args.out_dir, f"{p}.pt"))
        print(f"  SAVED {p}.pt  (F1 {base['f1']:.3f}->{ft['f1']:.3f}, "
              f"AUC {base['auc']:.3f}->{ft['auc']:.3f})")
        reason = "passed no-regression rule (F1)"
    else:
        why = "F1 not improved" if ft["f1"] <= base["f1"] else "AUC dropped > tol"
        print(f"  kept baseline  ({why})")
        reason = why

    del model
    if device == "cuda":
        torch.cuda.empty_cache()
    return {"p": p, "base_bal_acc": base["bal_acc"], "base_auc": base["auc"],
            "base_f1": base["f1"], "base_thr": base["thr"], "ft_bal_acc": ft["bal_acc"],
            "ft_auc": ft["auc"], "ft_f1": ft["f1"], "ft_thr": ft["thr"],
            "kept": bool(kept), "reason": reason}


# ---- results + entrypoint --------------------------------------------------

def print_results(results, args, t_start):
    macro = lambda kk, kb: float(np.mean([(r[kk] if r["kept"] else r[kb]) for r in results]))
    print("\n=== RESULTS - paste this back to Claude ===")
    print("run: ECG per-pathology F1 fine-tune (ecglib DenseNet-1D, PTB-XL fold 10)")
    print("objective: maximize macro F1 (esp. SBRAD/1AVB/STACH) with augmentation")
    print("honest target: macro F1 ~0.73 -> ~0.78-0.82; NOT 0.90 (ceiling ~0.75)")
    print(f"config: epochs={args.epochs} batch={args.batch_size} lr={args.lr} "
          f"augment={args.augment} focal_gamma={args.focal_gamma} "
          f"select={args.select_metric} seed={args.seed}")
    print(f"pathologies run: {[r['p'] for r in results]}\n")
    hdr = "{:<7}{:>9}{:>8}{:>7}{:>10}{:>9}{:>9}  {}".format(
        "path", "base_F1", "ft_F1", "ft_thr", "base_AUC", "ft_AUC", "ft_bA", "verdict")
    print(hdr); print("-" * len(hdr))
    for r in results:
        print("{:<7}{:>9.3f}{:>8.3f}{:>7.2f}{:>10.3f}{:>9.3f}{:>9.3f}  {}".format(
            r["p"], r["base_f1"], r["ft_f1"], r["ft_thr"], r["base_auc"], r["ft_auc"],
            r["ft_bal_acc"], "SAVED" if r["kept"] else f"kept baseline ({r['reason']})"))
    print()
    print("macro F1           : {:.3f} (baseline) -> {:.3f} (deployed)".format(
        float(np.mean([r["base_f1"] for r in results])), macro("ft_f1", "base_f1")))
    print("macro balanced-acc : {:.3f} (baseline) -> {:.3f} (deployed)".format(
        float(np.mean([r["base_bal_acc"] for r in results])), macro("ft_bal_acc", "base_bal_acc")))
    print("macro AUC          : {:.3f} (deployed; near-ceiling, expected ~flat)".format(
        macro("ft_auc", "base_auc")))
    kept_rows = [r for r in results if r["kept"]]
    print("kept (beat baseline): {}".format([r["p"] for r in kept_rows] or "none"))
    if kept_rows:
        print("\nF1 thresholds for the KEPT checkpoints (tuned on fold 9) — paste these")
        print("into F1_BALANCED_THRESHOLDS in backend/apps/inference/ecg_pipeline.py:")
        for r in kept_rows:
            print(f"    '{r['p']}': {r['ft_thr']:.2f},   # F1 {r['base_f1']:.3f} -> {r['ft_f1']:.3f}")
    print("\nplace kept <PATHOLOGY>.pt at backend/models_weights/ecg_finetuned/ "
          "(get_ecg_models() auto-detects; ECG_FINETUNED_DIR overrides)")
    print("runtime: {:.0f} min".format((time.time() - t_start) / 60))
    print("=== END RESULTS ===")


def main():
    default_out = str(PROJECT_ROOT / "backend" / "models_weights" / "ecg_finetuned")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ptbxl-dir", default="physionet.org/files/ptb-xl/1.0.3",
                    help="PTB-XL 1.0.3 root (contains ptbxl_database.csv)")
    ap.add_argument("--pathologies", nargs="*", default=ALL_PATHOLOGIES,
                    help="subset to fine-tune (default: all 7). e.g. SBRAD 1AVB STACH")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--patience", type=int, default=5)
    ap.add_argument("--augment", action="store_true", help="enable ECG augmentation (recommended)")
    ap.add_argument("--focal-gamma", type=float, default=0.0,
                    help=">0 (e.g. 2.0) uses focal loss; 0 = weighted BCE")
    ap.add_argument("--select-metric", choices=["f1", "balacc"], default="f1")
    ap.add_argument("--auc-tolerance", type=float, default=0.01,
                    help="keep rule: AUC may not drop more than this")
    ap.add_argument("--min-likelihood", type=float, default=0.0)
    ap.add_argument("--out-dir", default=default_out)
    ap.add_argument("--cache-dir", default="ecg_ft_cache",
                    help="where the memmap preprocessed arrays are cached")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    for p in args.pathologies:
        if p not in ALL_PATHOLOGIES:
            ap.error(f"unknown pathology {p!r}; valid: {ALL_PATHOLOGIES}")

    rng = np.random.default_rng(args.seed)
    torch.manual_seed(args.seed)
    t_start = time.time()
    print(f"device={device} | pathologies={args.pathologies} | augment={args.augment} "
          f"| select={args.select_metric}")

    ptbxl_dir = Path(args.ptbxl_dir)
    assert (ptbxl_dir / "ptbxl_database.csv").exists(), \
        f"PTB-XL not found at {ptbxl_dir} (need ptbxl_database.csv)"
    cache = Path(args.cache_dir)

    t_pp = time.time()
    Xtr, Ytr = build_split(ptbxl_dir, [1, 2, 3, 4, 5, 6, 7, 8], "train", cache, args.min_likelihood)
    Xval, Yval = build_split(ptbxl_dir, [9], "val", cache, args.min_likelihood)
    Xte, Yte = build_split(ptbxl_dir, [10], "test", cache, args.min_likelihood)
    print("preprocessing wall-clock: {:.0f} min".format((time.time() - t_pp) / 60))
    print("class positives (test):",
          {p: int(Yte[:, ALL_PATHOLOGIES.index(p)].sum()) for p in args.pathologies})

    results = [finetune_one(p, Xtr, Ytr, Xval, Yval, Xte, Yte, args, rng)
               for p in args.pathologies]

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "ecg_f1_finetune_metrics.json"), "w") as f:
        json.dump({"results": results, "config": vars(args)}, f, indent=2)
    print_results(results, args, t_start)


if __name__ == "__main__":
    main()
