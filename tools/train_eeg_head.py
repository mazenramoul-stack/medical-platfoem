"""Fine-tune the BIOT IIIC 6-class head on Kaggle-HMS (encoder frozen).

BIOT releases only a pretrained *encoder* (no IIIC classification head), so we
attach BIOT's own ``ClassificationHead`` and train just that head on the public
Kaggle "HMS — Harmful Brain Activity Classification" labels. The encoder is frozen,
so we extract its 256-d embeddings once and then train the small head cheaply —
feasible on CPU.

Output is a full ``BIOTClassifier`` state_dict (encoder + trained head) that
``model_loader.get_eeg_model()`` loads from BIOT_IIIC_WEIGHTS.

Usage (from project root):
    # 1. point Kaggle at your creds (~/.kaggle/kaggle.json) and accept the HMS rules.
    # 2. optionally let the script pull a balanced subset that fits a small disk:
    python tools/train_eeg_head.py --download 600 --hms-dir data/hms --out backend/models_weights/biot/biot_iiic.pt
    # or train from an already-downloaded HMS dir:
    python tools/train_eeg_head.py --hms-dir data/hms --limit 4000 --epochs 80
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DEFAULT_OUT = BACKEND_DIR / "models_weights" / "biot" / "biot_iiic.pt"
DEFAULT_ENCODER = BACKEND_DIR / "models_weights" / "biot" / "EEG-PREST-16-channels.ckpt"
HMS_COMP = "hms-harmful-brain-activity-classification"


def _kaggle_auth_header() -> str:
    """Authorization header for the Kaggle v1 REST API.

    Prefers the newer ``KGAT_`` API token (``KAGGLE_API_TOKEN``, Bearer); falls back
    to classic ``KAGGLE_USERNAME``/``KAGGLE_KEY`` basic auth. The classic ``kaggle``
    pip package does not understand ``KGAT_`` tokens, so we talk to the API directly.
    """
    import base64

    token = os.environ.get("KAGGLE_API_TOKEN")
    user, key = os.environ.get("KAGGLE_USERNAME"), os.environ.get("KAGGLE_KEY")
    if token:
        return "Bearer " + token
    if user and key:
        return "Basic " + base64.b64encode(f"{user}:{key}".encode()).decode()
    raise RuntimeError(
        "No Kaggle credentials. Set KAGGLE_API_TOKEN (KGAT_… token) or "
        "KAGGLE_USERNAME + KAGGLE_KEY in the environment.")


def _kaggle_download_file(fname: str, dest: Path, retries: int = 7) -> None:
    """Download one competition file to ``dest`` (handles redirect, 429 backoff, zip).

    The download route is ``/competitions/data/download/{comp}/{file_name}`` where a
    nested ``file_name`` must keep its slash **literally encoded as %2F** (the route
    is one path segment). ``urllib`` normalises %2F back to ``/`` and breaks the
    route, so we issue the initial request via ``http.client`` (which sends the path
    verbatim), then follow Kaggle's 302 to the signed storage URL. Kaggle rate-limits
    rapid sequential downloads (HTTP 429), so we retry with exponential backoff.
    """
    import http.client
    import io
    import time
    import urllib.error
    import urllib.request
    import zipfile

    enc = fname.replace("/", "%2F")
    path = f"/api/v1/competitions/data/download/{HMS_COMP}/{enc}"
    delay = 3.0
    data = None
    for attempt in range(retries):
        conn = http.client.HTTPSConnection("www.kaggle.com", timeout=300)
        try:
            conn.request("GET", path, headers={"Authorization": _kaggle_auth_header()})
            r = conn.getresponse()
            if r.status in (301, 302, 303, 307, 308):
                location = r.getheader("Location"); r.read()
                try:
                    with urllib.request.urlopen(location, timeout=300) as resp:
                        data = resp.read()
                    break
                except urllib.error.HTTPError as e:
                    if e.code == 429 and attempt < retries - 1:
                        time.sleep(delay); delay = min(delay * 2, 60); continue
                    raise
            elif r.status == 200:
                data = r.read(); break
            elif r.status == 429 and attempt < retries - 1:
                r.read(); time.sleep(delay); delay = min(delay * 2, 60); continue
            else:
                body = r.read(200)
                raise RuntimeError(f"Kaggle download {fname} -> HTTP {r.status}: {body[:160]!r}")
        finally:
            conn.close()
    if data is None:
        raise RuntimeError(f"Kaggle download {fname} failed after {retries} retries (rate-limited)")

    dest.parent.mkdir(parents=True, exist_ok=True)
    if data[:2] == b"PK":  # Kaggle sometimes zip-wraps single files
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            dest.write_bytes(z.read(z.namelist()[0]))
    else:
        dest.write_bytes(data)


def download_subset(hms_dir: Path, n_eegs: int) -> None:
    """Pull train.csv + a balanced subset of per-EEG parquet files via the Kaggle API.

    Downloads individual files so it fits a small disk (the full dataset is ~30 GB).
    Requires Kaggle creds in the environment (KAGGLE_API_TOKEN, or USERNAME+KEY) and
    one-time acceptance of the HMS competition rules on the website.
    """
    import pandas as pd

    hms_dir.mkdir(parents=True, exist_ok=True)
    (hms_dir / "train_eegs").mkdir(exist_ok=True)

    if not (hms_dir / "train.csv").exists():
        print("Downloading train.csv ...")
        _kaggle_download_file("train.csv", hms_dir / "train.csv")

    df = pd.read_csv(hms_dir / "train.csv")
    # one row per eeg_id, balanced across expert_consensus
    per = max(1, n_eegs // df["expert_consensus"].nunique())
    chosen = (
        df.drop_duplicates("eeg_id")
        .groupby("expert_consensus", group_keys=False)
        .apply(lambda g: g.head(per))
        .head(n_eegs)
    )
    import time
    print(f"Fetching {len(chosen)} EEG parquet files ...")
    for i, eeg_id in enumerate(chosen["eeg_id"].tolist(), 1):
        dest = hms_dir / "train_eegs" / f"{eeg_id}.parquet"
        if dest.exists():
            continue
        _kaggle_download_file(f"train_eegs/{eeg_id}.parquet", dest)
        time.sleep(0.25)  # be polite — Kaggle rate-limits rapid sequential downloads
        if i % 50 == 0:
            print(f"  ...{i}/{len(chosen)}")


def _embed(encoder, segments, device, batch=16):
    """Encode a list of (16,2000) segments -> (n,256) embeddings (encoder frozen)."""
    import torch
    embs = []
    with torch.no_grad():
        for i in range(0, len(segments), batch):
            x = torch.from_numpy(np.stack(segments[i:i + batch]).astype(np.float32)).to(device)
            embs.append(encoder(x).cpu().numpy())
    return np.concatenate(embs, axis=0) if embs else np.zeros((0, 256), np.float32)


def main() -> int:
    import torch
    import torch.nn as nn

    from apps.inference.biot import BIOTClassifier
    from apps.inference.eeg_preprocess import IIIC_CLASSES
    from eeg_hms import iter_segments, load_index, patient_split  # noqa: E402

    ap = argparse.ArgumentParser(description="Fine-tune the BIOT IIIC 6-class head on HMS.")
    ap.add_argument("--hms-dir", required=True, help="local HMS dir (train.csv + train_eegs/)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output checkpoint path")
    ap.add_argument("--encoder", default=str(DEFAULT_ENCODER), help="pretrained BIOT encoder ckpt")
    ap.add_argument("--download", type=int, default=0, metavar="N",
                    help="first download a balanced subset of N EEGs via the Kaggle API")
    ap.add_argument("--limit", type=int, default=4000, help="max labelled windows to use (0=all)")
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--lr", type=float, default=1e-3, help="head learning rate")
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--test-frac", type=float, default=0.2, help="patient-level val fraction")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--unfreeze", action="store_true",
                    help="FULL fine-tune: unfreeze the encoder and train end-to-end (needs a GPU). "
                         "This is the lever that reaches BIOT's published ~0.5 balanced-acc; the "
                         "default frozen-encoder linear probe plateaus near 0.28. With --unfreeze use "
                         "FEWER epochs (~6-12) — the encoder is already pretrained.")
    ap.add_argument("--encoder-lr", type=float, default=1e-5,
                    help="encoder LR when --unfreeze (head still uses --lr); ignored if frozen")
    ap.add_argument("--batch-size", type=int, default=32,
                    help="minibatch size for --unfreeze (raw segments flow through the encoder)")
    args = ap.parse_args()

    hms_dir = Path(args.hms_dir)
    if args.download:
        download_subset(hms_dir, args.download)

    if not (hms_dir / "train.csv").exists():
        print(f"ERROR: {hms_dir/'train.csv'} not found. Use --download or point --hms-dir "
              f"at a local HMS copy.", file=sys.stderr)
        return 2

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # ---- build the model + load the pretrained encoder ------------------
    model = BIOTClassifier(n_classes=6, n_channels=16, n_fft=200, hop_length=100)
    if not Path(args.encoder).exists():
        print(f"ERROR: encoder weights not found at {args.encoder}", file=sys.stderr)
        return 2
    model.biot.load_state_dict(torch.load(args.encoder, map_location=device))
    model.to(device)
    if args.unfreeze and device == "cpu":
        print("WARNING: --unfreeze on CPU is impractically slow. Run this on a GPU "
              "(Colab/Kaggle). Continuing anyway.", file=sys.stderr)

    # ---- load HMS windows ----------------------------------------------
    print("Indexing HMS labels ...")
    samples = load_index(hms_dir, limit=args.limit, balanced=True, seed=args.seed)
    if len(samples) < 20:
        print(f"ERROR: only {len(samples)} usable windows found (need the parquet files "
              f"present in {hms_dir/'train_eegs'}).", file=sys.stderr)
        return 1
    train_s, val_s = patient_split(samples, test_frac=args.test_frac, seed=args.seed)
    print(f"windows: {len(samples)}  (train {len(train_s)} / val {len(val_s)}, patient-split)")

    def collect(split):
        segs, ys = [], []
        for s, seg in iter_segments(hms_dir, split):
            segs.append(seg); ys.append(s["label"])
        return segs, np.asarray(ys, dtype=np.int64)

    t0 = time.time()
    print("Loading train segments ...")
    tr_segs, tr_y = collect(train_s)
    print("Loading val segments ...")
    va_segs, va_y = collect(val_s)
    print(f"  loaded {len(tr_segs)}+{len(va_segs)} windows in {time.time()-t0:.0f}s")

    # class-balanced loss (HMS is imbalanced) — shared by both modes
    counts = np.bincount(tr_y, minlength=6).astype(np.float32)
    weights = torch.tensor(counts.sum() / np.clip(counts, 1, None), dtype=torch.float32, device=device)
    lossf = nn.CrossEntropyLoss(weight=weights)

    def balanced_acc(pred, y):
        accs = []
        for c in range(6):
            m = y == c
            if m.sum():
                accs.append(float((pred[m] == c).mean()))
        return float(np.mean(accs)) if accs else 0.0

    if args.unfreeze:
        # ---- FULL fine-tune: encoder + head, end-to-end -----------------
        print(f"\nFULL FINE-TUNE: unfreezing encoder "
              f"(encoder lr {args.encoder_lr:.0e}, head lr {args.lr:.0e}, batch {args.batch_size})")
        for p in model.biot.parameters():
            if p.is_floating_point():        # skip integer buffers (e.g. channel index)
                p.requires_grad = True
        opt = torch.optim.Adam(
            [
                {"params": [p for p in model.biot.parameters() if p.requires_grad],
                 "lr": args.encoder_lr},
                {"params": model.classifier.parameters(), "lr": args.lr},
            ],
            weight_decay=args.weight_decay,
        )
        Xtr = np.stack(tr_segs).astype(np.float32)   # (N,16,2000)
        Xva = np.stack(va_segs).astype(np.float32)
        bs = args.batch_size
        best_state, best_bacc = None, -1.0
        for ep in range(args.epochs):
            model.train()
            perm = np.random.permutation(len(Xtr))
            run = 0.0
            for i in range(0, len(Xtr), bs):
                idx = perm[i:i + bs]
                xb = torch.from_numpy(Xtr[idx]).to(device)
                yb = torch.from_numpy(tr_y[idx]).to(device)
                opt.zero_grad()
                loss = lossf(model(xb), yb)
                loss.backward()
                opt.step()
                run += float(loss) * len(idx)
            model.eval()
            vp = []
            with torch.no_grad():
                for i in range(0, len(Xva), bs):
                    xb = torch.from_numpy(Xva[i:i + bs]).to(device)
                    vp.append(model(xb).argmax(1).cpu().numpy())
            vp = np.concatenate(vp)
            bacc = balanced_acc(vp, va_y)
            if bacc >= best_bacc:
                best_bacc = bacc
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            print(f"  epoch {ep+1:3d}  train loss {run/len(Xtr):.3f}  "
                  f"val balanced-acc {bacc:.3f}  (best {best_bacc:.3f})")
        if best_state is not None:
            model.load_state_dict(best_state)
    else:
        # ---- frozen-encoder linear probe (cheap, CPU-feasible) ----------
        model.biot.eval()
        for p in model.biot.parameters():
            p.requires_grad = False
        print("Encoding embeddings (frozen encoder) ...")
        tr_emb = _embed(model.biot, tr_segs, device)
        va_emb = _embed(model.biot, va_segs, device)
        head = model.classifier.to(device)
        opt = torch.optim.Adam(head.parameters(), lr=args.lr, weight_decay=args.weight_decay)
        Xtr = torch.from_numpy(tr_emb).to(device); Ytr = torch.from_numpy(tr_y).to(device)
        Xva = torch.from_numpy(va_emb).to(device)
        best_state, best_bacc = None, -1.0
        bs = 256
        for ep in range(args.epochs):
            head.train()
            perm = torch.randperm(len(Xtr))
            for i in range(0, len(Xtr), bs):
                idx = perm[i:i + bs]
                opt.zero_grad()
                loss = lossf(head(Xtr[idx]), Ytr[idx])
                loss.backward()
                opt.step()
            head.eval()
            with torch.no_grad():
                vp = head(Xva).argmax(1).cpu().numpy()
            bacc = balanced_acc(vp, va_y)
            if bacc >= best_bacc:
                best_bacc = bacc
                best_state = {k: v.detach().cpu().clone() for k, v in head.state_dict().items()}
            if (ep + 1) % 10 == 0:
                print(f"  epoch {ep+1:3d}  val balanced-acc {bacc:.3f}  (best {best_bacc:.3f})")
        if best_state is not None:
            head.load_state_dict(best_state)
        model.classifier = head

    print(f"Best val balanced-accuracy: {best_bacc:.3f}")

    # ---- save full classifier (encoder + trained head) ------------------
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), out)
    mode = "full fine-tune" if args.unfreeze else "frozen-encoder probe"
    print(f"\nSaved BIOT IIIC classifier ({mode}) -> {out}")
    print("Classes:", IIIC_CLASSES)
    print("\nReproduce:")
    print(f"  python tools/train_eeg_head.py --hms-dir {args.hms_dir} --limit {args.limit} "
          f"--epochs {args.epochs} --seed {args.seed}" + (" --unfreeze" if args.unfreeze else ""))
    print(f"  python tools/eval_eeg.py --hms-dir {args.hms_dir} --weights {out} "
          f"--limit {args.limit} --seed {args.seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
