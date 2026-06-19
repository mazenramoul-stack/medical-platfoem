# The Final Result — Mazen PFE

### Multimodal Medical AI Platform for Cardiology & Oncology — the complete A‑to‑Z

> **Master's PFE (Projet de Fin d'Études), 2025 / 2026**
> Université Abdelhamid Mehri — Constantine 2
> Faculté des Nouvelles Technologies de l'Information et de la Communication
> Département : Informatique Fondamentale et ses Applications
> **Student:** Mazen Ramoul · `mazen.ramoul@univ-constantine2.dz`
> **Supervisor:** Prof. DERDOUR Makhlouf · **Co‑supervisor:** Prof. TALBI Hichem

This single document explains everything I built and measured, so it can stand alone as the
backbone of the report and the defence. It covers, in order:

1. What the platform is and how it works (functionality + end‑to‑end workflow)
2. Full **platform architecture** and system design
3. How **each AI model works** + its **detailed architecture**
4. **What I did to obtain the parameters** (fine‑tuning + the data used)
5. **Results and a fair comparison** with the pre‑existing (stock) models, with the **datasets** and the **source links** of every model
6. Honest limitations (essential for a credible defence)
7. A **presentation guide**: slide plan, talking points, and likely jury questions
8. Appendix: one master table of all sources/datasets + reproducibility commands

> ⚠️ **Numbers discipline.** Every metric below was **verified locally** on this machine with the
> `tools/eval_*.py` harnesses (not just copied from Colab). The authoritative source for each number
> is `maybe read/VALIDATION.md`; the source for every model/dataset link is
> `docs/PROJECT_FUNCTIONALITY_A_TO_Z.md` §8. If a number ever changes, re‑run the harness and update both.

---

## 0. The idea in one paragraph

Hospitals analyse the brain and the heart with **separate, siloed tools**. This project puts
**four AI modalities in one web application**: a doctor logs in, registers a patient, uploads a
medical file (**brain MRI**, **12‑lead ECG**, **echocardiogram video**, or **EEG `.edf`**), and the
platform runs a pre‑trained deep‑learning model on it **immediately** (no waiting queue), saves the
result to the patient's record, and can generate **one combined PDF report** with a rule‑based
interpretation. The engineering contribution is the **integrated, modular, doctor‑isolated
platform**; the scientific contribution is **measuring, calibrating, and (where a free GPU allowed)
fine‑tuning** four public models, and reporting their accuracy **honestly** — including where they
fall short.

---

# PART A — HOW THE PLATFORM WORKS

## A.1 What it does (feature list)

| Feature | What the doctor gets |
|---|---|
| **Patient management** | Doctor‑scoped CRUD with a per‑patient history view |
| **MRI tumour analysis** | Pixel‑level segmentation overlay **+** 4‑class tumour type (glioma / meningioma / no‑tumour / pituitary) **+** a Grad‑CAM/SHAP explainability overlay |
| **12‑lead ECG screening** | 7 binary arrhythmia/conduction classifiers + HRV metrics (RMSSD, SDNN, pNN50) with reference ranges |
| **Echocardiography** | Ejection‑fraction (EF) estimate + left‑ventricle segmentation, with a clinical category (reduced / mildly reduced / normal) |
| **EEG screening** | Harmful‑brain‑activity 6‑class distribution over 10 s segments + a "harmful" flag |
| **Combined PDF report** | A multi‑section ReportLab PDF with a **rule‑based** combined interpretation |
| **Security** | Email‑based JWT auth (1‑hour access / 7‑day refresh); strict multi‑doctor data isolation |
| **Robustness** | Pipelines return **structured errors**, never crash the API; lazy model loading; CPU‑compatible (GPU auto‑detected) |

## A.2 The end‑to‑end workflow (7 steps)

```
1. AUTH      Doctor logs in → receives a JWT (sent on every request).
2. UPLOAD    Doctor registers/selects a patient → uploads a file to the modality endpoint
             (POST /api/mri|ecg|echo|eeg/).
3. PREPROCESS+INFERENCE   The view calls the modality pipeline SYNCHRONOUSLY (in the request
             thread). The lazy model loader returns a cached singleton (first call downloads
             ~700 MB of MRI/ECG weights; later calls reuse the local cache).
4. ENVELOPE  The pipeline returns a plain dict {status, ...result_fields, error?, error_type?}.
             It NEVER raises into the view — structured failure is part of the contract, so the
             API can report partial results (e.g. ECG with 6/7 models loaded).
5. PERSIST   The view writes envelope fields onto the modality record, sets status=completed
             (or failed), and saves artefact paths (overlays/plots) under media/.
6. RENDER    The frontend refetches the record and renders the modality‑specific result view
             (segmentation overlay, HRV table, per‑pathology probability table, EF + LV
             segmentation, EEG class distribution/timeline) + the raw textual report.
7. REPORT    Doctor calls POST /api/reports/generate/ with a patient ID + ≥1 completed analysis
             IDs. The reports app composes a multi‑section PDF with a rule‑based combined
             interpretation and streams it for download.
```

**Per‑modality preprocessing (Step 3), in one line each:**

- **MRI** (`analyze_mri`): load image → U‑Net produces a tumour probability mask (overlay + area + confidence); the central crop is classified by the Swin‑T into one of 4 types; a Grad‑CAM overlay + normalized peak are computed inline.
- **ECG** (`analyze_ecg`): load the 12‑lead signal → run the 7 DenseNet‑1D classifiers (per‑pathology calibrated thresholds) → NeuroKit2 computes HRV time‑domain metrics → render a signal plot.
- **Echo** (`analyze_echo`): sample 32‑frame clips → R(2+1)D‑18 regresses EF (averaged over clips); DeepLabV3 segments the LV at end‑diastole/end‑systole.
- **EEG** (`analyze_eeg`): parse `.edf` → BIOT‑exact preprocessing (16‑channel longitudinal‑bipolar montage, resample to 200 Hz, 10 s = 2000‑sample segments, per‑channel 95th‑percentile amplitude normalisation) → classify every 10 s segment (frozen encoder + fine‑tuned IIIC head) → aggregate to per‑class proportions, a dominant pattern, and a harmful flag (any SZ/LPD/GPD).

## A.3 Two contracts that hold the backend together

1. **Doctor isolation.** Every queryset in `patients`, `mri`, `ecg`, `echo`, `reports` filters by the
   requesting doctor. The FK chain is `<Analysis> → patient → doctor`. An endpoint that can return
   another doctor's data is treated as a bug. (Even the on‑demand MRI `/explain/` endpoint resolves
   the record from the requesting doctor's queryset, so a foreign id returns **404**, never a leak.)
2. **Pipeline result envelope.** Inference functions always return `{status, ...fields, error?,
   error_type?}` and never raise into the view. This is what lets the platform report **partial
   results** and degrade gracefully instead of 500‑ing.

## A.4 Complete functionality catalogue (everything the platform does)

A grouped list of every capability — use it to make sure no feature goes unmentioned in the defence.

**Clinical inference (per modality)**
- **MRI:** tumour **segmentation** (pixel mask + area + overlay) → **bounding‑box crop** → 4‑class **type** classification (glioma / meningioma / no‑tumour / pituitary) + confidence.
- **ECG:** **7 binary pathology** classifiers (AFIB, 1AVB, STACH, SBRAD, RBBB, LBBB, PVC) with per‑pathology calibrated thresholds; **heart‑rate + HRV** (RMSSD, SDNN, pNN50 via NeuroKit2, with reference ranges); annotated **signal plot** with R‑peaks.
- **Echo:** **ejection‑fraction** regression (averaged over clips) + **LV segmentation** at end‑diastole/end‑systole + a **clinical category** (reduced / mildly‑reduced / normal).
- **EEG:** per‑**10 s window** 6‑class IIIC classification → aggregated **class distribution**, a **dominant pattern**, and a **harmful‑activity flag** (any SZ/LPD/GPD).

**Explainability (XAI) — the part to show off**
- **Grad‑CAM** heatmap for the MRI Swin classifier (where the model looked), computed **inline** during every MRI analysis (returns the overlay + a normalized peak `{nx, ny}`).
- **SHAP** (Captum **GradientShap**) pixel‑level saliency, on demand via `POST /api/mri/{id}/explain/` (Grad‑CAM **+** SHAP together).
- A **faithfulness harness** (`tools/eval_mri_explainer.py`): Grad‑CAM↔SHAP agreement (Spearman + top‑k IoU), peak‑in‑mask localization, and a deletion causal test.

**Cross‑cutting clinical features**
- **Patient management** — doctor‑scoped CRUD + a `/history/` aggregate endpoint per patient.
- **Combined PDF report** — multi‑section ReportLab document (per‑modality findings + a rule‑based combined interpretation), generated from any subset of completed analyses and streamed for download.
- **Result persistence** — every analysis is saved to the patient record with status (`completed`/`failed`) and artefact paths.

**User experience**
- **Interactive 3D anatomy** (react‑three‑fiber): rotatable **Brain3D** and **Heart3D** scenes (`Scene3D`, `Anatomy3DPanel`) that visually anchor each result to the organ — a memorable demo element.
- **Light / dark theme** (CSS‑variable palettes) and **English / French i18n** (per‑namespace dictionaries) across the whole UI.
- **Per‑modality result views** (segmentation overlay, probability tables, EF + LV view, EEG distribution/timeline) + the raw textual report; toast notifications and an `ErrorBoundary`.

**Security & data protection**
- **JWT auth** (email login, 1 h access / 7 d refresh, auto‑refresh on 401).
- **Multi‑doctor isolation** on every queryset (foreign id → 404).
- **HMAC‑signed, time‑limited media URLs** (no raw `/media/` ever returned).
- **Rate limiting** (login 10/min, register 5/min, refresh 30/min).

**Reliability & configurability**
- **Lazy singleton model loader** (downloads once, caches; CPU‑compatible, GPU auto‑detected; `warmup()` pre‑loads MRI+ECG).
- **Structured‑error envelope** → graceful **partial results** (e.g. ECG reporting 6/7 if one model fails mid‑request).
- **Timeout‑guarded inference** (`run_inference_with_timeout`, 300 s).
- **Auto‑detected fine‑tuned weights** (ECG/MRI checkpoints picked up automatically when present).
- **Switchable operating points** via env vars — `ECG_THRESHOLD_MODE=f1|recall`, `MRI_NOTUMOR_MIN_CONFIDENCE`, `REDUCED_EF_SCREEN_CUTOFF` — i.e. balanced vs high‑sensitivity screening **without code changes**.

**Dev / ops tooling**
- **Management commands** (`seed_database`, `cleanup_media` retention), **sample generators** (MRI/ECG/EEG), and the full **`tools/eval_*.py`** validation suite.
- **Tests** (doctor isolation, auth, ECG reject, health, media security, pipelines) + **GitHub Actions CI**; **cloud deploy** (HF Space + Vercel + Atlas).

## A.5 The interesting engineering (technical highlights worth a slide)

These are the non‑obvious, "I actually engineered this" details that impress a technical jury:

1. **Grad‑CAM on a Transformer, not a CNN.** Swin has no conv feature map — I hook the **final LayerNorm**, fold the `[B, L, C]` token sequence back into a `side×side` grid, and weight by mean gradient. Standard CNN Grad‑CAM doesn't apply here.
2. **SHAP via GradientShap with a two‑point baseline** (black + channel‑mean grey) — the fast, faithful gradient‑based SHAP variant suited to a deep net on CPU (unlike KernelSHAP/LIME).
3. **Explainability is best‑effort.** Grad‑CAM runs in a `try/except` so a failure logs a warning and returns `None` — it can **never break the inference envelope**. (Both explainers deliberately run **outside `torch.no_grad()`** because they backprop.)
4. **Two‑stage MRI (crop‑then‑classify).** The U‑Net mask drives a **bounding‑box crop** that is then classified — localising the tumour before typing it, which also makes the Grad‑CAM tighter.
5. **The double‑sigmoid bug fix.** Diagnosed that the U‑Net already sigmoids inside `forward()`; removing the redundant second sigmoid took Dice **0.02 → 0.85** — a real debugging contribution, not a retrain.
6. **Calibration ≠ retraining, and I proved it.** ECG macro‑F1 jumped 0.51 → 0.71 while ROC‑AUC stayed flat — evidence the gain came from per‑pathology threshold calibration, not an overfit model.
7. **No‑regression fine‑tuning rule.** A fine‑tuned checkpoint ships only if it beats stock on the target metric — fine‑tuning can never degrade the deployed ensemble.
8. **Quantified uncertainty.** Bootstrap 95% CIs on every headline + an EEG permutation test (p = 0.0005) — numbers are never presented bare.
9. **One operating point, two behaviours.** The same models serve a **balanced** or a **high‑sensitivity** screen by flipping an env var — the recall‑first tables stay in the code.
10. **Faithfulness measured at the coarser resolution.** Grad‑CAM (7×7) vs SHAP (224×224) are compared at the common coarser grid on purpose — comparing at the full grid spuriously drives correlation to ~0.

---

# PART B — PLATFORM ARCHITECTURE & SYSTEM DESIGN

## B.1 Big picture

```
                         Doctor's browser
                               │  JWT on every request (Axios interceptor)
                               ▼
   ┌───────────────────────────────────────────────────────────────┐
   │  FRONTEND — React 19 + Vite 8 + Tailwind 3.4 + Redux Toolkit    │
   │  Per‑domain modules: Auth, Dashboard, Patients, MRI, ECG,       │
   │  Echo, EEG, Reports.  3D scenes via react‑three‑fiber.          │
   └───────────────────────────────────────────────────────────────┘
                               │  REST / JSON  (api/…)
                               ▼
   ┌───────────────────────────────────────────────────────────────┐
   │  BACKEND — Django 3.2.25 + DRF 3.14 + SimpleJWT                 │
   │                                                                 │
   │   apps/authentication   custom User (email login) + JWT views   │
   │   apps/patients         doctor‑scoped CRUD + /history/          │
   │   apps/mri  ecg  echo  eeg   upload + SYNCHRONOUS inference      │
   │   apps/reports          ReportLab combined PDF                  │
   │   apps/inference        lazy singleton model loader + pipelines │
   │                         + explainers/ (Grad‑CAM, SHAP)          │
   └───────────────────────────────────────────────────────────────┘
        │                         │                         │
        ▼                         ▼                         ▼
   MongoDB (via djongo)      Local weight cache        media/ (overlays,
   patients, analyses,       ~/.cache/torch,            plots, PDFs)
   reports metadata          ~/.cache/huggingface
```

## B.2 Backend slicing (Django apps under `backend/apps/`, registered as `apps.<name>`)

| App | Responsibility |
|---|---|
| `apps/authentication` | Custom User (email login), JWT issue/refresh |
| `apps/patients` | Doctor‑scoped CRUD + `/history/` aggregate endpoint |
| `apps/mri` | Upload + synchronous inference + result URLs; on‑demand `/explain/` (Grad‑CAM + SHAP) |
| `apps/ecg` | Upload + synchronous inference + signal plot URL |
| `apps/echo` | Upload + synchronous EchoNet inference (LV segmentation + EF regression) |
| `apps/eeg` | Upload `.edf` + synchronous BIOT/IIIC inference (6‑class) |
| `apps/reports` | ReportLab PDF generation with combined interpretation |
| `apps/inference` | Lazy singleton model loader + the 4 pipelines + utils; vendored BIOT under `biot/`; post‑hoc MRI explainers under `explainers/` |

**URL prefixes** (`core/urls.py`): `api/auth/`, `api/` (patients), `api/mri/`, `api/ecg/`, `api/echo/`,
`api/eeg/`, `api/reports/`. MRI additionally exposes `POST api/mri/{id}/explain/`.

## B.3 Key design decisions (and why)

- **Synchronous in‑request inference (no Celery/RQ).** Simpler to reason about and deploy for a PFE;
  the trade‑off is that it blocks horizontal scaling (one long request per inference). Honest debt.
- **Lazy singleton loader.** Models load once on first use and are cached; this is why the first call
  is slow (~700 MB download) and later calls are fast. Echo/EEG heads are *not* auto‑downloaded by
  design (they need a license/dataset access), so a fresh checkout returns a clear `FileNotFoundError`.
- **MongoDB via djongo.** Chosen for schemaless flexibility; the cost is a **hard version freeze**
  (Python 3.10/3.11, Django 3.2 LTS) because djongo is incompatible with Django 4.x and Python 3.12+.
- **Structured‑error envelope.** Lets the UI show partial/failed analyses without the API crashing.

## B.4 Frontend wiring

- Axios instance attaches the JWT and intercepts `401 → /login`.
- Redux slices: `auth`, `patients`, `notifications`. Per‑resource service modules wrap REST calls;
  components consume via hooks (`useAuth`, `usePatients`, `useApi`).
- Functional components only (the single allowed class component is `ErrorBoundary`).
- Light/dark theme + EN/FR i18n via CSS‑variable palettes and context providers.

## B.5 Deployment (cloud)

The monorepo splits for the cloud: **backend → a Hugging Face Docker Space** (port 7860, gunicorn,
synchronous), **frontend → Vercel** (SPA rewrite so deep links resolve), **DB → MongoDB Atlas**
(`MONGO_URI` = `mongodb+srv://…`). A first‑boot `token_blacklist` migration traceback on the Space is
*expected* (djongo can't translate SimpleJWT's BigAutoField retypes; a three‑pass fake‑migrate works
around it). Local dev remains `runserver` + `npm run dev`.

---

# PART C — HOW EACH MODEL WORKS + DETAILED ARCHITECTURE

> **One sentence on the nature of the models** (a frequent jury question): the ECG models are **1‑D
> CNNs on the raw 12‑lead signal** (not spectrograms, not LSTM); MRI uses a **CNN (U‑Net)** + a
> **Transformer (Swin)**; Echo uses a **2‑D CNN** (segmentation) + a **3‑D spatiotemporal CNN** (EF);
> EEG uses **BIOT**, a **linear‑attention Transformer** over per‑channel STFT tokens.

## C.1 MRI — segmentation (U‑Net) + classification (Swin‑T)

**Two‑stage pipeline.** First the U‑Net produces a tumour mask (where), then the Swin‑T classifies the
tumour type (what).

- **U‑Net** — a 2‑D CNN encoder–decoder (~7.7 M params). The encoder downsamples the image into
  increasingly abstract feature maps; the decoder upsamples back to full resolution with **skip
  connections** that re‑inject fine spatial detail, so the output is a per‑pixel probability map of
  "tumour vs background". It applies a **sigmoid inside its own `forward()`** — a detail that mattered
  (see Part D / the double‑sigmoid fix).
- **Swin Transformer (Swin‑T)** — a hierarchical Vision Transformer (~28 M params). It splits the
  224×224 image into patches and computes self‑attention **inside local windows**, then **shifts** the
  windows between layers so information crosses window boundaries; resolution is halved and channels
  doubled at each stage (like a CNN's pyramid, but with attention). The final LayerNorm emits a token
  grid that a linear head maps to the 4 classes: **glioma, meningioma, no‑tumour, pituitary**.
  *(Architecture: Liu et al., "Swin Transformer", ICCV 2021, arXiv:2103.14030.)*

**Explainability (my XAI contribution).** For the Swin‑T I added post‑hoc attribution:
- **Grad‑CAM** hooks the Swin **final LayerNorm** (token sequence `[B, L, C]`, `L = side²`, folded back
  to a `side×side` grid — there is no conv feature map), weights channels by mean gradient, ReLUs and
  normalises → a heatmap of "where the model looked".
- **SHAP** via **Captum GradientShap** — a gradient‑based SHAP variant giving a pixel‑level saliency map.
- Both must run **outside `torch.no_grad()`** (they backprop). Faithfulness is checked by
  `tools/eval_mri_explainer.py` (Grad‑CAM↔SHAP agreement, peak‑in‑mask localization, deletion test).

## C.2 ECG — 7× DenseNet‑1D‑121 ensemble + NeuroKit2 (HRV)

- **DenseNet‑1D‑121** (~8 M params each) — a **1‑D convolutional** DenseNet applied to the **raw
  12‑lead waveform**. In a DenseNet every layer receives the feature maps of *all* preceding layers
  (dense connectivity), which improves gradient flow and feature reuse. Seven independent binary
  models, one per pathology: **AFIB, 1AVB, STACH, SBRAD, RBBB, LBBB, PVC**. Each outputs an independent
  presence probability; a **per‑pathology calibrated threshold** turns it into a yes/no.
  *(Library: `ecglib` 1.0.1 by ISP RAS; weights paper: Avetisyan et al., 2023, arXiv:2305.18592.)*
- **NeuroKit2** — classical DSP (no neural net) for HRV time‑domain metrics (RMSSD, SDNN, pNN50),
  shown against reference ranges.

## C.3 Echo — DeepLabV3‑ResNet50 (segmentation) + R(2+1)D‑18 (EF)

- **DeepLabV3‑ResNet50** (~40 M params) — a 2‑D CNN semantic‑segmentation network (ResNet‑50 backbone +
  atrous/dilated convolutions + ASPP) with the classifier head replaced by a single‑channel conv to
  segment the **left ventricle**. Locates end‑diastole/end‑systole frames.
- **R(2+1)D‑18** (~31 M params) — a **3‑D spatiotemporal CNN** that factorises 3‑D convolution into a
  2‑D spatial conv followed by a 1‑D temporal conv. It regresses **ejection fraction** from sampled
  **32‑frame clips**, averaged over clips. The final FC layer is replaced with a single regression unit.
  *(Both from EchoNet‑Dynamic, Stanford; Ouyang et al., Nature 2020.)*

## C.4 EEG — BIOT (Biosignal Transformer), IIIC 6‑class

- **BIOT** (~3 M params) — a **linear‑attention Transformer** over biosignals. Each EEG channel is
  turned into **STFT tokens** (short‑time Fourier patches), embedded, and processed by a Transformer
  whose **linear attention** scales to long multi‑channel sequences. The encoder is **genuinely
  pretrained** (BIOT's released `EEG‑PREST‑16‑channels` checkpoint, bundled).
- **IIIC head** — a small 6‑class linear head on top, classifying each 10 s window into
  **SZ (seizure), LPD, GPD, LRDA, GRDA, Other**. The first three are flagged **harmful**.
  This head is **not released by BIOT** — I fine‑tuned it on the Kaggle HMS dataset.
  *(BIOT: Yang et al., NeurIPS 2023, github.com/ycq091044/BIOT — vendored under `apps/inference/biot/`.)*

---

# PART D — WHAT I DID TO OBTAIN THE PARAMETERS (FINE‑TUNING + DATA)

This is the heart of the scientific contribution. For each model: **what was pretrained**, **what I
changed**, and **the data I used**.

## D.1 Summary — pretrained vs. trained by me

| Modality | Weights origin | Did I train it? |
|---|---|---|
| MRI U‑Net | torch.hub — mateuszbuda | **No** — used as released; I **fixed a double‑sigmoid bug** (Dice 0.02 → 0.85) |
| MRI Swin‑T | HuggingFace — Devarshi | **Yes** — continue‑trained on Kaggle Brain‑Tumor (Colab T4, June 2026): **80.4% → 95.4%** |
| ECG ×7 | ecglib — ISP RAS | **Partly** — **6 of 7 deployed checkpoints are fine‑tuned** (all but AFIB; two Colab T4 passes under a no‑regression rule) and **all 7 thresholds calibrated** (the big lever) |
| Echo (×2) | Stanford EchoNet‑Dynamic | **No** — used as released |
| EEG encoder | BIOT authors | **No** — used as released (then unfrozen for the full fine‑tune) |
| **EEG IIIC head** | **this repo** | **Yes** — fine‑tuned on Kaggle HMS |

## D.2 MRI Swin‑T — full fine‑tune (the headline gain)

- **Process:** continue‑training the Devarshi Swin‑T on the **Kaggle Brain Tumor MRI dataset**
  `Training/` split, using the platform's **exact preprocessing** and the **original label order** (so
  the comparison to the stock model is apples‑to‑apples), on a free **Colab T4** GPU (June 2026).
- **Data:** ~7 000 images, 4 classes (glioma / meningioma / no‑tumour / pituitary).
- **Result:** **80.4% → 95.4%** test accuracy. The stock model's dominant error (pituitary confusion)
  is gone (recall 0.995); the remaining weakness is **glioma recall 0.83** (48 gliomas read as
  meningioma — a clinically related distinction).
- **Verification:** re‑verified locally with `tools/eval_mri_classifier.py`; Colab numbers reproduced.

## D.3 ECG — threshold calibration + partial fine‑tuning

Two distinct improvements (important to separate them in the defence):

1. **Threshold calibration — no retraining.** The stock pipeline used a flat `p > 0.5` decision rule
   that over‑flagged badly. I tuned a **per‑pathology threshold on PTB‑XL validation fold 9**, then
   applied it **unchanged** to held‑out test fold 10 (no leakage). This alone raised **macro F1
   0.514 → 0.711**. (ROC‑AUC is unchanged — proof this is a *calibration* gain, not a different model.)
2. **Fine‑tuning (Colab T4), under a strict no‑regression rule.** A first pass (balanced‑accuracy
   objective) kept fine‑tuned weights only where they beat stock — **1AVB, RBBB, PVC** (AUCs 0.972 /
   0.995 / 0.993). A second **F1‑objective** pass with ECG‑domain augmentation targeted the weak classes
   **STACH/SBRAD/1AVB/LBBB**, kept those that beat baseline on **F1**, and replaced 1AVB with its F1
   version. With re‑tuned thresholds the deployed ensemble reaches **macro F1 0.727 → 0.777**. In the
   deployed ensemble **6 of 7 models are fine‑tuned** (only AFIB stays stock); the single biggest win is
   **STACH F1 0.684 → 0.852**.
- **Data:** PTB‑XL (PhysioNet v1.0.3); thresholds tuned on fold 9, evaluated on fold 10 (2 198 records).
- **Leakage caveat & mitigation:** `ecglib` may have trained on a corpus that includes PTB‑XL, so I
  added an **independent external check** on **Chapman‑Shaoxing‑Ningbo** (`tools/eval_ecg_external.py`).

## D.4 EEG IIIC head — fine‑tuning (frozen, then full)

- **Frozen‑encoder head (CPU).** Trained only the 6‑class head on a 1 451‑EEG balanced subset of HMS
  (split **by patient** — no patient in both train and test). Result: balanced acc **0.278**, κ 0.147.
  Critically, **3.7× more data did not move the headline** — the signature of a **frozen‑encoder ceiling**.
- **Full fine‑tune (unfreeze encoder, Colab GPU) — DEPLOYED.** Encoder LR 1e‑5. Result: balanced acc
  **0.379**, κ **0.352** (95% bootstrap CI [0.359, 0.400]; permutation p = 0.0005 vs the 0.167 chance
  floor; CI does **not** overlap the frozen baseline). I **rejected** a higher‑raw‑BA variant (0.415,
  enc‑LR 3e‑5) because it was a rare‑class artifact rather than a genuine improvement.
- **Data:** Kaggle **HMS — Harmful Brain Activity Classification**.
- **Honest framing:** 0.379 is **2.3× chance** and a real gain, but **below** BIOT's published full‑data
  IIIC level (~0.5), which is itself **capped by inter‑rater ambiguity** (expert κ ≈ 0.5). The deployed
  value is as a **sensitivity‑first screen** (94.9% of seizures routed for review), not a definitive
  6‑way classifier.

## D.5 MRI U‑Net — the bug fix (a real contribution, not training)

The U‑Net applies sigmoid **inside** `forward()`, so its output is already a probability map. The
original pipeline applied `torch.sigmoid()` **again**, squashing [0,1] into [0.5, 0.73] so every pixel
crossed the 0.5 threshold → the mask saturated (≈100% of the image) and the saturation guard then
suppressed it to "no tumour". Removing the redundant sigmoid took **Dice from ~0.02 → 0.85**.

---

# PART E — RESULTS & COMPARISON WITH THE PRE‑EXISTING MODELS

> All "current" numbers are the **deployed** values verified locally; "stock" is the **pre‑existing
> public model as released**, evaluated by me on the same data with the same harness.

## E.1 MRI tumour‑type classification (Swin‑T, 4‑class)

| Metric | Stock (Devarshi as released) | **Mine (fine‑tuned)** |
|---|---:|---:|
| Test accuracy | 80.4% | **95.4%** |
| Pituitary recall | (low — dominant error) | 0.995 |
| Glioma recall | — | 0.83 (remaining weakness) |
| No‑tumour recall | — | 1.000 (400/400) |

- **Dataset:** Kaggle Brain Tumor MRI (~7 000 images). **Reproduce:** `tools/eval_mri_classifier.py`.

## E.2 MRI tumour segmentation (U‑Net) — used as released, bug‑fixed

| Metric | Before fix | **After fix** | Source paper |
|---|---:|---:|---:|
| Dice (tumour‑positive slices) | ~0.02 (100% saturated) | **0.852** | ~0.89 mean DSC |
| Dice (all slices) | — | 0.827 | — |
| IoU | — | 0.78–0.80 | — |

- **Dataset:** LGG MRI Segmentation (3 929 slices: 1 373 tumour‑positive, 2 556 empty), with
  ground‑truth masks. **Reproduce:** `tools/eval_mri_segmentation.py`.

## E.3 ECG 7‑pathology ensemble (PTB‑XL fold 10, 2 198 records)

| Metric | Stock ecglib | **Mine (calibrated + fine‑tuned)** |
|---|---:|---:|
| Mean ROC‑AUC | 0.978 | **0.981** |
| Macro F1 | 0.711 | **0.777** |
| Macro balanced accuracy | 0.884 | **0.896** |
| Subset (exact‑match) accuracy | 0.831 | **0.880** |

- Threshold calibration alone (no retraining): **macro F1 0.514 → 0.711**. Two fine‑tune passes then
  lifted it to **0.777** (6/7 models fine‑tuned; headline **STACH F1 0.684 → 0.852**). Weakest remaining
  after fine‑tune: **SBRAD F1 0.613**, **1AVB F1 0.632** — precision‑limited despite high AUC. Full
  per‑pathology table (stock vs deployed) in **Part H**.
- **Datasets:** PTB‑XL fold 10 (primary), Chapman‑Shaoxing‑Ningbo (external leakage check).
  **Reproduce:** `tools/eval_ecg_classifier.py`, `tools/eval_ecg_external.py`.

## E.4 Echocardiography — EF + LV segmentation (used as released)

| Metric | **400 videos (headline)** | 40‑video subset |
|---|---:|---:|
| EF MAE | **4.01%** | 3.19% |
| EF RMSE | 5.30% | 4.01% |
| EF R² | **0.831** | 0.860 |

- **Dataset:** EchoNet‑Dynamic (Stanford), official TEST split (~10 030 videos total; EF on 400).
  **Reproduce:** `tools/eval_echo.py`. *(No fine‑tuning — used as released; weights not bundled.)*

## E.5 EEG harmful‑brain‑activity (BIOT/IIIC, 6‑class)

| Metric | Frozen head | **Full fine‑tune (deployed)** | Reference |
|---|---:|---:|---:|
| Balanced accuracy | 0.278 | **0.379** | 0.167 = chance; ~0.5 = BIOT full‑data |
| Cohen's κ | 0.147 | **0.352** | 0 = chance; ≈0.5 = expert agreement |
| Seizure recall (screen) | — | **0.949** | — (sensitivity‑first value) |

- **Dataset:** Kaggle HMS — Harmful Brain Activity Classification. 95% CI [0.359, 0.400], p = 0.0005.
  **Reproduce:** `tools/eval_eeg.py` (+ `tools/bootstrap_cis.py` for the CIs). 

## E.6 Sources of the pre‑existing models + the datasets (links)

| Modality | Pre‑existing model (source link) | Dataset (link) |
|---|---|---|
| MRI classification | Devarshi/Brain_Tumor_Classification — https://huggingface.co/Devarshi/Brain_Tumor_Classification (base: https://huggingface.co/microsoft/swin-tiny-patch4-window7-224) | Kaggle Brain Tumor MRI — https://www.kaggle.com/datasets/masoudnickparvar/brain-tumor-mri-dataset |
| MRI segmentation | mateuszbuda/brain-segmentation-pytorch (torch.hub) | LGG MRI Segmentation — https://www.kaggle.com/datasets/mateuszbuda/lgg-mri-segmentation |
| ECG ×7 | ecglib 1.0.1 (ISP RAS) — https://github.com/ispras/EcgLib · https://pypi.org/project/ecglib/ · paper https://arxiv.org/abs/2305.18592 | PTB‑XL — https://physionet.org/content/ptb-xl/1.0.3/ · external: Chapman‑Shaoxing‑Ningbo https://physionet.org/content/ecg-arrhythmia/1.0.0/ |
| Echo (×2) | EchoNet‑Dynamic — https://echonet.github.io/dynamic/ · https://github.com/echonet/dynamic · paper https://www.nature.com/articles/s41586-020-2145-8 | EchoNet‑Dynamic (~10 030 videos) — https://echonet.github.io/dynamic/index.html#dataset |
| EEG | BIOT — https://github.com/ycq091044/BIOT (Yang et al., NeurIPS 2023) | Kaggle HMS — https://www.kaggle.com/competitions/hms-harmful-brain-activity-classification |
| Swin paper | Liu et al., ICCV 2021 — https://arxiv.org/abs/2103.14030 | — |

---

# PART F — HONEST LIMITATIONS (say these before the jury does)

- **The multimodal "combination" is rule‑based, not learned.** The combined report applies template
  logic over each modality's output; it is **not** a model that learned cross‑modal correlations.
  Closing this needs a **paired clinical dataset** (the natural continuation of this PFE). This is the
  biggest *scientific* gap — frame it as future work, not a flaw.
- **EEG is a screen, not a classifier.** Even after a full fine‑tune (0.379 balanced acc), 6‑class IIIC
  is below clinical use; its value is high seizure sensitivity (0.949) for routing to expert review.
- **Possible ECG train/test overlap.** ecglib may have seen PTB‑XL; mitigated (not eliminated) by the
  independent Chapman‑Shaoxing‑Ningbo external check.
- **Models are validated on different datasets.** E.g. MRI segmentation is validated on LGG (which has
  masks) but classification on the Kaggle set — so a single uploaded image is **not** validated
  end‑to‑end through both stages simultaneously.
- **Structural/engineering debt.** djongo freezes Django 3.2 + Python 3.10/3.11; synchronous inference
  blocks scaling; Echo/EEG weights are not bundled (license/dataset access).
- **Operating point.** The platform runs the **balanced** operating point by default (e.g. ECG macro‑F1
  thresholds); a **recall‑first** high‑sensitivity mode is available behind env vars but is opt‑in.

---

# PART G — PRESENTATION GUIDE

## G.1 Suggested slide deck (~12–14 slides)

1. **Title** — project, university, your name, date.
2. **Problem** — brain & heart analysed by siloed tools; no single integrated, explainable workflow.
3. **Solution in one screen** — a screenshot of the dashboard + the "upload → analyse → combined PDF" arrow.
4. **Live demo / GIF** — login → upload an MRI → segmentation overlay + 4‑class result + Grad‑CAM.
5. **Platform architecture** — the Part B.1 diagram.
6. **The 4 modalities** — one slide, the "Models actually used" table (Part C intro quote).
7. **Model deep‑dive ×1** — pick MRI (most visual): U‑Net + Swin + Grad‑CAM, with the overlay image.
8. **What I actually did** — Part D.1 table (pretrained vs trained by me) — this is your contribution.
9. **Results: MRI** — 80.4% → 95.4% + confusion matrix.
10. **Results: ECG** — calibration 0.51 → 0.71, fine‑tune → 0.777, with the comparison table.
11. **Results: Echo + EEG** — EF MAE 4.01% / R² 0.831; EEG honest framing (screen, CI, p‑value).
12. **Honest limitations + future work** — Part F (especially the "learned fusion" gap).
13. **Engineering** — doctor isolation, structured‑error envelope, lazy loading, cloud deploy.
14. **Conclusion** — one integrated, validated, honestly‑measured, explainable platform.

## G.2 Talking points (one‑liners that land)

- "I didn't just call APIs — I **measured every model on held‑out data, calibrated it, and fine‑tuned
  what a free GPU allowed**, then reported the numbers honestly, including where they fail."
- "The **ECG headline gain came from calibration, not retraining** — proven by ROC‑AUC staying flat."
- "**More EEG data didn't help with a frozen encoder** — that's why I unfroze it; the gain is
  statistically significant (CIs don't overlap, p = 0.0005)."
- "The combination is **presentational, not learned** — and I know exactly what dataset would fix that."

## G.3 Likely jury questions (and crisp answers)

- *Is it agentic / does it use an LLM?* No — it's a **modular pipeline** of task‑specific models, not an
  agent. Deterministic and auditable, which suits clinical use.
- *Are the ECG models spectrogram/LSTM based?* No — **1‑D CNNs on the raw 12‑lead signal**.
- *Did you train from scratch?* No — I used **pre‑trained public models**, then calibrated/fine‑tuned;
  training brain/heart models from scratch needs data and compute beyond a PFE, and transfer learning is
  the correct, honest choice.
- *Why is EEG only ~0.38?* 6‑class IIIC is **capped by inter‑rater ambiguity (κ≈0.5)**; even the original
  authors reach ~0.5 with full‑data fine‑tuning. I deploy it as a **high‑sensitivity screen**.
- *Why MongoDB / why old Django?* djongo gives schemaless flexibility but freezes versions — a conscious,
  documented trade‑off; I'd swap djongo to modernise.
- *How do you stop one doctor seeing another's patients?* Every queryset filters on the requesting
  doctor along the `analysis → patient → doctor` FK chain; a foreign id returns 404.

---

# PART H — DETAILED RESULTS (backup slides)

These are the full tables behind the headline numbers — keep them as **backup slides** and pull them
up only if the jury asks for depth. Every number is verified locally on held‑out data.

## H.1 MRI 4‑class classification — per‑class, stock vs fine‑tuned (n = 1 600, 400/class)

**Stock hub model (Devarshi, as released):** accuracy **80.4%** (1286/1600), macro F1 0.794.

| Class | Precision (stock → mine) | Recall (stock → mine) | F1 (stock → mine) |
|---|---|---|---|
| glioma | 0.981 → **0.997** | 0.517 → **0.833** | 0.678 → **0.907** |
| meningioma | 0.856 → **0.888** | 0.698 → **0.990** | 0.769 → **0.936** |
| no‑tumour | 0.891 → **0.952** | 1.000 → **1.000** | 0.942 → **0.976** |
| pituitary | 0.651 → **0.995** | 1.000 → **0.995** | 0.789 → **0.995** |

**The story:** the stock model dumped 109 gliomas + 105 meningiomas into "pituitary" (precision 0.65).
The fine‑tune fixed that (pituitary precision 0.65 → 0.995); the only residual weakness is glioma↔meningioma
(glioma recall 0.83), a genuinely hard, clinically related distinction. *(The stock 80.4% is far below the
model card's ~99% because it ran on the full image with the platform's preprocessing — the fine‑tune
closes that gap under identical conditions, so the comparison is apples‑to‑apples.)*

## H.2 ECG 7‑pathology — per‑pathology, stock vs deployed (PTB‑XL fold 10)

| Pathology | Support | AUC (stock → mine) | Sensitivity (stock → mine) | Precision (stock → mine) | F1 (stock → mine) |
|---|--:|---|---|---|---|
| AFIB (stock) | 152 | 0.975 → 0.975 | 0.855 → 0.855 | 0.812 → 0.812 | 0.833 → 0.833 |
| 1AVB ★ | 79 | 0.960 → **0.975** | 0.709 → **0.759** | 0.412 → **0.541** | 0.521 → **0.632** |
| STACH ★ | 82 | 0.990 → **0.993** | 0.634 → **0.915** | 0.743 → **0.798** | 0.684 → **0.852** |
| SBRAD ★ | 64 | 0.950 → **0.955** | 0.562 → 0.531 | 0.409 → **0.723** | 0.474 → **0.613** |
| RBBB ★ | 166 | 0.993 → **0.995** | 0.916 → 0.861 | 0.784 → **0.867** | 0.844 → **0.864** |
| LBBB ★ | 62 | 0.982 → 0.982 | 0.935 → 0.823 | 0.699 → **0.810** | 0.800 → **0.816** |
| PVC ★ | 114 | 0.992 → **0.993** | 0.904 → 0.886 | 0.752 → **0.777** | 0.821 → **0.828** |

★ = fine‑tuned checkpoint (**6/7**; only AFIB is stock). Deployed thresholds: AFIB 0.91, 1AVB 0.90,
STACH 0.92, SBRAD 0.89, RBBB 0.95, LBBB 0.96, PVC 0.96. **The headline win is STACH** (F1 0.684 → 0.852;
sensitivity 0.63 → 0.92). The F1 objective sometimes *trades recall for precision* (e.g. SBRAD precision
0.41 → 0.72), which is the right call for an over‑flagging screen.

## H.3 Statistical robustness — bootstrap 95% confidence intervals

Every headline is a single‑split point estimate; to prove the numbers are **stable, not a lucky split**,
each carries a 95% CI from **2 000 bootstrap resamples** of the cached per‑record predictions
(`tools/bootstrap_cis.py --boot 2000 --seed 0`).

| Modality | Metric | Point | 95% CI |
|---|---|--:|---|
| MRI | 4‑class accuracy (n = 1 600) | 95.4% | **[94.3, 96.4]** |
| MRI | macro F1 | 0.954 | [0.942, 0.963] |
| ECG | macro ROC‑AUC (n = 2 198) | 0.980 | **[0.973, 0.985]** |
| Echo | EF MAE (n = 400) | 4.01% | **[3.68, 4.35]** |
| Echo | EF R² | 0.831 | [0.789, 0.863] |
| Echo | LV segmentation Dice | 0.897 | — |
| EEG | balanced accuracy — frozen head (n = 1 883) | 0.278 | [0.257, 0.299] |
| EEG | balanced accuracy — **deployed full fine‑tune** (n = 2 681) | **0.379** | **[0.359, 0.400]** |

**EEG significance:** a permutation test (2 000 label shuffles) puts the 6‑class chance line at ~0.167
(95th percentile 0.186); the deployed 0.379 sits far outside it — **p = 0.0005**. The deployed CI
[0.359, 0.400] does **not overlap** the frozen baseline's [0.257, 0.299], so the fine‑tune gain is
statistically real, not noise.

## H.4 How my results compare to the published literature (state of the art)

| Modality | My result | Published reference | Reading |
|---|---|---|---|
| MRI segmentation (U‑Net) | Dice **0.852** | Buda et al. ~**0.89** mean DSC | Within a few points; gap is a per‑image vs per‑volume normalisation detail |
| MRI classification (Swin‑T) | **95.4%** (4‑class) | Swin‑T ImageNet‑1k ~81% top‑1 (arch ref); Devarshi card ~99% on its own preprocessing | Strong; my number is apples‑to‑apples under the platform's preprocessing |
| Echo EF (R(2+1)D‑18) | MAE **4.01%**, R² **0.831** | EchoNet‑Dynamic (Ouyang, *Nature* 2020) ≈ **4.0% MAE** | **Matches** the published model — nothing for a GPU to win back |
| Echo LV segmentation | Dice **0.897** | EchoNet‑Dynamic paper ~0.92 | Matches |
| EEG IIIC (BIOT) | balanced acc **0.379** | BIOT full‑data IIIC ~**0.5**; chance 0.167; expert κ ≈ 0.5 | Above chance, below clinical — a screen, capped by label ambiguity |

---

# PART I — TECHNICAL REFERENCE (input/output & preprocessing)

Exact, source‑verified I/O for a "how does data actually flow" backup slide.

| Modality | Input | Preprocessing (verified from the pipeline) | Model(s) | Output |
|---|---|---|---|---|
| **MRI** | image (PNG/JPG) | U‑Net: resize **256×256** RGB, per‑channel z‑score. Then a **bounding‑box crop** of the tumour region → Swin processor **224×224**, ImageNet norm | U‑Net → Swin‑T | mask + area + 4‑class type + confidence + Grad‑CAM peak |
| **ECG** | 12‑lead signal | per‑lead normalisation; **lead II** used for R‑peak/HRV (NeuroKit2); PTB‑XL is 500 Hz | 7× DenseNet‑1D‑121 | 7 independent probabilities + per‑pathology threshold decision + HRV + plot |
| **Echo** | video (.avi/.mp4) | OpenCV decode → RGB, resize **112×112**, EchoNet mean/std; EF over up to **4 clips of 32 frames** (stride 2), tensor `(3, 32, 112, 112)` | DeepLabV3‑ResNet50 + R(2+1)D‑18 | EF % (+ category) + LV mask at ED/ES |
| **EEG** | `.edf` | **16‑channel** longitudinal‑bipolar montage → resample **200 Hz** → **10 s = 2000‑sample** windows → per‑channel **95th‑percentile** amplitude normalisation | BIOT (STFT tokens) + IIIC head | per‑window 6‑class → aggregated proportions + dominant pattern + harmful flag |

**ECG decision thresholds** are per‑pathology and mode‑switchable via `ECG_THRESHOLD_MODE`:
**`f1`** (default, balanced) vs **`recall`** (opt‑in, screening — macro recall ≈ 0.98, lower precision).
Deployed `f1` thresholds: AFIB 0.91 · 1AVB 0.90 · STACH 0.92 · SBRAD 0.89 · RBBB 0.95 · LBBB 0.96 · PVC 0.96.

---

# PART J — METHODOLOGY & SCIENTIFIC RIGOUR (how the numbers were earned)

Say this explicitly — it is what separates "I ran a demo" from "I evaluated models like a scientist".

- **Public benchmark datasets only** (no clinical collaboration): PTB‑XL (21 837 × 12‑lead, 500 Hz),
  Kaggle Brain‑Tumor (~7 k images), LGG (3 929 slices + masks), EchoNet‑Dynamic (10 030 videos), Kaggle HMS.
- **No test‑set leakage.** ECG thresholds were tuned on **validation fold 9** and applied **unchanged** to
  **held‑out test fold 10**. EEG used a **patient‑level split** (no patient in both train and test).
- **No‑regression rule for fine‑tuning.** A fine‑tuned ECG checkpoint was kept **only if it beat the stock
  weights** on the target metric; otherwise the stock model was retained. This guarantees fine‑tuning can
  never make the deployed ensemble worse.
- **Local re‑verification of every Colab number.** Nothing trained on Colab is trusted until re‑run on this
  machine with the `tools/eval_*.py` harness; the reproduced numbers matched exactly.
- **Uncertainty quantified.** Bootstrap 95% CIs on all headlines + a permutation test for EEG
  significance — point estimates are never presented bare.
- **Calibration vs. retraining separated.** The ECG ROC‑AUC barely moved while macro F1 jumped 0.51 → 0.71,
  *proving* the gain was decision‑threshold calibration, not a different/over‑fit model.
- **Independent external check.** Because `ecglib` may have trained on a corpus overlapping PTB‑XL, ECG was
  also evaluated on **Chapman‑Shaoxing‑Ningbo** (a different hospital corpus) as an anti‑leakage test.

**Threats to validity (state them before the jury does):**
- *Internal:* possible ECG train/test overlap (mitigated by the external check); single‑split estimates (mitigated by CIs).
- *External:* validated on public benchmarks, not local clinical data — generalisation to other scanners/populations is unverified.
- *Construct:* EEG IIIC labels are **expert votes** with inherent disagreement (κ ≈ 0.5), which caps any 6‑class accuracy.
- *Design:* the multimodal combination is **rule‑based, not learned** — no paired multi‑modal dataset exists for this cohort.

---

# PART K — SECURITY, PRIVACY & ETHICS (medical data)

| Concern | What the platform does | Honest limitation |
|---|---|---|
| **Authentication** | Email‑based JWT (SimpleJWT), **1‑hour access / 7‑day refresh**; Axios intercepts 401 → re‑login | JWT stored in browser `localStorage` (XSS‑exposed) |
| **Multi‑doctor isolation** | Every queryset filters on the requesting doctor along `analysis → patient → doctor`; a foreign id returns **404**, not 403 (no existence leak) | — |
| **PHI / media access** | Result images, uploads, PDFs are served via an **HMAC‑signed, time‑limited** `/media/` view (`core/media.py`); the API never returns a raw `/media/` URL | A signed URL is **time‑scoped, not per‑identity** — anyone holding an unexpired URL can fetch it |
| **Abuse protection** | DRF scoped rate limits: login 10/min, register 5/min, refresh 30/min | — |
| **Data at rest / audit** | — | **No encryption at rest, no audit log** — flag as future work |
| **Clinical safety framing** | Outputs are **decision support**, not diagnosis; EEG is an explicit **sensitivity‑first screen** | A clinician must remain in the loop |

> Presentation tip: positioning the tool as **assistive decision‑support with a human in the loop** (not an
> autonomous diagnostician) is both the honest and the defensible framing for a medical jury.

---

# PART L — GLOSSARY (define every term you'll say)

**Tumour types (MRI):** *Glioma* — tumour from glial cells (often aggressive). *Meningioma* — tumour of the
meninges (usually benign). *Pituitary* — tumour of the pituitary gland. *No‑tumour* — healthy/abnormal‑free scan.

**ECG pathologies:** *AFIB* — atrial fibrillation (irregular rhythm). *1AVB* — first‑degree AV block (slowed
conduction). *STACH* — sinus tachycardia (fast). *SBRAD* — sinus bradycardia (slow). *RBBB / LBBB* — right /
left bundle‑branch block. *PVC* — premature ventricular contraction (extra beats).

**HRV metrics** (heart‑rate variability, from lead II; shown against reference ranges in the UI):
*RMSSD (ms)* — short‑term beat‑to‑beat variability (parasympathetic tone). *SDNN (ms)* — overall variability.
*pNN50 (%)* — proportion of successive beats differing > 50 ms. (Higher generally = healthier autonomic tone;
exact ranges are age‑dependent.)

**Echo:** *LV* — left ventricle. *EF (ejection fraction, %)* — fraction of blood the LV pumps per beat;
**< 50% reduced**, ~50–54% mildly reduced, ≥ 55% normal. *ED / ES* — end‑diastole / end‑systole frames.

**EEG (IIIC 6 classes):** *SZ* — seizure. *LPD / GPD* — lateralised / generalised periodic discharges.
*LRDA / GRDA* — lateralised / generalised rhythmic delta activity. *Other* — background. SZ/LPD/GPD = **harmful**.

**ML metrics:** *Dice / IoU* — overlap of predicted vs true mask (1 = perfect). *ROC‑AUC* — ranking quality,
threshold‑independent (1 = perfect, 0.5 = chance). *Sensitivity/Recall* — % of positives caught.
*Specificity* — % of negatives correctly cleared. *Precision* — % of positive calls that were right.
*F1* — harmonic mean of precision & recall. *Macro F1 / balanced accuracy* — averaged across classes
(fair under class imbalance). *Cohen's κ* — agreement above chance (0 = chance, 1 = perfect). *MAE / R²* —
mean absolute error / variance explained (regression, for EF).

---

# PART M — CONTRIBUTIONS, CHEAT SHEET & DEMO SCRIPT

## M.1 My contributions (claim these clearly)

**Engineering (the platform):**
1. Designed and built a full‑stack, **modular multimodal** platform (Django 3.2 + DRF + React 19) covering 4 medical modalities.
2. **Doctor‑isolation** security model + JWT auth + HMAC‑signed media URLs.
3. **Structured‑error envelope** contract → graceful partial results, the API never crashes.
4. **Lazy singleton model loader** (CPU‑compatible, GPU auto‑detected) — 4 model families behind one interface.
5. **MRI explainability** subsystem (Grad‑CAM + Captum SHAP) + a faithfulness harness.
6. **Combined PDF report** generator and a plug‑in recipe for new modalities.
7. **Cloud deployment** (Hugging Face Space + Vercel + MongoDB Atlas).

**Scientific (the models):**
8. **Rigorous local validation** of every model on held‑out data (no‑leakage splits, bootstrap CIs, permutation test).
9. **ECG threshold calibration** — macro F1 **0.51 → 0.71** with *no retraining* (proven via flat ROC‑AUC).
10. **MRI Swin fine‑tune** — **80.4% → 95.4%**.
11. **ECG fine‑tune** (6/7, no‑regression rule) — macro F1 → **0.777** (STACH F1 0.684 → 0.852).
12. **EEG IIIC head fine‑tune** (frozen → full) — balanced acc **0.278 → 0.379**, deployed as a sensitivity‑first screen.
13. **Diagnosed and fixed the U‑Net double‑sigmoid bug** — Dice **0.02 → 0.85**.
14. **External‑dataset leakage check** (Chapman‑Shaoxing‑Ningbo) for ECG.

## M.2 Key‑numbers cheat sheet (memorise these)

| | Number |
|---|---|
| Modalities / ECG pathologies / EEG classes / MRI classes | 4 / 7 / 6 / 4 |
| **MRI** accuracy (was → now) | 80.4% → **95.4%** · segmentation Dice **0.852** |
| **ECG** macro F1 (stock → calibrated → fine‑tuned) | 0.51 → 0.71 → **0.777** · ROC‑AUC **0.981** |
| **Echo** EF | MAE **4.01%** · R² **0.831** · LV Dice **0.897** |
| **EEG** harmful‑activity screen | balanced acc **0.379** (chance 0.167) · κ 0.352 · seizure recall **0.949** |
| First‑run weight download | ~700 MB · inference is **synchronous in‑request** |

## M.3 Live demo script (rehearse this order)

1. **Login** — `doctor@test.com` / `TestPass123!` (seed with `python tools/seed_database.py`).
2. **Dashboard** — show the patient list / history (proves doctor‑scoped data).
3. **Patient** — open or create one.
4. **MRI** — upload a sample → show the **segmentation overlay + 4‑class type + confidence**.
5. **Explain** — trigger `/explain/` → show the **Grad‑CAM + SHAP** overlays ("where the model looked").
6. **ECG** — upload a sample → show the **per‑pathology probability table + HRV + signal plot**.
7. *(If Echo/EEG weights are present)* run one and show EF / the EEG class distribution.
8. **Combined report** — generate the **PDF** and open it (segmentation + ECG + interpretation sections).
9. *(Optional, powerful)* log in as a **second doctor** → confirm the first doctor's patient is invisible (404).

> Fallback if the network/weights aren't ready on the day: pre‑capture screenshots/GIFs of steps 4–8 (the
> `SCREENSHOTS/` folder is a numbered checklist for exactly this) and narrate over them.

---

# APPENDIX — reproduce every number

```bash
# MRI
python tools/eval_mri_segmentation.py     # U‑Net Dice on LGG (validates the double‑sigmoid fix)
python tools/eval_mri_classifier.py       # 4‑class Swin accuracy (Kaggle brain‑tumor)
python tools/eval_mri_explainer.py        # Grad‑CAM↔SHAP faithfulness (agreement / localize / deletion)
# ECG
python tools/eval_ecg_classifier.py       # ecglib pathology models, PTB‑XL fold 10
python tools/eval_ecg_external.py         # external Chapman‑Shaoxing‑Ningbo (anti‑leakage)
# Echo
python tools/eval_echo.py                 # EchoNet EF / segmentation
# EEG
python tools/eval_eeg.py                  # BIOT/IIIC head (after placing biot_iiic.pt)
# Confidence intervals
python tools/bootstrap_cis.py             # 95% CIs + EEG permutation test on cached predictions
```

**Authoritative sources inside the repo:** `maybe read/VALIDATION.md` (every number + how it was
measured), `docs/PROJECT_FUNCTIONALITY_A_TO_Z.md` (full workflow + §8 source links), `README.md`
(architecture + tech stack), `Colab PFE/README.md` (fine‑tuning round‑trip), `Mazen_PFE/Problems of My
Project.md` (limitations). When any metric changes, re‑run the harness above and update VALIDATION.md.
