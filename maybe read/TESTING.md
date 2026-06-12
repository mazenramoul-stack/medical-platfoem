# Testing & Local Setup Guide

This document is the single reference for getting the **Multimodal Medical
AI Platform** running end-to-end on a developer machine and walking through
a full clinical workflow.

---

## A. Prerequisites

| Requirement | Why |
|---|---|
| **Python 3.10 or 3.11** | Backend runtime; `djongo 1.3.6` does not support 3.12+. |
| **Node.js 18+** | Frontend build / dev server (Vite). |
| **MongoDB Community Edition** | Database backend (via `djongo`). |
| **~8 GB RAM** | ViT + ecglib + matplotlib all in memory during inference. |
| **~5 GB free disk** | Model weights (~700 MB MRI/ECG + ~13 MB BIOT encoder), node_modules (~500 MB), media files. Optional EEG training data (Kaggle HMS subset) adds ~1–2 GB. |
| Stable internet (first run only) | Pre-trained models download from PyTorch Hub, HuggingFace, and ecglib. EEG training additionally needs Kaggle (token + HMS rules). |

---

## B. Starting the System

### 1. MongoDB

Run a local Mongo daemon listening on the default port `27017`.

```bash
# Linux / macOS
mongod --dbpath /your/db/path

# Windows: MongoDB ships as a Windows Service.
# Start via Services.msc -> "MongoDB Server" -> Start
# or from an Admin PowerShell:
#   net start MongoDB
```

Verify Mongo is reachable:
```bash
mongosh "mongodb://localhost:27017"  # or `mongo` on older installs
```

### 2. Backend

```bash
cd backend

# Activate the virtualenv created in Step 2
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Windows (cmd):
venv\Scripts\activate.bat
# Linux / macOS:
source venv/bin/activate

# First-time only: confirm migrations applied
python manage.py migrate

# Start the dev server
python manage.py runserver        # → http://localhost:8000
```

### 3. Frontend

```bash
cd frontend
npm run dev                       # → http://localhost:3000
```

> **Port note.** The backend's CORS rule in [backend/.env](backend/.env) is
> pinned to `http://localhost:3000`. Vite is configured to bind port 3000 too
> (`strictPort: true`). If another process is holding port 3000 (e.g. an
> unrelated CRA project), Vite will refuse to start — free the port first.
> The user-spec template references `5173` (Vite's default), but this project
> ships configured for `3000` to match the CORS policy.

---

## C. First-Time Model Setup

The first MRI or ECG inference triggers a one-time download of pre-trained
weights. Be patient — subsequent calls hit local cache and are 10–20× faster.

| Stage | Source | Approx. size | Cache location |
|---|---|---|---|
| U-Net (FLAIR MRI segmentation) | PyTorch Hub `mateuszbuda/brain-segmentation-pytorch` | ~30 MB | `~/.cache/torch/hub/` |
| ViT (4-class tumor classifier) | HuggingFace `Devarshi/Brain_Tumor_Classification` | ~350 MB | `~/.cache/huggingface/` |
| DenseNet-1D-121 × 7 (ECG pathology) | ecglib (ISPRAS) | ~150 MB total | `~/.cache/torch/hub/checkpoints/` |
| **Total first-run download** | | **~700 MB** | |

Pre-warm the cache *before* running the test scenario:

```bash
cd backend
python apps/inference/test_pipelines.py
```

This runs the end-to-end inference smoke test from Step 6 and downloads
everything needed.

> **Echo & EEG weights are NOT auto-downloaded** (unlike MRI/ECG). They are
> deliberately left out of `warmup()` and load from disk on demand:
> - **Echo (EchoNet-Dynamic):** place `echonet_seg.pt` + `echonet_ef.pt` in
>   `backend/models_weights/echonet/` (or set `ECHONET_SEG_WEIGHTS` /
>   `ECHONET_EF_WEIGHTS`).
> - **EEG (BIOT/IIIC):** the encoder ships in `backend/models_weights/biot/`, but
>   the 6-class IIIC head is **not released by BIOT** — fine-tune it on Kaggle HMS:
>   `python tools/train_eeg_head.py --download 400 --hms-dir data/hms` (needs a
>   Kaggle token + accepting the HMS competition rules; see
>   [VALIDATION.md](VALIDATION.md) §5).
>
> Both endpoints raise a clear `FileNotFoundError` until their weights are present —
> that is expected, not a bug.

---

## D. Full Test Scenario (manual walk-through)

This is the canonical 11-step clinical workflow used to validate every
feature of the platform.

> **Sample data.** Generate sample MRI + ECG (+ EEG) files first:
> ```bash
> python tools/download_sample_mri.py       # → samples/mri/tumor_sample_*.png
> python tools/generate_sample_ecg.py       # → samples/ecg/{normal,tachy,brady,afib}.csv
> python tools/generate_sample_eeg.py       # → data/samples/sample_eeg.edf (synthetic)
> ```

1. Open <http://localhost:3000>. You should land on `/login`.
2. Click **Register** and create an account:
   - Email: `doctor@test.com`
   - Password: `TestPass123!`
   - Full name: `Dr. Test`
   - Role: `Doctor`
3. **Log in** with that account.
4. Sidebar → **Patients** → **+ New patient**. Fill in:
   - Full name: `John Doe`
   - Age: `45`
   - Gender: `Male`
   - Medical history: anything you like.
5. Open John Doe's detail page → click **+ New MRI analysis** → drop in
   `samples/mri/tumor_sample_1.png`. Click **Analyze MRI**.
6. Wait 30–60 s for the first inference (model load + segmentation +
   classification). The progress UI advances upload → inference → done.
7. The MRI result page opens. Verify:
   - **TumorBadge** is set (e.g. `glioma`, `no_tumor`).
   - **Confidence bar** is populated.
   - **Overlay / Mask / Original** tabs all show images.
   - **Inference report** is rendered as a monospaced block.
8. Back to John Doe → **+ New ECG analysis** → drop in
   `samples/ecg/normal.csv`. Click **Analyze ECG**.
9. The ECG result page opens. Verify:
   - 12-lead plot renders.
   - **Primary diagnosis** card (color-coded green if normal).
   - **HRV metrics**: RMSSD / SDNN / pNN50 with "in range" badges.
   - **Pathology probability table** sorted descending, detected rows red.
10. Back to John Doe → **+ Generate report**. Pick the MRI + ECG just
    uploaded → **Generate report**. PDF auto-downloads.
11. Open the downloaded PDF and verify:
    - Header (Multimodal Medical AI Platform / Constantine 2).
    - Patient information block.
    - Brain MRI Analysis section with embedded overlay.
    - 12-Lead ECG Analysis section with HRV + pathology table + plot.
    - Combined Clinical Interpretation paragraph.
    - Disclaimer footer.

If all 11 steps pass, the MRI+ECG core is working end-to-end.

### Optional: Echo & EEG (require their weights — see section C)

12. **Echo** — patient detail → **+ New Echo analysis** → drop an echo video
    (`.avi`/`.mp4`). The result page shows the ejection fraction, EF category, and the
    LV-segmentation overlay. (Needs the EchoNet checkpoints in
    `backend/models_weights/echonet/`.)
13. **EEG** — patient detail → **+ New EEG analysis** → drop a `.edf` (e.g.
    `data/samples/sample_eeg.edf`). The result page shows the dominant IIIC pattern,
    the 6-class distribution + timeline, and a harmful-activity flag. (Needs a
    fine-tuned `biot_iiic.pt`; the synthetic sample EDF is for plumbing only — its
    prediction is not clinically meaningful.)
14. **Combined report** now also offers Echo and EEG selectors; any subset of the
    four modalities renders into the PDF.

> Honesty note: EEG is *functional* harmful-brain-activity screening (the complement
> to the structural MRI tumour analysis), not a tumour detector, and its accuracy is
> modest (balanced-acc ~0.28). See [VALIDATION.md](VALIDATION.md) §5.

---

## E. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Server unreachable` toast in UI | Backend not running, or wrong CORS origin. | `python manage.py runserver` and confirm port 8000. Check `CORS_ALLOWED_ORIGINS` in `backend/.env`. |
| `MongoServerError: connection refused` on migrate | `mongod` is not running. | Start the MongoDB service (`net start MongoDB` on Windows). |
| 403 / OPTIONS errors in browser console | CORS misconfigured. | Verify `corsheaders` is in `INSTALLED_APPS` and `CorsMiddleware` is first in `MIDDLEWARE`. |
| `Cannot install … djongo 1.3.6` (sqlparse conflict) | Django 4.x is installed; djongo only supports 3.x. | Keep `Django==3.2.25` in `requirements.txt` — this is documented in Step 2. |
| Inference takes minutes / hangs | First run is downloading 700 MB of weights, or out of RAM. | Watch the terminal for tqdm download bars. Close other apps if RAM-constrained. |
| `ImportError: cannot import name 'create_model' from 'ecglib.models'` | Wrong ecglib version installed. | `pip install ecglib==1.0.1` (exact pin). |
| MRI segmentation marks the whole image as tumor | This was a **double-sigmoid bug**: the `mateuszbuda` U-Net already applies sigmoid inside `forward()`, and the pipeline applied it again, saturating the mask. | **Fixed** — the pipeline uses the U-Net output directly (no second sigmoid); Dice ~0.85 on LGG (`tools/eval_mri_segmentation.py`). The saturation guard remains as a harmless safety net. |
| Vite refuses to bind port 3000 | Another process is holding the port. | `Get-NetTCPConnection -LocalPort 3000` on Windows / `lsof -i :3000` on Unix. Stop the conflicting process. |
| `ecglib` warnings for IRBBB / CRBBB at startup | The build spec asked for IRBBB/CRBBB, which ecglib 1.0.1 doesn't have; the loader already requests `RBBB`/`LBBB` instead. | Harmless — all **7/7** models load (`[AFIB, 1AVB, STACH, SBRAD, RBBB, LBBB, PVC]`). The substitution is already in `apps/inference/model_loader.py`; no action needed. |
| PDF report shows `?` glyphs | Helvetica is missing the box-drawing characters. | Already handled in [pdf_generator.py](backend/apps/reports/pdf_generator.py) via `_ascii()` substitution. |
| Echo upload fails: `EchoNet … weights not found` | EchoNet checkpoints are not bundled. | Place `echonet_seg.pt` + `echonet_ef.pt` in `backend/models_weights/echonet/` (or set the `ECHONET_*_WEIGHTS` env vars). Expected on a fresh checkout. |
| EEG upload fails: `BIOT IIIC … head not found` | BIOT releases only an encoder; the IIIC head must be fine-tuned. | `python tools/train_eeg_head.py --download 400 --hms-dir data/hms` (Kaggle token + HMS rules accepted). See VALIDATION.md §5. Expected on a fresh checkout. |
| EEG upload fails: `missing referential 10-20 electrodes` | The `.edf` montage isn't a standard referential 10-20 set. | The pipeline derives a 16-ch bipolar montage from referential electrodes; the error lists which are missing. Use a standard scalp EEG. |
| Kaggle download fails: `HTTP 429 TooManyRequests` | Kaggle rate-limits rapid sequential downloads. | The downloader already retries with backoff; just re-run — cached files are skipped. Or train on what's already downloaded (drop `--download`). |

---

## F. Running the automated test suites

### Sample-data generators

```bash
python tools/download_sample_mri.py
python tools/generate_sample_ecg.py
python tools/generate_sample_eeg.py
```

The MRI/ECG scripts write to `samples/`; the EEG script writes a synthetic `.edf`
to `data/samples/`. Re-running is idempotent (the MRI script skips
already-downloaded files; the ECG/EEG scripts overwrite).

### EEG model evaluation (after fine-tuning a head)

```bash
python tools/eval_eeg.py --hms-dir data/hms --weights backend/models_weights/biot/biot_iiic.pt
```

Prints balanced accuracy, Cohen's κ, macro/weighted F1, per-class P/R/F1, the 6×6
confusion matrix, and KL divergence on a patient-disjoint held-out split.

### Django test suite

```bash
cd backend
python manage.py test tests           # → tests under backend/tests/
```

> ⚠ With `djongo` 1.3.6 + Django 3.2, Django's test runner sometimes has
> trouble with `CREATE / DROP TEST DATABASE` because Mongo doesn't have
> SQL-style DDL. The inference-level tests use `SimpleTestCase` (no DB)
> and always run; the API tests use `APITestCase` (test DB) and may
> require manual DB management. If the test runner refuses to create the
> test DB, run the inference-level tests in isolation:
>
> ```bash
> python manage.py test tests.test_pipelines.MRIPipelineTest tests.test_pipelines.ECGPipelineTest
> ```

### Seed the dev database

```bash
cd backend
python tests/seed_database.py
```

Creates `doctor@test.com / TestPass123!` plus 5 sample patients. Idempotent —
re-running is safe (the seed checks for existing records before inserting).
