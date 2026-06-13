# How the Platform Works — A to Z

A complete walkthrough of the Multimodal Medical AI Platform: what it is, how a
request flows through it, how each of the four modalities works, how the frontend,
backend, database, reports and validation fit together — and an honest account of
what it does **not** do.

---

## 0. What it is (in one paragraph)
A web platform for clinicians that runs **pretrained** deep-learning models on four
kinds of medical data — **brain MRI**, **12-lead ECG**, **echocardiogram video**,
and **EEG** — stores the results per patient, and merges them into a downloadable
PDF report. Each modality is analysed **independently**; there is **no learned
multimodal fusion** (see §12). The contribution is the *integration architecture* and
the *validation*, not new models.

---

## 1. High-level architecture

```
┌──────────────────────────── Browser (clinician) ────────────────────────────┐
│  React 19 + Vite + Tailwind (dark-neon 3D UI, Three.js)                      │
│  Redux Toolkit (auth/patients/notifications) · Axios (JWT, 401→/login)       │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                 │  REST  /api/*   (Authorization: Bearer <JWT>)
┌───────────────────────────────▼──────────────────────────────────────────────┐
│  Django 3.2 + DRF + SimpleJWT                                                 │
│  apps/authentication  apps/patients  apps/mri  apps/ecg  apps/echo  apps/eeg  │
│  apps/reports                          apps/inference (engine)                │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                 │  in-process call (synchronous, no queue)
┌───────────────────────────────▼──────────────────────────────────────────────┐
│  Inference engine — ModelLoader (lazy singleton, CUDA/CPU)                    │
│   MRI : U-Net (seg) + Swin (classify)                                        │
│   ECG : 7× DenseNet-1D (ecglib) + NeuroKit2 (HRV)                            │
│   Echo: DeepLabV3 (seg) + R(2+1)D (EF)        [EchoNet-Dynamic]              │
│   EEG : BIOT transformer + IIIC 6-class head                                  │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                 ▼
                MongoDB (via djongo) · media/ files · ReportLab PDFs
```

---

## 2. Technology stack (actual, with versions)
- **Backend:** Python 3.10/3.11, Django 3.2.25 LTS, DRF 3.14, SimpleJWT 5.3,
  MongoDB via **djongo 1.3.6** + pymongo 3.12, config via python-decouple.
- **ML:** PyTorch 2.2, torchvision 0.17, transformers 4.38, **ecglib 1.0.1**,
  NeuroKit2 0.2.7, SciPy 1.11, OpenCV (echo video), MNE (EEG), **BIOT** (vendored).
- **Frontend:** React + Vite 8, TailwindCSS 3.4, Redux Toolkit, react-router 6,
  Axios, **Three.js / @react-three/fiber / drei** (the 3D UI), ReportLab (PDF).
- **PDF:** ReportLab 4.0.

---

## 3. The request lifecycle (the spine every modality shares)
Take an MRI upload as the canonical example ([apps/mri/views.py](../backend/apps/mri/views.py)):

1. **`POST /api/mri/upload/`** with multipart `{patient_id, file}` + a JWT.
2. The view **validates** the file (extension allow-list, size cap).
3. It resolves the patient with `get_object_or_404(Patient, pk=patient_id,
   doctor=request.user)` — this one line enforces **doctor isolation** (you can only
   attach analyses to *your* patients).
4. It creates an `MRIAnalysis` row with `status = PROCESSING` and saves the upload.
5. **Inference runs synchronously, in the request thread**, wrapped in a hard
   timeout: `run_inference_with_timeout(analyze_mri, path, 300)`.
6. The returned result dict updates the row → `COMPLETED` (HTTP 201) or `FAILED`
   (HTTP 202); the serialized record is returned.

Every modality (`mri`, `ecg`, `echo`, `eeg`) follows this exact shape. The frontend
Axios client therefore uses a **5-minute timeout** — the upload call blocks until
inference finishes. **There is no Celery/RQ task queue.**

### Two contracts every pipeline obeys
1. **Doctor isolation** — every queryset filters `patient__doctor=request.user`.
   The FK chain is `<Analysis> → patient → doctor`.
2. **Result-envelope contract** — pipelines return a plain dict
   `{status, ...result_fields, error?, error_type?}` and **never raise into the
   view**. Structured failure is part of the contract — all 7 ECG models load
   normally, but the envelope can still report a runtime partial (e.g. 6/7) if a
   model fails mid-request.

---

## 4. Authentication & authorization
- Custom **email-login `User`** (no username); `USERNAME_FIELD='email'`.
- **SimpleJWT**: 60-min access token, 7-day refresh; the access token embeds
  `email/role/full_name`.
- Frontend stores tokens in `localStorage`; Axios attaches `Authorization: Bearer`
  and, on a `401`, clears tokens and redirects to `/login`.
- Authorization = **per-doctor data isolation** on every endpoint.

---

## 5. The model loader (how weights are managed)
`ModelLoader` ([apps/inference/model_loader.py](../backend/apps/inference/model_loader.py))
is a **process-wide thread-safe singleton**:
- **Lazy:** a model loads only on first use; subsequent calls reuse it.
- **Cached:** MRI/ECG weights download once (~700 MB) to `~/.cache`; Echo/EEG weights
  load from `backend/models_weights/`.
- **Device-aware:** picks CUDA if available, else CPU (this project runs CPU).
- `warmup()` can force-load everything at boot.

---

## 6. MRI pipeline (A→Z)  — `analyze_mri`
Two stages ([apps/inference/mri_pipeline.py](../backend/apps/inference/mri_pipeline.py)):

1. **Load & preprocess** — any format (PNG/JPG/TIFF/DICOM/NIfTI) → RGB; for the
   U-Net: resize 256×256, **per-channel z-score**.
2. **Segmentation (U-Net)** — `mateuszbuda/brain-segmentation-pytorch` (torch.hub,
   ~7.7 M params) outputs a probability map **already sigmoid-activated**; threshold
   at 0.5 → tumour mask. *(Critical fix: an earlier version applied `sigmoid` twice,
   saturating every mask; removing the second sigmoid restored it.)* A **saturation
   guard** rejects degenerate masks covering >75% of the image.
3. **Classification (Swin Transformer (Swin-T))** — `Devarshi/Brain_Tumor_Classification` (HuggingFace,
   ~28 M) over the image (or a bounding-box crop of the tumour) → one of
   **glioma / meningioma / notumor / pituitary** + confidence.
4. **Fusion logic (rule-based)** — `generate_clinical_note()` combines the U-Net and
   Swin verdicts into a recommendation (agree → confirmed; disagree → "radiologist
   review", etc.). This is **rule-based text, not a learned fusion**.
5. **Outputs** — 3 PNGs (original / mask / overlay), a text report, and the result
   fields stored on `MRIAnalysis`.

**Validated:** segmentation **Dice 0.85** (LGG); classification **95.4%** accuracy
(Kaggle test split; fine-tuned June 2026 — stock model: 80.4%). See §11.

---

## 7. ECG pipeline (A→Z)  — `analyze_ecg`
Two parallel streams ([apps/inference/ecg_pipeline.py](../backend/apps/inference/ecg_pipeline.py)):

1. **Load & standardize** — `.csv/.edf/.dat+.hea` → a fixed `(12 leads, 5000
   samples)` array at **500 Hz**, padded/trimmed to 10 s, missing leads broadcast.
2. **Filter & normalize** — 4th-order **Butterworth band-pass 0.5–40 Hz** (removes
   baseline wander + EMG noise) + **per-lead z-score**.
3. **Deep-learning stream** — **7× DenseNet-1D-121** (`ecglib`, ~8 M each), one
   binary classifier per pathology: **AFIB, 1AVB, STACH, SBRAD, RBBB, LBBB, PVC**.
   Each outputs a probability; a pathology is "detected" if it exceeds a
   **per-pathology tuned threshold** (calibrated on PTB-XL fold 9 — see §11). Primary
   diagnosis = highest detected pathology, else "Normal Sinus Rhythm".
4. **Classical stream** — **NeuroKit2** on lead II → mean HR, **RMSSD/SDNN/pNN50**,
   brady/tachy flags. This *cross-checks* the deep-learning output (e.g. STACH vs HR).
5. **Sanitize** — NaN/Inf scrubbed before JSON. Outputs stored on `ECGAnalysis`.

**Validated:** mean **AUC 0.980**, macro balanced accuracy **0.887** (PTB-XL test
fold 10; 1AVB/RBBB/PVC fine-tuned June 2026). Threshold calibration raised
macro-F1 0.54→0.73 (stock: 0.51→0.71). See §11.

---

## 8. Echo pipeline (A→Z)  — `analyze_echo`
Video-based, two pretrained EchoNet-Dynamic models
([apps/inference/echo_pipeline.py](../backend/apps/inference/echo_pipeline.py)):

1. **Decode video** — OpenCV reads the `.avi/.mp4` → frames → 112×112 grayscale →
   **EchoNet normalization**.
2. **Ejection fraction (R(2+1)D-18)** — a 3-D spatiotemporal CNN runs on 32-frame
   clips sampled across the video; EF is **averaged over clips** → EF % + category
   (Normal / Mildly reduced / Reduced).
3. **LV segmentation (DeepLabV3-ResNet50)** — per-frame left-ventricle mask; LV area
   per frame locates **end-diastole (max area)** and **end-systole (min area)**.
4. **Outputs** — EF %, category, ED/ES areas, a 3-panel overlay PNG, report.

**Validated:** **EF MAE 3.19% / R² 0.86**, LV **Dice 0.90** (EchoNet TEST subset),
matching the published model. See §11.

---

## 9. EEG pipeline (A→Z)  — `analyze_eeg`
Transformer-based, **BIOT** + a fine-tuned IIIC head
([apps/inference/eeg_pipeline.py](../backend/apps/inference/eeg_pipeline.py)):

1. **Load & montage** — MNE reads the `.edf`; `eeg_preprocess.edf_to_bipolar`
   builds the standard bipolar montage; resample to BIOT's rate.
2. **Segment** — the recording is split into consecutive **10-second segments**.
3. **Classify (BIOT)** — BIOT (Biosignal Transformer; tokenizes each channel-second,
   adds channel + positional embeddings, runs a Transformer encoder). The released
   BIOT encoder + a **6-class IIIC head fine-tuned on the Kaggle HMS dataset**
   (`tools/train_eeg_head.py`) classify each segment into the Ictal-Interictal-Injury
   Continuum: **SZ, LPD, GPD, LRDA, GRDA, Other**.
4. **Aggregate** — per-class proportions over time, a **dominant pattern**, and a
   **harmful-activity flag** (any SZ/LPD/GPD) + a distribution plot. Stored on
   `EEGAnalysis`.

**Scope (honest):** EEG is the **functional** complement to the **structural** MRI —
it flags harmful brain electrical activity (which a tumour can cause via
tumour-related seizures / focal discharges), but it **does not diagnose tumours**,
and IIIC is a general critical-care cohort, not a tumour cohort.

---

## 10. Data model, database & files
```
User (doctor)
  └─< Patient
        ├─< MRIAnalysis   (file, status, result_*, report)
        ├─< ECGAnalysis   (file, status, hrv JSON, pathology-probs JSON, ...)
        ├─< EchoAnalysis  (file, status, result_ef, ef_category, ED/ES, overlay)
        ├─< EEGAnalysis   (file, status, dominant_pattern, harmful, class-dist JSON)
        └─< Report (FK to patient + each analysis via SET_NULL; ReportLab PDF)
```
- **MongoDB** via djongo; uploads + generated artifacts under `backend/media/`.
- Deleting an analysis sets the report's FK null (report survives); deleting a
  patient cascades its analyses + reports.

---

## 11. Validation (how "it works" is proven)
Each modality has a reproducible harness in `tools/`; full tables in
[VALIDATION.md](../maybe%20read/VALIDATION.md).

| Modality | Dataset (held-out) | Headline result |
|---|---|---|
| ECG (7 pathologies; 3 fine-tuned June 2026) | PTB-XL fold 10 | mean AUC **0.980**, balanced-acc **0.887**, macro F1 0.727 |
| MRI classification (fine-tuned June 2026) | Kaggle Brain-Tumor `Testing/` | accuracy **95.4%**, macro-F1 0.954 |
| MRI segmentation | LGG MRI | **Dice 0.85** |
| Echo (EF + LV) | EchoNet-Dynamic | EF MAE **3.2%**, R² 0.86, Dice **0.90** |
| EEG (IIIC 6-class) | Kaggle HMS | reported by `tools/eval_eeg.py` (fine-tuned head) |

> **Safety-first operating points (June 2026):** each model is also calibrated to
> minimize false negatives — ECG recall ≥0.95 (all 7), MRI tumour-detection 0.998,
> Echo reduced-EF 0.95, EEG seizure-routing 0.966 — a decision-rule change, no GPU.
> Full table + precision costs in [VALIDATION.md §0](../maybe%20read/VALIDATION.md).

Two engineering contributions surfaced during validation: the **ECG per-pathology
threshold calibration** (+0.20 macro-F1) and the **MRI double-sigmoid fix**
(Dice 0.02 → 0.85).

---

## 12. What the platform does NOT do (read before writing the thesis)
Be precise about scope — these are easy to over-claim:
- **No learned multimodal fusion.** Modalities run independently; the "combined
  interpretation" in the PDF is **rule-based template text**, not feature fusion or a
  joint model. The thesis outline's "Multimodal Fusion / Feature Fusion" is **future
  work**, not implemented.
- **No neuro-cardiac / cross-modal correlation.** Not modelled; no paired dataset.
- **No Explainable-AI module.** SHAP / LIME are **not** implemented.
- **EEG model naming:** uses **BIOT**, not EEGNet; ECG uses **DenseNet-1D**, not a
  generic ResNet1D. Describe what's actually there.
- **EEG is not a tumour detector** — functional screening only.
- **Inference is synchronous** (no queue) — doesn't scale to concurrent load; echo
  video on CPU is slow.
- **Security notes** (for the ethics section): PHI under `/media/` is served via an
  **HMAC-signed, time-limited** view (`core/media.py`) — not raw — though a signed URL
  is time-scoped, not per-identity; JWT in `localStorage`; no encryption at rest / audit log.

---

## 13. Frontend (how the UI works)
- **Dark-neon 3D theme** (Three.js): particle background, mouse glow, 3D Brain &
  Heart on Login/Dashboard, tilt cards, glass panels. A global CSS "dark shim"
  re-skins the data pages; flagship pages use the 3D scenes.
- **Routing** ([App.jsx](../frontend/src/App.jsx)): public `/login` `/register`;
  everything else behind `ProtectedRoute` inside `DashboardLayout`. Per modality:
  a landing page (`/mri` `/ecg` `/echo` `/eeg`) and a result page (`/…/:id`).
- **State:** Redux slices (`auth`, `patients`, `notifications`); per-resource service
  modules (`mriService`, `ecgService`, `echoService`, `eegService`, …) wrap REST.
- **Patient detail** is the hub: tabs for MRI / ECG / Echo / EEG / Reports; each tab
  uploads via a modal and lists past analyses; "Generate report" combines completed
  analyses into the PDF.

---

## 14. End-to-end example (a full session)
1. Doctor registers / logs in → JWT stored, redirected to the 3D dashboard.
2. Creates a patient (doctor auto-attached from the JWT).
3. Opens the patient → **New MRI analysis** → drag-drops a brain MRI.
4. The backend stores it, runs U-Net + Swin synchronously (~30–60 s on CPU), saves
   tumour type + mask + overlay, returns the record.
5. The MRI result page shows the overlay, type, confidence, and report.
6. Repeat for ECG / Echo / EEG as available.
7. **Generate report** → ReportLab builds one PDF with a section per completed
   modality + a rule-based combined note → auto-downloads.

---

## 15. How to run it
```
# one-click (Windows): checks Mongo/ports, starts backend + frontend, opens browser
start.bat            (stop.bat to stop)

# or manually
cd backend && .\venv\Scripts\Activate.ps1
python manage.py migrate && python manage.py runserver      # needs MongoDB :27017
cd frontend && npm run dev                                  # http://localhost:3000
```
Seed demo login: `python backend/tests/seed_database.py` → `doctor@test.com` /
`TestPass123!`.

---

## 16. Repository map (where to look)
- `backend/apps/inference/` — the four pipelines + `model_loader` + preprocessing.
- `backend/apps/{mri,ecg,echo,eeg}/` — per-modality upload/list/detail APIs.
- `backend/apps/reports/` — combined PDF generation.
- `backend/core/` — settings, root URLconf.
- `frontend/src/modules/` — per-modality React UIs; `components/`, `services/`, `store/`.
- `tools/eval_*.py` — the validation harnesses.
- `VALIDATION.md`, `METHODOLOGY.md`, `README.md`, `CLAUDE.md` — docs.

---

*This document describes the system as actually implemented. Where the thesis
proposal lists features not present (learned fusion, SHAP/LIME, EEGNet), treat them
as future work — do not report them as built.*
