# Colab runbook — Echo full-TEST eval & EEG full fine-tune

Two GPU jobs you can't run locally (hardware limit). Each block below = one Colab
cell. **First: Runtime → Change runtime type → GPU (T4 is enough).**

Neither job can `git clone` (no remote), so you upload the repo **once** to Google
Drive as a zip and Colab unzips it each session.

---

## 0. One-time: put the repo on Drive

On your machine, zip the project (exclude the venv — it's huge and Linux-incompatible):

```powershell
# from e:\MASTER  (PowerShell)
Compress-Archive -Path medical-platform\* -DestinationPath medical-platform.zip -Force
```

Then upload `medical-platform.zip` to the **root of your Google Drive** (`My Drive/`).
The bundled BIOT encoder (`backend/models_weights/biot/EEG-PREST-16-channels.ckpt`,
13 MB) is inside the zip, so the EEG job needs nothing else from you.

For **echo** you also need on Drive (they're git-ignored, too big for the zip):
- the two weights: `echonet_seg.pt`, `echonet_ef.pt`
- the dataset folder `EchoNet-Dynamic/` (has `FileList.csv`, `Videos/`, `VolumeTracings.csv`)

Put them anywhere on Drive and fix the paths in the echo cells.

---

# A. EEG — full fine-tune (unfreeze the encoder) → target ~0.5 balanced-acc

The frozen-encoder probe plateaus at ~0.28. `--unfreeze` trains the whole model
end-to-end, which is how BIOT reaches its published IIIC numbers. Needs a GPU.

### A1 — confirm GPU
```python
import torch; print(torch.__version__, torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NO GPU")
```

### A2 — unpack the repo from Drive
```python
from google.colab import drive; drive.mount('/content/drive')
!rm -rf /content/medical-platform
!mkdir -p /content/medical-platform
!unzip -q "/content/drive/My Drive/medical-platform.zip" -d /content/medical-platform
# if the zip nested an extra folder, flatten it:
import os, glob
root = "/content/medical-platform"
if not os.path.exists(f"{root}/tools") and os.path.exists(f"{root}/medical-platform/tools"):
    root = f"{root}/medical-platform"
print("repo root:", root)
%cd $root
```

### A3 — deps (Colab already has torch/pandas/numpy)
```python
!pip -q install linear-attention-transformer pyarrow
```

### A4 — Kaggle creds (HMS is a Kaggle competition)
You must **accept the HMS competition rules once** at
https://www.kaggle.com/competitions/hms-harmful-brain-activity-classification/rules
Then upload your `kaggle.json` (Kaggle → Settings → Create New Token):
```python
from google.colab import files
up = files.upload()                       # pick kaggle.json
import json, os
k = json.load(open('kaggle.json'))
os.environ['KAGGLE_USERNAME'] = k['username']
os.environ['KAGGLE_KEY'] = k['key']
print("kaggle creds set for", k['username'])
```

### A5 — download a balanced HMS subset + full fine-tune
`--download` pulls N EEG parquet files via the Kaggle API (rate-limited, ~10–20 min
for 2500). Bigger N + more windows = better. `--limit` caps windows so RAM stays sane.
```python
!python tools/train_eeg_head.py \
    --download 2500 --hms-dir data/hms \
    --limit 16000 --unfreeze --epochs 10 \
    --batch-size 32 --encoder-lr 1e-5 --lr 1e-3 --seed 0 \
    --out backend/models_weights/biot/biot_iiic.pt
```
Watch the per-epoch `val balanced-acc`. If it's still climbing at epoch 10, bump
`--epochs`. If you hit an out-of-memory error, drop `--batch-size` to 16 or `--limit`
to 10000.

### A6 — evaluate on the patient-disjoint held-out split
Use the **same** `--limit`/`--seed` so the split matches training (no leakage).
```python
!python tools/eval_eeg.py \
    --hms-dir data/hms \
    --weights backend/models_weights/biot/biot_iiic.pt \
    --limit 16000 --seed 0
```
**Copy this whole printout back to me** — balanced-acc, κ, macro-F1, KL, the
per-class table and the 6×6 confusion matrix.

### A7 — save the trained head to Drive (Colab is wiped on disconnect)
```python
!cp backend/models_weights/biot/biot_iiic.pt "/content/drive/My Drive/biot_iiic.pt"
print("saved biot_iiic.pt to Drive")
```

---

# B. Echo — full TEST split (the 1,277-video number)

EchoNet already matches the paper on subsets; this just removes `--limit` to get the
report-grade figure. GPU helps the models; video decoding is CPU-bound so it's still
~minutes.

### B1 — unpack repo (skip if you just ran section A in the same session)
```python
from google.colab import drive; drive.mount('/content/drive')
!rm -rf /content/medical-platform && mkdir -p /content/medical-platform
!unzip -q "/content/drive/My Drive/medical-platform.zip" -d /content/medical-platform
import os
root = "/content/medical-platform"
if not os.path.exists(f"{root}/tools") and os.path.exists(f"{root}/medical-platform/tools"):
    root = f"{root}/medical-platform"
%cd $root
!pip -q install opencv-python-headless
```

### B2 — point the loader at the weights on Drive, run full TEST
Fix the two weight paths and the dataset root to wherever you put them on Drive.
```python
import os
os.environ['ECHONET_SEG_WEIGHTS'] = "/content/drive/My Drive/echonet_seg.pt"
os.environ['ECHONET_EF_WEIGHTS']  = "/content/drive/My Drive/echonet_ef.pt"
DATA = "/content/drive/My Drive/EchoNet-Dynamic"     # has FileList.csv + Videos/ + VolumeTracings.csv

!python tools/eval_echo.py "$DATA" --split TEST
```
This prints EF MAE / RMSE / R² / Pearson r and LV-segmentation Dice over the full
TEST split. **Copy the printout back to me.**

> Faster sanity check first: add `--limit 100` to B2 — if MAE ≈ 3–4 % and Dice ≈ 0.9,
> the setup is right; then rerun without `--limit` for the headline number.

---

## What to send back
- **EEG:** the full `eval_eeg.py` output from A6 (and the best val balanced-acc line from A5).
- **Echo:** the full `eval_echo.py` output from B2.

I'll fold the new numbers into `VALIDATION.md` and tell you whether the EEG fine-tune
actually closed the gap to BIOT's ~0.5.
