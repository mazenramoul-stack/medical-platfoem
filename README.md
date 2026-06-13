# Multimodal Medical AI Platform for Cardiology & Oncology

> **Master's PFE Project (2025 / 2026)**
> Université Abdelhamid Mehri – Constantine 2
> Faculté des Nouvelles Technologies de l'Information et de la Communication
> Département : Informatique Fondamentale et ses Applications

A web-based clinical decision support platform that integrates pre-trained deep
learning models for **brain MRI tumor analysis**, **12-lead ECG arrhythmia
detection**, **echocardiogram analysis** (ejection fraction + LV segmentation),
and **EEG harmful-brain-activity screening** into a single workflow, producing
combined PDF reports for clinicians.

---

## Authors

- **Student**: Mazen Ramoul · `mazen.ramoul@univ-constantine2.dz`
- **Supervisor**: Prof. DERDOUR Makhlouf
- **Co-supervisor**: Prof. TALBI Hichem

---

## Abstract

Non-communicable diseases — cardiovascular pathologies and cancers in particular
— remain the leading cause of mortality worldwide. Modern clinical practice
generates heterogeneous patient data (medical imaging, physiological signals,
electronic health records) which is rarely integrated at the point of decision.
This project addresses that gap by designing and implementing a **modular,
multimodal decision-support platform** that consumes MRI images, 12-lead ECG
recordings, echocardiogram videos, and EEG recordings and produces unified,
explainable clinical reports.

The platform composes open, peer-reviewed deep-learning components: a
**U-Net** trained on TCGA-LGG for tumor segmentation (Buda et al., 2019), a
**Swin Transformer (Swin-T)** for four-class brain tumor classification (Liu
et al., 2021), a **DenseNet-1D-121 ensemble** trained on 500 000+ ECG
records via the `ecglib` toolkit (Avetisyan et al., 2023), the **EchoNet-Dynamic**
models for echocardiographic ejection-fraction regression and LV segmentation
(Ouyang et al., 2020), and **BIOT**, a biosignal transformer for EEG
harmful-brain-activity (IIIC) screening (Yang et al., 2023). Classical signal
processing for heart-rate variability is delegated to the validated **NeuroKit2**
library (Makowski et al., 2021). Results from all modalities are aggregated
into a single PDF that includes a *combined clinical interpretation* — a
deliberate design choice motivated by the neuro-cardiac coupling literature,
in which brain pathology can manifest as autonomic dysregulation visible on
the ECG.

> Provenance note. Two components are **not** turnkey pretrained models: EchoNet
> weights are downloaded separately (not bundled), and BIOT ships only a pretrained
> *encoder* — its IIIC classification head is fine-tuned in-repo on the public
> Kaggle HMS dataset (`tools/train_eeg_head.py`). Both fail with a clear error until
> their weights are present. See [VALIDATION.md](maybe%20read/VALIDATION.md) for honest scope.

The technical contribution is not the models themselves but the **architecture
that integrates them**: a Django + MongoDB backend with synchronous inference
behind a typed REST API, a React + TailwindCSS frontend with strict
doctor-scoped data isolation, and an end-to-end testing harness. The platform
is intentionally modality-agnostic; adding a new domain (CT, EEG, genomics)
requires only a new pipeline module and view set without touching the core.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                      Browser (clinician)                           │
└──────────────────┬─────────────────────────────────────────────────┘
                   │ HTTPS  (JWT bearer)
┌──────────────────▼─────────────────────────────────────────────────┐
│   React 19 + Vite + TailwindCSS                                    │
│   ├─ Redux Toolkit (auth, patients, notifications)                 │
│   ├─ Axios w/ interceptors  (401 → /login)                         │
│   └─ react-router-dom 6                                            │
└──────────────────┬─────────────────────────────────────────────────┘
                   │ REST /api/*
┌──────────────────▼─────────────────────────────────────────────────┐
│   Django 3.2 + Django REST Framework + SimpleJWT                   │
│   ├─ apps/authentication  →  custom User model, email login        │
│   ├─ apps/patients        →  doctor-scoped CRUD, /history/         │
│   ├─ apps/mri             →  upload + sync inference + result urls │
│   ├─ apps/ecg             →  upload + sync inference + plot url    │
│   ├─ apps/echo            →  upload + sync inference (EF + LV seg) │
│   ├─ apps/eeg             →  upload (.edf) + sync BIOT/IIIC infer  │
│   ├─ apps/reports         →  ReportLab PDF, combined interpretation│
│   └─ apps/inference       ┐                                        │
└──────────────────┬────────┘                                        │
                   │  ┌──────────────────────────────────────────────┤
                   │  │   Inference Engine (lazy singleton)          │
                   │  │   ├─ MRI pipeline                            │
                   │  │   │   • U-Net  (torch.hub, ~30 MB)           │
                   │  │   │   • Swin-T (HuggingFace, ~110 MB)        │
                   │  │   ├─ ECG pipeline                            │
                   │  │   │   • DenseNet-1D ×7 (ecglib, ~150 MB)     │
                   │  │   │   • NeuroKit2 HRV (CPU, classical)       │
                   │  │   ├─ Echo pipeline (EchoNet-Dynamic)         │
                   │  │   │   • DeepLabV3-R50 + R(2+1)D-18 (on disk) │
                   │  │   └─ EEG pipeline (BIOT, vendored)           │
                   │  │       • encoder (bundled) + IIIC head (HMS)  │
                   │  └──────────────────────────────────────────────┘
┌──────────────────▼─────────────────────────────────────────────────┐
│   MongoDB (via djongo)                                             │
│   medical_platform DB: users·patients·mri·ecg·echo·eeg·reports     │
└────────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Backend framework | Django + DRF | 3.2.25 / 3.14.0 |
| Authentication | SimpleJWT | 5.3.1 |
| Database | MongoDB (via djongo) | 7.x / 1.3.6 |
| Inference framework | PyTorch + transformers | 2.2.0 / 4.38.0 |
| MRI models | torch.hub + 🤗 Hub | — |
| ECG models | ecglib (ISPRAS) | 1.0.1 |
| Echo models | EchoNet-Dynamic (torchvision) | — |
| EEG model | BIOT (vendored) + linear-attention-transformer | 0.19.1 |
| EEG / signal I/O | MNE, edfio, pyarrow | 1.12 / 0.4 / 24.0 |
| Signal processing | NeuroKit2, SciPy | 0.2.7 / 1.11.4 |
| PDF generation | ReportLab | 4.0.9 |
| Frontend framework | React + Vite | 19 / 8 |
| Styling | TailwindCSS | 3.4 |
| State | Redux Toolkit + react-redux | 2 / 9 |
| HTTP | Axios | 1.16 |
| Routing | react-router-dom | 6 |
| Icons | lucide-react | — |

---

## Deep Learning Models Used

### MRI Analysis

| Model | Architecture | Source | Pre-trained On | Parameters |
|---|---|---|---|---|
| **U-Net** | CNN encoder-decoder | `mateuszbuda/brain-segmentation-pytorch` (torch.hub) | TCGA-LGG (110 patients, FLAIR MRI) | ~7.7 M |
| **Swin Transformer (Swin-T)** | Swin Transformer (base: `microsoft/swin-tiny-patch4-window7-224`) | `Devarshi/Brain_Tumor_Classification` (HuggingFace) | Brain Tumor MRI Dataset (~7 000 images, 4 classes) | ~28 M |

Classes: `glioma`, `meningioma`, `no_tumor`, `pituitary`.

### ECG Analysis

| Model | Architecture | Source | Pre-trained On | Parameters |
|---|---|---|---|---|
| **DenseNet-1D-121** (×7) | 1D Deep CNN | `ecglib` (ISPRAS) | 500 000+ 12-lead ECG records | ~8 M each |
| **NeuroKit2** | Classical DSP | `neurokit2` Python lib | — (rule-based, validated) | — |

Pathologies modelled (all 7 load): `AFIB`, `1AVB`, `STACH`, `SBRAD`, `RBBB`,
`LBBB`, `PVC`.

### Echocardiography Analysis

| Model | Architecture | Source | Pre-trained On | Parameters |
|---|---|---|---|---|
| **DeepLabV3-ResNet50** | 2D CNN segmentation | EchoNet-Dynamic (Stanford) | EchoNet-Dynamic echo videos | ~40 M |
| **R(2+1)D-18** | 3D spatiotemporal CNN | EchoNet-Dynamic (Stanford) | EchoNet-Dynamic echo videos | ~31 M |

Outputs: left-ventricle segmentation + ejection-fraction (EF) regression with a
clinical category (reduced / mildly reduced / normal). **Weights are not bundled** —
download the EchoNet checkpoints into `backend/models_weights/echonet/`.

### EEG Analysis

| Model | Architecture | Source | Pre-trained On | Parameters |
|---|---|---|---|---|
| **BIOT** | Linear-attention Transformer over STFT tokens | `ycq091044/BIOT` (vendored) | encoder: 5M MGH resting EEG; IIIC head: Kaggle HMS | ~3 M |

Classes (IIIC 6-class harmful-brain-activity): `SZ`, `LPD`, `GPD`, `LRDA`, `GRDA`,
`Other`. **The encoder is pretrained and bundled; the 6-class IIIC head is fine-tuned
in-repo** (`tools/train_eeg_head.py`) — BIOT does not release one. This is *functional*
screening (the complement to the structural MRI tumour analysis), **not** a tumour
detector.

---

## Validation & Results

All models were validated on held-out public datasets. Full tables, per-class
metrics, confusion matrices and reproduce commands are in
[VALIDATION.md](maybe%20read/VALIDATION.md); the evaluation harnesses are in `tools/`.

| Model | Dataset (held-out) | Headline result |
|---|---|---|
| **ECG** (7 pathologies, multi-label; 1AVB/RBBB/PVC fine-tuned June 2026) | PTB-XL fold 10 (2,198 records) | mean ROC-AUC **0.980**, macro balanced accuracy **0.887**, macro F1 **0.727** (stock baseline: 0.978 / 0.884 / 0.711 — see VALIDATION.md §1) |
| **MRI classification** (Swin, 4-class, fine-tuned June 2026) | Kaggle Brain-Tumor `Testing/` (1,600 images) | accuracy **95.4 %**, macro F1 **0.954** (stock hub model scored 80.4 % — see VALIDATION.md §2) |
| **MRI segmentation** (U-Net) | LGG MRI Segmentation (3,929 slices) | **Dice 0.85** (tumour slices), IoU 0.78 |
| **Echo** (EF regression + LV seg) | EchoNet-Dynamic TEST (400 videos) | EF **MAE 4.01 %**, R² 0.83; LV **Dice 0.90** (an earlier 40-video subset gave MAE 3.19 % — see VALIDATION.md §4) |
| **EEG** (BIOT/IIIC, 6-class) | Kaggle HMS, patient-disjoint (1,883 windows) | balanced acc **0.278**, κ **0.147**, macro F1 **0.265** |

> The EEG result is honest-but-modest by design: unlike the other modalities (turnkey
> pretrained models), the BIOT IIIC head was trained in-repo on a 1,451-EEG subset
> with the encoder **frozen** on CPU — above chance, below BIOT's full-data ~0.5. A
> GPU full-fine-tune is the documented path to close that gap. See VALIDATION.md §5.

**Safety-first operating points (June 2026) — minimizing false negatives.** For a
screening tool, missing a sick patient (false negative) is far costlier than an
extra review. Because the *decision threshold / decision rule* — not the model
weights — controls this, every model was re-calibrated for high recall **with no
GPU retraining**:

| Model | "Don't-miss" recall | False negatives | Precision cost |
|---|---|---|---|
| ECG (7 pathologies) | all ≥0.95, macro **0.98** | 13 / 2,198 records | macro 0.69 → 0.35 |
| MRI (tumour vs healthy) | **0.998** (1.000 in zero-miss mode) | 2 / 1,200 (0 in zero-miss) | 2–17 / 400 healthy flagged |
| EEG (abnormal screen) | seizures routed **0.966**; general abnormal **0.931** | 128 / 1,850 windows | specificity ≈0 |
| Echo (reduced EF) | **0.95** (flag EF<55 %) | 4 / 83 reduced | precision 0.88 → 0.68 |

ECG ships both a `recall` (default) and `f1` operating point (`ECG_THRESHOLD_MODE`).
ECG/MRI/Echo all clear ≥0.95 with no GPU. **EEG is the honest exception:** its
seizure-routing (0.966) clears the bar but the general abnormal screen (0.931)
falls just short — the frozen-head model can't rule out benign activity. Reaching
≥0.95 there needs the GPU full fine-tune (the one place GPU is warranted); 6-way
*type* recall stays unreachable (inter-rater-ambiguous). Full tables, per-class
numbers, and reproduce commands: VALIDATION.md §0.

Two implementation bugs were diagnosed and fixed during validation:

- **ECG decision threshold** — the flat `prob > 0.5` cut-off over-flagged badly.
  Tuning a per-pathology threshold on the validation fold (no test leakage) raised
  macro F1 from **0.51 → 0.71** with no retraining (re-tuned June 2026 for the
  fine-tuned ensemble: **0.54 → 0.73**).
- **MRI segmentation double-sigmoid** — the U-Net already applies sigmoid in its
  `forward()`; the pipeline applied it again, saturating every mask. Removing the
  redundant sigmoid took Dice from **0.02 → 0.85**.

> Leakage check (done): `ecglib`'s unpublished corpus *may* include PTB-XL, so the
> fold-10 AUC could in principle be optimistic. Tested on the PTB-XL-independent
> Chapman-Shaoxing-Ningbo set (`tools/eval_ecg_external.py`): **macro AUC 0.981** ≈ the
> PTB-XL value → **no meaningful leakage** (indicative n=150; rerun `--stream 1500` for
> report-grade rare-pathology numbers). The three models are validated independently —
> the platform does **not** model a data-driven neuro-cardiac correlation (future work).

---

## Features

- **Patient management** — doctor-scoped CRUD with history view
- **MRI tumor detection** — pixel-level segmentation overlay + 4-class type
- **12-lead ECG arrhythmia screening** — 7 binary classifiers
- **HRV time-domain metrics** — RMSSD, SDNN, pNN50 with reference ranges
- **Echocardiography** — ejection-fraction estimate + LV segmentation (EchoNet)
- **EEG harmful-brain-activity screening** — BIOT/IIIC 6-class over 10 s segments
- **Combined clinical PDF reports** — rule-based combined interpretation (template logic, not a learned correlation)
- **JWT authentication** — email-based, 1-hour access / 7-day refresh
- **Multi-doctor isolation** — patients are strictly visible only to their owner
- **Modular** — new modalities (CT, EEG, genomics) plug in without touching auth
- **Lazy model loading** — first inference downloads weights; subsequent calls reuse
- **CPU-compatible** — GPU auto-detected if available
- **Robust failure modes** — pipelines return structured errors, never crash the API

---

## Installation

### Prerequisites

- Python 3.10 or 3.11 — required by torch 2.2 + djongo 1.3
- Node.js ≥ 18
- MongoDB Community 6+ running on `localhost:27017`
- ~8 GB RAM (Swin + ecglib models hold ~3 GB resident)
- ~3 GB free disk for cached model weights

### Backend

```bash
cd backend
python -m venv venv
# Windows
.\venv\Scripts\Activate.ps1
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt

# Copy the env template and edit if needed
cp .env.example .env        # (Windows: copy .env.example .env)

python manage.py migrate
python manage.py runserver   # http://localhost:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev                  # http://localhost:3000
```

### One-click launcher (Windows)

```
start.bat        # opens backend + frontend in separate windows + browser
stop.bat         # kills both
```

---

## Usage

1. Register a doctor account (or run `python backend/tests/seed_database.py` for
   the demo user: `doctor@test.com` / `TestPass123!`).
2. Create a patient from the *Patients* page.
3. From a patient's detail page, click **+ New MRI / ECG / Echo / EEG analysis**.
   Drag-and-drop the file. Inference runs synchronously (~5–60 s depending on cache
   state; EEG over many segments can take longer on CPU).
4. Result pages render the segmentation overlay, HRV metrics, per-pathology
   probability table, EF + LV segmentation, EEG IIIC class distribution/timeline,
   and the raw inference report.
5. **+ Generate report** combines any completed analyses (MRI / ECG / Echo / EEG,
   or any subset) into a multi-section PDF and triggers an auto-download.

> Note: Echo and EEG need their weights present first — EchoNet checkpoints in
> `backend/models_weights/echonet/`, and a fine-tuned BIOT IIIC head in
> `backend/models_weights/biot/biot_iiic.pt` (`python tools/train_eeg_head.py`).
> Both endpoints return a clear error until then.

Sample data:

```bash
python tools/download_sample_mri.py
python tools/generate_sample_ecg.py
python tools/generate_sample_eeg.py      # synthetic .edf for EEG smoke-testing
```

---

## Project Structure

```
medical-platform/
├── backend/
│   ├── apps/
│   │   ├── authentication/   custom User (email login) + JWT views
│   │   ├── patients/         doctor-scoped CRUD, /history/ endpoint
│   │   ├── mri/              upload + inference orchestration
│   │   ├── ecg/              upload + inference orchestration
│   │   ├── echo/             upload + EchoNet inference (EF + LV seg)
│   │   ├── eeg/              upload (.edf) + BIOT/IIIC inference
│   │   ├── reports/          PDF generation via ReportLab
│   │   └── inference/        model loader, MRI/ECG/Echo/EEG pipelines, biot/ (vendored), utils
│   ├── core/                 Django settings, root URLConf
│   ├── media/                uploads + generated artifacts
│   ├── tests/                test_pipelines.py + seed_database.py
│   ├── manage.py
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── modules/          Auth, Dashboard, Patients, MRI, ECG, Echo, EEG, Reports
│       ├── components/       Layout (Sidebar/Navbar) + UI primitives
│       ├── services/         axios instance + per-resource service modules
│       ├── store/            Redux slices (auth, patients, notifications)
│       ├── hooks/            useAuth, usePatients, useApi
│       └── utils/            formatters, validators, constants
├── samples/                  generated test inputs (gitignored)
├── tools/                    sample generators (mri/ecg/eeg) + eval_* harnesses + train_eeg_head.py
├── README.md                 ← this file
├── maybe read/               non-runtime docs: TESTING, VALIDATION, METHODOLOGY,
│                             CONTRIBUTING, CHANGELOG, PFE_REPORT_OUTLINE
├── start.bat / stop.bat      Windows one-click launchers
└── docker-compose.yml        optional containerised demo
```

---

## API Endpoints

All endpoints are JSON unless noted. Authenticated requests carry
`Authorization: Bearer <access_token>`.

### Authentication — `/api/auth/`

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/register/` | — | `{email, password, full_name, role}` | `201` `{user, access, refresh}` |
| POST | `/login/` | — | `{email, password}` | `200` `{access, refresh, user}` |
| POST | `/refresh/` | — | `{refresh}` | `200` `{access}` |
| GET  | `/me/` | ✓ | — | `200` `{id, email, full_name, role, …}` |

### Patients — `/api/patients/`

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET    | `/` | ✓ | List **only the requesting doctor's** patients |
| POST   | `/` | ✓ | `doctor` is auto-set from the JWT |
| GET    | `/{id}/` | ✓ | 404 if not yours |
| PATCH  | `/{id}/` | ✓ | 404 if not yours |
| DELETE | `/{id}/` | ✓ | Cascades the patient's MRI/ECG/Echo/EEG; reports survive via null FK |
| GET    | `/{id}/history/` | ✓ | `{patient_id, patient_name, mri_analyses[], ecg_analyses[], echo_analyses[], eeg_analyses[]}` |

### MRI — `/api/mri/`

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST   | `/upload/` | ✓ | multipart `{patient_id, file}`; runs synchronous inference |
| GET    | `/` (`?patient_id=X` optional) | ✓ | doctor-scoped, ordered by `-created_at` |
| GET    | `/{id}/` | ✓ | full record with `file_url`, `mask_url`, `overlay_url`, `analysis_url` |
| DELETE | `/{id}/` | ✓ | removes upload + all 3 result images |

### ECG — `/api/ecg/`

Same shape as MRI. Result fields include `plot_url`, `result_hrv_metrics` (JSON),
`result_pathology_probabilities` (JSON).

### Echo — `/api/echo/`

Same shape as MRI. Result fields include `result_ef`, `result_ef_category`,
`result_ed_area`, `result_es_area`, `overlay_url`. Accepts echo video uploads.

### EEG — `/api/eeg/`

Same shape as MRI. Accepts `.edf` uploads (max 200 MB). Result fields include
`result_dominant_pattern`, `result_harmful` (bool), `result_class_distribution`
(JSON, 6-class proportions), `plot_url`. Fails with a clear error if the fine-tuned
IIIC head is absent (see VALIDATION.md §5).

### Reports — `/api/reports/`

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST   | `/generate/` | ✓ | `{patient_id, mri_analysis_id?, ecg_analysis_id?, echo_analysis_id?, eeg_analysis_id?}`; ≥1 analysis required, must be `completed` |
| GET    | `/` (`?patient_id=X` optional) | ✓ | |
| GET    | `/{id}/` | ✓ | |
| GET    | `/{id}/download/` | ✓ | streams `application/pdf` with `Content-Disposition: attachment` |
| DELETE | `/{id}/` | ✓ | removes the PDF from disk |

---

## Known Limitations

Honest disclosures for the thesis defence:

1. **MRI segmentation and classification use different datasets.** Segmentation is
   validated on LGG (which ships tumour masks; Dice 0.85); the 4-class Swin is
   validated on the Kaggle Brain-Tumor set (no masks; 95.4 % accuracy after the
   June 2026 fine-tune). These are
   different MRI modalities, so a single uploaded image is **not** validated
   end-to-end through both tasks. (Segmentation itself was previously made to look
   non-functional by a double-sigmoid bug, now fixed — see *Validation & Results*.)
2. **Model disagreement (MRI).** Because the U-Net and the Swin are trained on
   different datasets, they can disagree on the same input. The report displays both
   without resolution; a clinician-facing release would add a confidence-based
   "uncertain" verdict.
3. **ECG decision threshold needs calibration.** All 7 `ecglib` pathologies load,
   but a flat 0.5 threshold over-flags. The pipeline now uses per-pathology
   thresholds tuned on PTB-XL (macro F1 0.54 → 0.73 with the June 2026 fine-tuned
   ensemble; 0.51 → 0.71 stock); these are calibrated for PTB-XL-like data and
   should be re-tuned for a different source.
4. **djongo + Django 4.2 incompatible.** The full Django 4.2 stack was specified but
   migration fails on djongo 1.3.6. The project runs on **Django 3.2.25 LTS** instead,
   which is the latest version djongo supports.
5. **CORS pinned to port 3000.** If another local React app squats `:3000`, Vite will
   refuse to bind. Configurable via `CORS_ALLOWED_ORIGINS` in `backend/.env`.
6. **Validated on public datasets, not a clinical cohort.** The models are
   evaluated on held-out public benchmarks (PTB-XL, Kaggle Brain-Tumor, LGG — see
   [VALIDATION.md](maybe%20read/VALIDATION.md)), not on a real prospective patient cohort.
   ECG leakage was checked externally (Chapman-Shaoxing-Ningbo, macro AUC 0.981 ≈ PTB-XL) — no meaningful leakage.
7. **No data-driven neuro-cardiac correlation.** The "combined interpretation" in
   the PDF is rule-based template text, not a learned/measured relationship between
   brain pathology and ECG. Testing that hypothesis needs a paired imaging+ECG
   cohort — the project's principal future work.
8. **Echo & EEG weights are not bundled.** EchoNet checkpoints must be downloaded
   separately; BIOT ships only an encoder, so the EEG IIIC head is fine-tuned in-repo
   on Kaggle HMS. Both endpoints raise a clear `FileNotFoundError` until weights are
   present — by design (honest failure, not a crash).
9. **EEG accuracy is modest (frozen-encoder, subset-trained).** Unlike the other
   turnkey-pretrained modalities, the BIOT IIIC head was trained on CPU on a
   1,451-EEG subset with the encoder frozen → balanced-acc ~0.28 (above the 0.167
   chance floor, below BIOT's full-data ~0.5). More data did not lift it; the real
   lever is a GPU full-fine-tune. EEG is also a **critical-care** screening task
   (functional), not tumour-specific — it never localises or diagnoses a tumour.

---

## References

1. **Buda, M., Saha, A., Mazurowski, M. A.** (2019). Association of genomic
   subtypes of lower-grade gliomas with shape features automatically extracted
   by a deep learning algorithm. *Computers in Biology and Medicine*, **109**, 218–225.
2. **Liu, Z., et al.** (2021). Swin Transformer: Hierarchical Vision Transformer
   using Shifted Windows. *ICCV 2021*. arXiv:2103.14030.
3. **Ronneberger, O., Fischer, P., Brox, T.** (2015). U-Net: Convolutional
   Networks for Biomedical Image Segmentation. *MICCAI 2015*.
4. **Avetisyan, A., et al.** (2023). Deep Neural Networks Generalization and
   Fine-Tuning for 12-lead ECG Classification. *arXiv:2305.18592*.
5. **Wagner, P., et al.** (2020). PTB-XL, a large publicly available
   electrocardiography dataset. *Scientific Data*, **7**, 154.
6. **Huang, G., Liu, Z., van der Maaten, L., Weinberger, K. Q.** (2017).
   Densely Connected Convolutional Networks. *CVPR 2017*.
7. **Makowski, D., et al.** (2021). NeuroKit2: A Python toolbox for
   neurophysiological signal processing. *Behavior Research Methods*, **53**, 1689–1696.
8. **He, K., Zhang, X., Ren, S., Sun, J.** (2016). Deep Residual Learning for
   Image Recognition. *CVPR 2016*.
9. **Esteva, A., et al.** (2019). A guide to deep learning in healthcare.
   *Nature Medicine*, **25**(1), 24–29.
10. **Lundberg, S. M., Lee, S. I.** (2017). A unified approach to interpreting
    model predictions. *NeurIPS 2017*.
11. **Ouyang, D., et al.** (2020). Video-based AI for beat-to-beat assessment of
    cardiac function (EchoNet-Dynamic). *Nature*, **580**, 252–256.
12. **Yang, C., Westover, M. B., Sun, J.** (2023). BIOT: Biosignal Transformer for
    Cross-data Learning in the Wild. *NeurIPS 2023*.
13. **Jing, J., et al.** (2023). Development of expert-level classification of
    seizures and rhythmic/periodic patterns during EEG interpretation (IIIC).
    *Neurology*.

---

## License

Released under the **MIT License** for academic use — see the [LICENSE](LICENSE)
file (which also carries the medical disclaimer and the third-party model/dataset
attributions).

**Medical disclaimer:** this is a research/educational prototype, **not** a
certified medical device and not for clinical use; all outputs are AI-assisted
estimates requiring review by a qualified professional.

**Data-governance posture (honest scope):** this is a prototype. Access is
doctor-scoped at the API layer and no real patient data is committed to the
repository, but **formal GDPR controls are not implemented** — there is no
consent capture, pseudonymisation, retention-expiry, or access audit log. These
are noted as future work, not claimed as delivered.

---

## Acknowledgments

- **ISPRAS** for the open-source `ecglib` library.
- **mateuszbuda** for the brain segmentation U-Net.
- **Devarshi** (HuggingFace) for the Brain Tumor Swin classifier.
- **PTB-XL contributors** for the ECG dataset that underpins the ecglib models.
- **EchoNet-Dynamic team (Stanford)** for the echocardiography models.
- **Chaoqi Yang et al.** for the open-source **BIOT** biosignal transformer (MIT).
- **Kaggle HMS — Harmful Brain Activity Classification** for the public IIIC dataset.
- **Anthropic Claude Code** for development assistance during the implementation
  phase.
- **Université Abdelhamid Mehri – Constantine 2** and supervisors Prof. Derdour
  Makhlouf and Prof. Talbi Hichem for guidance and project framing.
