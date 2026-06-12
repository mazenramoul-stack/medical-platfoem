# My Project – The End
### Multimodal Medical AI Platform — how it works, from A to Z

> Master's PFE — University of Constantine 2.
> One web application where a doctor uploads brain MRI, 12-lead ECG, echocardiogram video, or EEG recordings, gets an AI analysis for each, and downloads one combined PDF report.

---

## 1. The idea in one paragraph

Hospitals analyse the brain and the heart with separate tools. This project puts **four AI modalities in one place**: a doctor logs in, registers a patient, uploads a medical file, and the platform runs a pre-trained deep-learning model on it **immediately** (no waiting queue), saves the result to the patient's record, and can generate a **single PDF report** that combines all findings with a rule-based interpretation.

---

## 2. Architecture (the big picture)

```
                 Doctor's browser
                       │  JWT token on every request
                       ▼
   ┌─────────────────────────────────────────────┐
   │  FRONTEND — React 19 + Vite (port 3000)     │
   │  TailwindCSS UI · Redux Toolkit state       │
   │  Axios (auto-attaches JWT, 401 → /login)    │
   └──────────────────────┬──────────────────────┘
                          │  REST  /api/*
                          ▼
   ┌─────────────────────────────────────────────┐
   │  BACKEND — Django 3.2 + DRF (port 8000)     │
   │                                             │
   │  apps/authentication  email login, JWT      │
   │  apps/patients        doctor-scoped CRUD    │
   │  apps/mri             upload + inference    │
   │  apps/ecg             upload + inference    │
   │  apps/echo            upload + inference    │
   │  apps/eeg             upload + inference    │
   │  apps/reports         combined PDF          │
   │  apps/inference       ◄── the "brain":      │
   │     model loader + 4 pipelines              │
   └──────────┬───────────────────┬──────────────┘
              │                   │
              ▼                   ▼
   ┌──────────────────┐   ┌──────────────────────┐
   │  MongoDB          │   │  media/ filesystem   │
   │  (via djongo)     │   │  uploads, masks,     │
   │  users, patients, │   │  overlays, plots,    │
   │  analysis records │   │  PDF reports         │
   └──────────────────┘   └──────────────────────┘
```

**Three tiers:** React in the browser → Django REST API → MongoDB + media files.
**One rule everywhere:** every query filters by the logged-in doctor — a doctor can never see another doctor's patients (the chain is *analysis → patient → doctor*).

---

## 3. The journey, A to Z

| Step | What happens | Where |
|---|---|---|
| **A. Register / Login** | Doctor signs up with email + password; gets a JWT access token (60 min) + refresh token (7 days). | `apps/authentication`, `/api/auth/` |
| **B. Add a patient** | Name, age, sex, notes. The patient belongs to *this* doctor only. | `apps/patients`, `/api/patients/` |
| **C. Upload a file** | MRI image, ECG (CSV/EDF/WFDB), echo video, or EEG (.edf), via drag-and-drop. | frontend modules → `/api/mri/` etc. |
| **D. Inference runs synchronously** | The view calls the pipeline **in the same request**. First call ever downloads ~700 MB of weights to the local cache; after that it's fast. | `apps/inference` |
| **E. Result saved + displayed** | Diagnosis, probabilities, and generated images (mask overlay, ECG plot…) are stored on the patient record and rendered in the UI. | MongoDB + `media/` |
| **F. Patient history** | One endpoint aggregates all analyses of a patient across all modalities. | `/api/patients/<id>/history/` |
| **G. PDF report** | ReportLab builds one document with every modality's findings + a combined, rule-based interpretation. The PDF survives even if the patient is later deleted. | `apps/reports` |

---

## 4. The four AI modalities

| Modality | Model(s) | What it outputs | Validated result |
|---|---|---|---|
| **MRI** | U-Net (`mateuszbuda/brain-segmentation-pytorch`) + 4-class image classifier (ViT-B/16, `Devarshi/Brain_Tumor_Classification`, fine-tuned in this project) | Tumour mask + overlay; tumour type (glioma / meningioma / pituitary / none) | Dice **0.852** on LGG; **95.4 %** accuracy on Kaggle Brain-Tumor (fine-tuned June 2026; stock model: 80.4 %) |
| **ECG** | `ecglib` DenseNet-1D, 7 pathology models (AFIB, STACH, SBRAD, RBBB, LBBB, PVC, 1AVB) — **1AVB/RBBB/PVC fine-tuned by me, June 2026** | Per-pathology probability with **per-pathology tuned thresholds** | Mean ROC-AUC **0.980**, macro balanced-acc **0.887**, macro F1 **0.727** on PTB-XL fold 10 (stock: 0.978 / 0.884 / 0.711); independently re-checked on Chapman-Shaoxing-Ningbo |
| **Echo** | EchoNet-Dynamic (LV segmentation + ejection-fraction regression) | EF % + left-ventricle outline on the video | EF MAE **4.01 %** (400 TEST videos; a 40-video subset gave 3.19 %), segmentation Dice **0.897** — matches the published paper |
| **EEG** | BIOT pretrained encoder + IIIC head fine-tuned in-repo on Kaggle HMS | 6-class harmful-brain-activity screening (seizure, LPD, GPD, LRDA, GRDA, other) | Balanced-acc **0.278** (chance = 0.167) — modest, honestly reported |

Two design points worth defending:

- **Lazy singleton loader** — models load once, on first use, and stay in memory. Echo and EEG weights are *deliberately not bundled* (license/size); the loader raises a clear `FileNotFoundError` with instructions instead of crashing.
- **Result envelope contract** — every pipeline returns `{status, ...fields, error?}` and **never raises into the view**, so the API can report partial results (e.g. ECG still answers even if some sub-models are missing).
- **Safety-first / never-miss posture** (June 2026) — because a screening tool must not produce false negatives, every model is calibrated for **high recall**: ECG all 7 pathologies ≥0.95 (13 FN in 2,198 records), MRI tumour-detection 0.998 (a tumour is never silently cleared), Echo reduced-EF 0.95 (flag EF<55 %), EEG seizure-routing 0.966. This is a **decision-threshold change, not retraining — no GPU needed**; the cost is lower precision (more cases flagged for human review), which is the correct trade for screening. The one gap: EEG *general* abnormal screen (0.931) and 6-way *type* recall — the latter is inter-rater-ambiguous and unreachable by anyone. Full numbers: `maybe read/VALIDATION.md` §0.

---

## 5. Technology stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React 19, Vite, TailwindCSS, Redux Toolkit, Axios, Three.js | fast dev server, modern SPA, 3D landing scenes |
| Backend | Django 3.2 LTS, Django REST Framework, SimpleJWT | mature REST stack, JWT auth |
| Database | MongoDB through **djongo** | document store for flexible analysis records (djongo forces Django 3.2 and Python 3.10/3.11) |
| ML | PyTorch, torchvision, MONAI, transformers, ecglib | run the pre-trained models |
| Reports | ReportLab | programmatic PDF generation |

---

## 6. How to start it (2 terminals)

```bash
# Terminal 1 — backend (from backend/, venv active, MongoDB running)
python manage.py migrate
python manage.py runserver          # → http://localhost:8000

# Terminal 2 — frontend (from frontend/)
npm install
npm run dev                         # → http://localhost:3000
```

Or on Windows just double-click **`start.bat`**. Seed a demo doctor with
`python tests/seed_database.py` → `doctor@test.com / TestPass123!`.

---

## 7. What makes the design extensible

The platform is **modality-agnostic**: each medical domain is an isolated plug-in (one inference pipeline + one Django app + one frontend module + one report section). Adding CT or genomics tomorrow follows an 8-step recipe without touching any existing modality's code — that is the main architectural contribution beyond the models themselves.

---

## 8. Where every model comes from — sources & links

All models start from weights **pre-trained by their original authors**; none were trained from scratch. Three components were **fine-tuned in this project**: the MRI classifier (June 2026), three of the seven ECG models (1AVB, RBBB, PVC — June 2026), and the EEG IIIC head. Here is the full provenance trail.

### 8.1 MRI — tumour segmentation (U-Net)

| What | Link |
|---|---|
| Pre-trained weights (auto-downloaded via `torch.hub`) | <https://github.com/mateuszbuda/brain-segmentation-pytorch> |
| PyTorch Hub model page | <https://pytorch.org/hub/mateuszbuda_brain-segmentation-pytorch_unet/> |
| Training + validation dataset (TCGA **LGG**, 110 patients, FLAIR + masks) | <https://www.kaggle.com/datasets/mateuszbuda/lgg-mri-segmentation> |
| Paper — Buda et al., 2019 | <https://doi.org/10.1016/j.compbiomed.2019.05.002> |
| Architecture paper — U-Net, Ronneberger et al., 2015 | <https://arxiv.org/abs/1505.04597> |

### 8.2 MRI — tumour-type classification (ViT, 4 classes)

| What | Link |
|---|---|
| Pre-trained / fine-tuned weights (auto-downloaded from HuggingFace) | <https://huggingface.co/Devarshi/Brain_Tumor_Classification> |
| Base backbone it was fine-tuned from (Google ViT-B/16) | <https://huggingface.co/google/vit-base-patch16-224-in21k> |
| Training + validation dataset (Brain Tumor MRI, ~7 000 images, 4 classes) | <https://www.kaggle.com/datasets/masoudnickparvar/brain-tumor-mri-dataset> |
| Architecture paper — ViT, Dosovitskiy et al., 2021 | <https://arxiv.org/abs/2010.11929> |

### 8.3 ECG — 7 pathology classifiers (DenseNet-1D)

| What | Link |
|---|---|
| Library + pre-trained weights (`ecglib 1.0.1` by ISPRAS; weights auto-download on first use) | <https://github.com/ispras/EcgLib> |
| PyPI package | <https://pypi.org/project/ecglib/> |
| Paper behind the weights — Avetisyan et al., 2023 | <https://arxiv.org/abs/2305.18592> |
| **Validation** dataset I used (PTB-XL, fold 10) | <https://physionet.org/content/ptb-xl/1.0.3/> |
| **Independent external check** dataset (Chapman-Shaoxing-Ningbo — anti-leakage test) | <https://physionet.org/content/ecg-arrhythmia/1.0.0/> |
| Signal-quality / DSP helper (NeuroKit2, rule-based, no weights) | <https://github.com/neuropsychology/NeuroKit> |

### 8.4 Echo — LV segmentation + ejection fraction (EchoNet-Dynamic)

| What | Link |
|---|---|
| Project page (Stanford) — weights + dataset access requests | <https://echonet.github.io/dynamic/> |
| Code repository | <https://github.com/echonet/dynamic> |
| Training + validation dataset (EchoNet-Dynamic, ~10 030 echo videos) | <https://echonet.github.io/dynamic/index.html#dataset> |
| Paper — Ouyang et al., *Nature* 2020 | <https://www.nature.com/articles/s41586-020-2145-8> |

> ⚠ The two checkpoints (`echonet_seg.pt`, `echonet_ef.pt`) are **not bundled** in my repo — they must be downloaded from the project page into `backend/models_weights/echonet/`.

### 8.5 EEG — harmful-brain-activity screening (BIOT + IIIC head)

| What | Link |
|---|---|
| BIOT code + **pre-trained encoder** checkpoints (`EEG-PREST-16-channels.ckpt` is bundled in my repo) | <https://github.com/ycq091044/BIOT> |
| Paper — Yang, Westover, Sun, *NeurIPS 2023* | <https://arxiv.org/abs/2305.10351> |
| Dataset I used to **fine-tune the 6-class IIIC head myself** (Kaggle HMS competition data) | <https://www.kaggle.com/competitions/hms-harmful-brain-activity-classification> |
| IIIC label definitions — Jing et al., *Neurology* 2023 | <https://doi.org/10.1212/WNL.0000000000207127> |

> The IIIC head is the only weight **trained in this project** (`tools/train_eeg_head.py`, encoder frozen, Kaggle HMS subset). BIOT's authors release only the encoder, never an IIIC classification head.

### 8.6 Summary table — pretrained vs. trained by me

| Modality | Weights origin | Trained by me? |
|---|---|---|
| MRI U-Net | torch.hub — mateuszbuda | No (used as released) |
| MRI ViT | HuggingFace — Devarshi | **Yes — continue-trained on Kaggle Brain-Tumor (Colab T4, June 2026): 80.4 % → 95.4 %** |
| ECG ×7 | ecglib — ISPRAS | **Partly — fine-tuned 3 of 7 (1AVB, RBBB, PVC) on PTB-XL (Colab T4, June 2026): macro F1 0.711 → 0.727**; also calibrated all decision thresholds (F1 0.51 → 0.71 stock, 0.54 → 0.73 after fine-tune) |
| Echo (2 models) | Stanford EchoNet-Dynamic | No (used as released) |
| EEG encoder | BIOT authors | No (used as released, frozen) |
| **EEG IIIC head** | **this repo** | **Yes — fine-tuned on Kaggle HMS** |

---

## 9. Where everything lives in the repo

```
backend/apps/inference/    the 4 pipelines + model_loader (lazy singleton)
backend/apps/<modality>/   upload view + DB model per modality
backend/models_weights/    biot/ (bundled encoder) · echonet/ (you download)
frontend/src/modules/      one folder per screen domain
tools/eval_*.py            reproduce every number in this document
tools/train_eeg_head.py    the one training script (EEG IIIC head)
maybe read/VALIDATION.md   full metrics, confusion matrices, reproduce commands
```

---

*Honest limits and future work are in the companion file: **Problems of My Project.md**.*
