# Project Work — Mazen Ramoul — Architecture, Results, and Honest Self-Assessment

> **Multimodal Medical AI Platform for Cardiology & Oncology**
> Master's PFE (2025 / 2026) — Université Abdelhamid Mehri, Constantine 2
> Faculté des Nouvelles Technologies de l'Information et de la Communication
> Département : Informatique Fondamentale et ses Applications
>
> **Student:** Mazen Ramoul · `mazen.ramoul@univ-constantine2.dz`
> **Supervisor:** Prof. DERDOUR Makhlouf · **Co-supervisor:** Prof. TALBI Hichem
>
> This document is a complete walkthrough of the project written for the thesis defence.
> Every number and claim is traceable to the repository's own documents
> ([README.md](README.md), [VALIDATION.md](maybe%20read/VALIDATION.md),
> [Problems of My Project.md](Mazen_PFE/Problems%20of%20My%20Project.md),
> [My Project – The End.md](Mazen_PFE/My%20Project%20%E2%80%93%20The%20End.md),
> [Colab PFE/README.md](Colab%20PFE/README.md), and
> [EXTERNAL_ECG_EVAL.md](tools/EXTERNAL_ECG_EVAL.md)). It is organised in the six parts you asked for.

---

## Table of contents

1. [How the project works — the architecture](#1-how-the-project-works--the-architecture)
2. [All the results — what they originally were and how they changed](#2-all-the-results--what-they-originally-were-and-how-they-changed)
3. [What I focused on (recall) and what I deliberately did not focus on](#3-what-i-focused-on-recall-and-what-i-deliberately-did-not-focus-on)
4. [Source-site results vs. my results — every possible comparison](#4-source-site-results-vs-my-results--every-possible-comparison)
5. [The value of my work](#5-the-value-of-my-work)
6. [Where I fell short — mistakes, conflicts, missing elements](#6-where-i-fell-short--mistakes-conflicts-missing-elements)

---

## 1. How the project works — the architecture

### 1.1 The idea in one paragraph

Hospitals analyse the brain and the heart with separate, disconnected tools. This project puts **four AI modalities in one web application**: a doctor logs in, registers a patient, uploads a medical file (brain MRI, 12-lead ECG, echocardiogram video, or EEG recording), and the platform runs a pre-trained deep-learning model on it **immediately, in the same request — no waiting queue**, saves the result to the patient's record, and can generate a **single combined PDF report** with a rule-based clinical interpretation. The technical contribution is **not the models themselves** (they are open, peer-reviewed components) but the **architecture that integrates them** into one doctor-scoped workflow.

### 1.2 Three-tier architecture

```
                 Doctor's browser
                       │  JWT bearer token on every request
                       ▼
   ┌─────────────────────────────────────────────┐
   │  FRONTEND — React 19 + Vite (port 3000)      │
   │  TailwindCSS UI · Redux Toolkit state        │
   │  Axios (auto-attaches JWT, 401 → /login)     │
   │  react-router-dom 6 · Three.js 3D scenes     │
   └──────────────────────┬───────────────────────┘
                          │  REST  /api/*
                          ▼
   ┌─────────────────────────────────────────────┐
   │  BACKEND — Django 3.2 LTS + DRF (port 8000)  │
   │  apps/authentication  email login, JWT       │
   │  apps/patients        doctor-scoped CRUD     │
   │  apps/mri             upload + inference      │
   │  apps/ecg             upload + inference      │
   │  apps/echo            upload + inference      │
   │  apps/eeg             upload + inference      │
   │  apps/reports         combined PDF            │
   │  apps/inference  ◄── the "brain":            │
   │     lazy-singleton model loader + 4 pipelines │
   └──────────┬───────────────────┬────────────────┘
              │                   │
              ▼                   ▼
   ┌──────────────────┐   ┌──────────────────────┐
   │  MongoDB          │   │  media/ filesystem    │
   │  (via djongo)     │   │  uploads, masks,      │
   │  users, patients, │   │  overlays, plots,     │
   │  analysis records │   │  PDF reports          │
   └──────────────────┘   └──────────────────────┘
```

**Three tiers:** React in the browser → Django REST API → MongoDB + media filesystem.

### 1.3 The technology stack

| Layer | Technology | Version | Why this choice |
|---|---|---|---|
| Backend framework | Django + DRF | 3.2.25 LTS / 3.14.0 | Mature REST stack; **3.2 forced by djongo** (see §6) |
| Authentication | SimpleJWT | 5.3.1 | Email-login JWT, 60-min access / 7-day refresh |
| Database | MongoDB via djongo | 7.x / 1.3.6 | Document store for flexible analysis records |
| Inference framework | PyTorch + transformers | 2.2.0 / 4.38.0 | Run the pre-trained models |
| ECG models | ecglib (ISPRAS) | 1.0.1 (exact pin) | Pre-trained 12-lead pathology classifiers |
| Signal processing | NeuroKit2, SciPy | 0.2.7 / 1.11.4 | Classical, validated HRV/DSP |
| EEG model / I/O | BIOT (vendored), MNE, edfio | — / 1.12 / 0.4 | Biosignal transformer + .edf parsing |
| PDF generation | ReportLab | 4.0.9 | Programmatic combined report |
| Frontend | React + Vite | 19 / 8 | Modern SPA, fast dev server |
| Styling / state | TailwindCSS / Redux Toolkit | 3.4 / 2 | Utility CSS, predictable state |

### 1.4 The journey, A to Z

| Step | What happens | Where |
|---|---|---|
| **A. Register / Login** | Doctor signs up with email + password → JWT access (60 min) + refresh (7 days). | `apps/authentication`, `/api/auth/` |
| **B. Add a patient** | Name, age, sex, notes. The patient belongs to *this* doctor only. | `apps/patients`, `/api/patients/` |
| **C. Upload a file** | MRI image, ECG (CSV/EDF/WFDB), echo video, or EEG (.edf), drag-and-drop. | frontend modules → `/api/<modality>/upload/` |
| **D. Inference runs synchronously** | The view calls the pipeline **in the same request**. First call ever downloads ~700 MB of MRI/ECG weights to local cache; thereafter fast. | `apps/inference` |
| **E. Result saved + displayed** | Diagnosis, probabilities, and generated images (mask overlay, ECG plot, EF segmentation…) stored on the record and rendered in the UI. | MongoDB + `media/` |
| **F. Patient history** | One endpoint aggregates all analyses across all modalities. | `/api/patients/<id>/history/` |
| **G. PDF report** | ReportLab builds one document with every modality's findings + a combined rule-based interpretation. **The PDF survives even if the patient is later deleted** (null FK). | `apps/reports`, `/api/reports/` |

### 1.5 The inference engine — three design contracts worth defending

The heart of the platform is `apps/inference`, which holds the model loader plus the four pipelines. Three deliberate design choices define its behaviour:

1. **Lazy singleton loader.** Models load **once, on first use**, and stay resident in memory (~3 GB for the ViT + ecglib ensemble). Echo and EEG weights are *deliberately not bundled* (license/size); the loader raises a **clear `FileNotFoundError` with instructions** rather than crashing. `warmup()` pre-loads only MRI + ECG, never Echo/EEG, for this reason.

2. **Result-envelope contract.** Every pipeline returns a plain dict shaped `{status, ...result_fields, error?, error_type?}` and **never raises into the view**. Structured failure is part of the contract, so the API can report **partial results** (e.g. ECG still answers if some sub-models are missing). This is why a fresh checkout that lacks Echo/EEG weights fails *honestly*, not as a 500 crash.

3. **Doctor isolation.** Every queryset in `patients`, `mri`, `ecg`, `echo`, `reports` filters by the requesting doctor. The FK chain is `<Analysis> → patient → doctor`. An endpoint that returns another doctor's data is a bug, not a feature.

### 1.6 The four modalities and the models behind them

| Modality | Model(s) | Architecture | Output |
|---|---|---|---|
| **MRI** | U-Net (`mateuszbuda/brain-segmentation-pytorch`, torch.hub, ~7.7 M params) + ViT-B/16 4-class classifier (`Devarshi/Brain_Tumor_Classification`, HuggingFace, ~86 M) | CNN encoder-decoder + Vision Transformer | Tumour mask + overlay; type (glioma / meningioma / notumor / pituitary) |
| **ECG** | ecglib DenseNet-1D-121 ×7 (~8 M each) + NeuroKit2 (classical) | 1D deep CNN ensemble + rule-based DSP | Per-pathology probability (AFIB, 1AVB, STACH, SBRAD, RBBB, LBBB, PVC) + HRV metrics (RMSSD, SDNN, pNN50) |
| **Echo** | EchoNet-Dynamic: DeepLabV3-ResNet50 (~40 M) + R(2+1)D-18 (~31 M) | 2D segmentation + 3D spatiotemporal CNN | LV segmentation + ejection-fraction regression with clinical category |
| **EEG** | BIOT (vendored, ~3 M) — pretrained encoder + IIIC head fine-tuned in-repo | Linear-attention transformer over STFT tokens | 6-class harmful-brain-activity screening (SZ, LPD, GPD, LRDA, GRDA, Other) |

### 1.7 Why the design is extensible (the main architectural contribution)

The platform is **modality-agnostic**. Each medical domain is an isolated plug-in: **one inference pipeline + one Django app + one frontend module + one report section**. Adding CT, genomics, or any new domain tomorrow follows an 8-step recipe **without touching any existing modality's code** or the authentication core. That plug-in architecture — not the borrowed models — is the principal engineering contribution.

---

## 2. All the results — what they originally were and how they changed

All models were validated on **held-out public datasets** with reproducible harnesses in `tools/eval_*.py`. This section gives the full before/after trail.

### 2.1 The two bugs found and fixed during validation

These two fixes are the clearest "original → changed" story, because they turned broken outputs into working ones with **no retraining**:

| Fix | Original behaviour | Root cause | After fix |
|---|---|---|---|
| **MRI segmentation double-sigmoid** | Dice **≈ 0.02** — the mask saturated (~100% of every image flagged), which the saturation guard then suppressed to `tumor_detected: false`. | The `mateuszbuda` U-Net applies `sigmoid` *inside* its `forward()`; the pipeline applied `torch.sigmoid()` **again**, squashing [0,1] into [0.5, 0.73] so every pixel crossed the 0.5 threshold. | **Dice 0.85** on LGG tumour slices (IoU 0.78). Removing the redundant sigmoid restored the model. |
| **ECG flat decision threshold** | Macro F1 **0.51** (stock) — a flat `prob > 0.5` cut-off over-flagged badly. | One global threshold ignored per-pathology calibration. | Macro F1 **0.71** (stock) — per-pathology thresholds tuned on the validation fold (fold 9), applied unchanged to test fold 10 (**no leakage**). ROC-AUC unchanged, confirming the gain is calibration, not a different model. |

### 2.2 MRI classification (ViT, 4-class) — fine-tuned 80.4 % → 95.4 %

**Dataset:** Kaggle "Brain Tumor MRI" (Nickparvar), held-out `Testing/` split, **1,600 images** (400/class). Evaluated on the full image (the Kaggle set ships no masks).

| Metric | **Stock hub model (original)** | **Fine-tuned (deployed, June 2026)** |
|---|---|---|
| Accuracy | 80.4 % (1286/1600) | **95.4 %** (1527/1600) |
| Macro F1 | 0.794 | **0.954** |
| Mean confidence | 0.890 | 0.990 |

Per-class recall moved as follows (the fine-tune fixed the worst classes):

| Class | Stock recall | Fine-tuned recall |
|---|---:|---:|
| glioma | 0.517 | 0.833 |
| meningioma | 0.698 | 0.990 |
| notumor | 1.000 | 1.000 |
| pituitary | 1.000 | 0.995 |

The stock model's weakness was **glioma (recall 0.52)** — 109 gliomas and 105 meningiomas were misclassified as pituitary. After a 6-epoch continue-train on the `Training/` split (Colab T4, `colab_mri_vit_finetune.ipynb`), the pituitary confusion is gone; the **only remaining weakness is glioma recall (0.83)** — 48 gliomas still read as meningioma, a clinically related (both-are-tumours) distinction. The result was **re-verified locally** on the full 1,600-image split, confusion matrix identical to the Colab run.

### 2.3 MRI segmentation (U-Net) — Dice 0.02 → 0.85

**Dataset:** LGG MRI Segmentation, 3,929 slices (1,373 tumour-positive). After the double-sigmoid fix:

| Metric | All slices | Tumour-positive slices |
|---|---:|---:|
| Dice | 0.827 | **0.852** |
| IoU (Jaccard) | 0.802 | 0.781 |
| Saturated predictions | 0 % | — |

### 2.4 ECG (7 pathologies) — threshold calibration + 3/7 fine-tuned

**Dataset:** PTB-XL fold 10 (2,198 records); thresholds tuned on fold 9.

The "original → changed" story here has **two layers**:

**Layer 1 — threshold calibration (no retraining):**

| Average | Before (flat 0.5) | After (tuned) |
|---|---:|---:|
| Macro F1 (stock models) | 0.514 | 0.711 |
| Macro F1 (fine-tuned ensemble) | 0.544 | **0.727** |

**Layer 2 — per-pathology fine-tune (Colab T4, June 2026), kept under a no-regression rule (3 of 7 beat baseline):**

| Pathology | Stock F1 | Fine-tuned F1 | Kept? |
|---|---:|---:|---|
| 1AVB | 0.521 | **0.606** | ✅ (headline win: +0.085) |
| RBBB | 0.844 | **0.864** | ✅ (+0.020) |
| PVC | 0.821 | **0.828** | ✅ (+0.007) |
| AFIB, STACH, SBRAD, LBBB | — | did not beat baseline | ✗ kept stock |

**Aggregate (fine-tuned ensemble; stock in parentheses):** mean ROC-AUC **0.980** (0.978), macro F1 **0.727** (0.711), macro balanced accuracy **0.887** (0.884). The Colab AUCs reproduced **exactly** when re-verified locally on June 11 2026 (1AVB 0.972, RBBB 0.995, PVC 0.993).

### 2.5 Echo (EchoNet-Dynamic) — matches the published paper

**Dataset:** EchoNet-Dynamic TEST split. The headline is the **400-video** figure (an earlier 40-video subset gave a more flattering 3.19 % MAE, shown only for transparency).

| Metric | 400 videos (headline) | 40-video subset |
|---|---:|---:|
| EF MAE | **4.01 %** | 3.19 % |
| EF RMSE | 5.30 % | 4.01 % |
| EF R² | **0.831** | 0.860 |
| LV segmentation Dice | **0.897** (30 traced ED/ES frames) | — |

These were **used as released** (no fine-tuning) and match published EchoNet performance, confirming the pretrained models run correctly in the pipeline.

### 2.6 EEG (BIOT/IIIC, 6-class) — honest-but-modest 0.278

**Dataset:** Kaggle HMS, patient-disjoint split (6,814 train / 1,883 test). The encoder is **frozen**; only the 6-class head was trained on CPU on a 1,451-EEG subset.

| Metric | Value | Reference |
|---|---|---|
| Balanced accuracy | **0.278** | 0.167 = 6-class chance |
| Cohen's κ | **0.147** | 0 = chance agreement |
| Macro F1 | 0.265 | — |
| KL divergence (vs true votes) | 1.333 | lower is better |

**The key finding:** a 3.7× larger training set (an earlier 396-EEG run scored 0.31 on only 303 windows) did **not** move the headline — it converged to ~0.28. That is the signature of a **frozen-encoder ceiling**: a tiny linear head on fixed features plateaus regardless of data volume. The real lever is a GPU full fine-tune (unfreeze the encoder), the documented next step.

### 2.7 The safety-first recalibration (June 2026) — original F1 points → recall points

Per supervisor guidance that the platform must never produce a false negative, every model was re-calibrated for **high recall**. Crucially this is a **decision-threshold/rule change, not retraining — no GPU was needed for ECG/MRI/Echo**. Each row shows what the operating point became:

| Model | "Don't-miss" recall | False negatives | Precision cost |
|---|---|---|---|
| ECG (7 pathologies) | all ≥ 0.95, macro **0.982** | **13** / 2,198 (was ~62 at F1 thresholds) | macro 0.69 → 0.35 |
| MRI (tumour vs healthy) | **0.998** (1.000 in zero-miss mode) | **2** / 1,200 (0 in zero-miss) | 2–17 / 400 healthy flagged |
| EEG (abnormal screen) | seizures routed **0.966** ✓; general abnormal **0.931** | 128 / 1,850 windows | specificity ≈ 0 |
| Echo (reduced EF) | **0.952** (flag EF < 55 %) | **4** / 83 reduced (was 18 at no margin) | precision 0.88 → 0.68 |

ECG ships **both** operating points (`ECG_THRESHOLD_MODE=recall` default, `=f1` switchable).

---

## 3. What I focused on (recall) and what I deliberately did not focus on

### 3.1 The clinical posture: recall first

The whole platform runs a **recall-first / screening operating point by default**. The governing principle (stated by the supervisor and encoded across all four pipelines):

> A screening tool must **never silently clear a sick patient**. A false negative (telling a sick patient they are fine) is far costlier than a false positive (an extra human review). False alarms route to a human; missed disease does not.

This is why **low precision and liberal flagging are deliberate, not miscalibration**. Concretely, what I tuned *for*:

- **ECG** — recall-first thresholds: every pathology recall ≥ 0.95 on the held-out fold (macro recall 0.982), at the cost of macro precision ~0.35 (≈1,708 false positives, but only **13** false negatives in 2,198 records).
- **MRI** — a `notumor` verdict is accepted **only** when ViT confidence ≥ 0.99 **and** the U-Net found no tissue; otherwise the pipeline returns `screening_flag: possible_tumor_review`. This lifts tumour-detection recall 0.983 → 0.998.
- **Echo** — flags EF < 55 % (a +5 % safety margin over the 50 % clinical cutoff) so the regressor's ~4–5 % error doesn't miss borderline reduced-EF cases. Recall 0.783 → 0.952.
- **EEG** — reports `screen_positive` when **any** IIIC pattern appears; seizure-routing recall 0.966. It is a **routing signal, never a rule-out**.

### 3.2 What I deliberately did **not** optimise for

| Not prioritised | Why | Consequence (accepted on purpose) |
|---|---|---|
| **Precision** | Screening trades precision for recall by design. | Many false positives go to human review — the safe direction. |
| **EEG 6-way *type* accuracy** | IIIC is inter-rater-ambiguous (expert κ ≈ 0.5); 0.95 *type* recall is unreachable **by anyone**, not just this model. | EEG is presented as a screen, not a diagnostic classifier. |
| **A learned multimodal fusion** | The "combined interpretation" is rule-based template text, not a measured neuro-cardiac correlation. | The fusion is presentation-level; the correlation hypothesis is future work. |
| **Validation on a clinical cohort** | No paired prospective patient data exists in this project. | All numbers are on public benchmarks; real-world performance is unproven. |
| **EEG full GPU fine-tune** | CPU-only environment; the head was trained with the encoder frozen. | EEG accuracy stays at the frozen-encoder ceiling (~0.28). |
| **Plain "accuracy" headlines on ECG** | Under class imbalance an all-negative predictor scores 95–99 %. | Reported balanced accuracy / AUC / F1 / sensitivity / specificity instead. |

### 3.3 The honest exception within the recall story

Three of four modalities clear the ≥ 0.95 don't-miss bar with no GPU. **EEG is the exception:** its seizure-routing (0.966) clears the bar, but the *general* abnormal-vs-benign screen (0.931) falls just short, because the frozen head has essentially **no benign specificity** (Other recall 0.000 — it gets 0/33 true-`Other` windows right). Reaching ≥ 0.95 general-screen recall would require either flagging essentially everything (no filtering value) or the GPU full fine-tune. I report this gap openly rather than papering over it.

---

## 4. Source-site results vs. my results — every possible comparison

All models start from weights **pre-trained by their original authors** (none from scratch). This section compares my measured numbers against the source papers/sites, and against my own before/after.

### 4.1 Per-modality comparison table

| Modality | Source site / paper | Source-reported result | My result (this platform) | Verdict |
|---|---|---|---|---|
| **MRI U-Net seg** | `mateuszbuda/brain-segmentation-pytorch`; Buda et al. 2019 (TCGA-LGG) | mean DSC ≈ **0.89** (per-volume) | **Dice 0.852** on LGG tumour slices (per-image) | Within a few points; gap is per-image vs per-volume normalisation, not missing training. |
| **MRI ViT classifier** | `Devarshi/Brain_Tumor_Classification` (HuggingFace model card) | card headline ≈ **99 %** | stock **80.4 %** → fine-tuned **95.4 %** | The 99 % card number does not reproduce on the full image with my preprocessing; my fine-tune closed most of the gap **under apples-to-apples conditions**. |
| **ECG ensemble** | `ecglib` (ISPRAS); Avetisyan et al. 2023 (500k+ records) | strong multi-label AUC on its own corpus | mean ROC-AUC **0.980**, macro F1 **0.727** on PTB-XL fold 10 | Matches expectations — **but** ecglib's corpus is unpublished and may include PTB-XL (leakage caveat, §4.2). |
| **Echo EF + LV** | EchoNet-Dynamic (Stanford); Ouyang et al. *Nature* 2020 | EF MAE ≈ **4 %**, Dice ≈ **0.92** | EF MAE **4.01 %**, Dice **0.897** | Essentially matches the published paper — confirms correct integration. |
| **EEG BIOT/IIIC** | `ycq091044/BIOT`; Yang et al. NeurIPS 2023 | full-data fine-tune ≈ **0.5** balanced acc | frozen-head **0.278** balanced acc | Below BIOT's full-data level **because** I froze the encoder; the documented GPU path targets 0.45–0.55 (matching the authors). |

### 4.2 The ECG leakage check — the one comparison that needs an independent site

Because `ecglib`'s 500k+ training corpus is unpublished and **may include PTB-XL**, the ~0.98 AUC on PTB-XL could be optimistic. The documented, reproducible anti-leakage procedure ([EXTERNAL_ECG_EVAL.md](tools/EXTERNAL_ECG_EVAL.md)) re-evaluates the **frozen** ecglib ensemble on an **independent** dataset:

- **Independent dataset:** Chapman-Shaoxing-Ningbo (PhysioNet `ecg-arrhythmia`, SNOMED-CT labelled, independent of PTB-XL).
- **Metric to quote:** macro AUC (threshold-independent → measures genuine generalisation).
- **Script:** `tools/eval_ecg_external.py` (streaming or full-local mode); no retraining.
- **Reading the outcome:** if AUC stays ≈ 0.95+, the PTB-XL number is **vindicated**; if it drops, the optimism is **honestly quantified** — either way is good science.

> ⚠ Important caveat for the defence: the *June 2026 ECG fine-tune deliberately trains on PTB-XL folds 1–8*. That is **disclosed, fold-separated, and leakage-free by construction** — distinct from the *possible* ecglib-corpus leakage, which is the thing the external check rules out.

### 4.3 The "two macro-F1 numbers" reconciliation (a real conflict, resolved)

The Colab ECG fine-tune notebook reports macro F1 ≈ 0.57 → 0.60, *lower* than the 0.711/0.727 in VALIDATION.md. **This is not a contradiction:** the notebook tunes thresholds to maximise **balanced accuracy** (its model-selection metric), while the deployed pipeline and report tune thresholds to maximise **F1**. Same models, same fold-10 records, different threshold objective. Under the notebook's balanced-accuracy objective the same ensemble scores macro balanced-acc 0.946.

### 4.4 Datasets / sites used (full provenance)

| Modality | Weights origin (site) | Validation dataset (site) | Trained by me? |
|---|---|---|---|
| MRI U-Net | torch.hub — mateuszbuda | TCGA-LGG (Kaggle) | No (as released) |
| MRI ViT | HuggingFace — Devarshi (base: Google ViT-B/16) | Kaggle Brain-Tumor (Nickparvar) | **Yes — Colab T4, 80.4 → 95.4 %** |
| ECG ×7 | ecglib — ISPRAS (PyPI) | PTB-XL fold 10 (PhysioNet) + Chapman-Shaoxing-Ningbo (external) | **Partly — 3/7 fine-tuned + all thresholds calibrated** |
| Echo (2 models) | Stanford EchoNet-Dynamic | EchoNet-Dynamic TEST | No (as released) |
| EEG encoder | BIOT authors (`ycq091044/BIOT`) | — | No (frozen) |
| **EEG IIIC head** | **this repo** (`tools/train_eeg_head.py`) | Kaggle HMS | **Yes — fine-tuned, encoder frozen** |

---

## 5. The value of my work

### 5.1 The architecture is the contribution

The models are borrowed and peer-reviewed; the **value is the system that integrates them**:

- **A modality-agnostic plug-in architecture** — four AI domains (MRI, ECG, Echo, EEG) in one doctor-scoped workflow, where a fifth domain plugs in via an 8-step recipe **without touching existing code**. This is the principal architectural contribution.
- **A typed REST API with strict doctor isolation** — every queryset filters by the owning doctor; the FK chain `analysis → patient → doctor` is enforced everywhere.
- **A robust failure contract** — pipelines return structured `{status, …, error?}` envelopes and never crash the API, enabling partial results and honest "weights not present" failures.
- **A combined PDF report** that aggregates any subset of completed analyses and survives patient deletion.

### 5.2 Concrete engineering wins (measured, reproducible, no-GPU)

| Contribution | Impact | Cost |
|---|---|---|
| **ECG threshold calibration** | Macro F1 0.51 → 0.71 (stock), 0.54 → 0.73 (fine-tuned) | **Zero retraining** — pure calibration on the validation fold |
| **MRI double-sigmoid fix** | Dice 0.02 → 0.85 | A one-line bug fix found via systematic validation |
| **Safety-first recalibration** | ECG/MRI/Echo all clear ≥ 0.95 don't-miss recall | **No GPU** — decision-rule change only; precision is the tracked cost |
| **MRI ViT fine-tune** | 80.4 % → 95.4 % accuracy | One Colab T4 session, re-verified locally |
| **ECG 3/7 fine-tune** | macro F1 0.711 → 0.727, under a no-regression rule | One Colab T4 session, re-verified locally |
| **EEG IIIC head** | Built the head BIOT never released; 0.278 (above 0.167 chance) | CPU, frozen encoder — a working pipeline awaiting GPU |

### 5.3 Honest, reproducible validation methodology

Every headline number has a **reproduce command** in `tools/eval_*.py` and is documented in VALIDATION.md with per-class metrics and confusion matrices. Colab results were never trusted blindly — each was **re-verified locally** on the same harness before being written into the docs. The project reports **balanced accuracy / AUC / F1** under class imbalance rather than inflated plain accuracy, and explicitly keeps both the stock baseline and the fine-tuned result side by side. This methodological honesty — including a documented anti-leakage external check — is itself a defensible contribution.

### 5.4 Strongest parts (for the defence)

- **ECG** — AUC 0.980 + macro F1 0.727 + external leakage check + the threshold-calibration contribution.
- **MRI classification** — 95.4 % after fine-tune (from a non-reproducing 99 % card to a verified number under real conditions).
- **Echo** — matches the published EchoNet-Dynamic paper.
- **The plug-in modality architecture** and the **honest, reproducible validation**.

---

## 6. Where I fell short — mistakes, conflicts, missing elements

This section is deliberately exhaustive. Knowing these is a strength at the defence, not a weakness.

### 6.1 Bugs I made (and fixed)

| Bug | What went wrong | How it was caught / fixed |
|---|---|---|
| **MRI double-sigmoid** | Applied `torch.sigmoid()` to a U-Net output that was *already* a sigmoid probability map → masks saturated → segmentation looked dead (Dice 0.02). | Found during validation; removing the redundant sigmoid restored Dice to 0.85. The saturation guard remains as a harmless safety net. |
| **ECG flat 0.5 threshold** | A single global threshold over-flagged badly (macro F1 0.51). | Replaced with per-pathology thresholds tuned on the validation fold (macro F1 0.71). |

### 6.2 A real process mistake (housekeeping / Git)

- **The Git repository root was `E:\MASTER`, not `medical-platform/`** — the repo was initialised one level *above* the project, had zero commits, and no remote. Pushed as-is, GitHub would **ignore `.github/workflows/ci.yml`** (it must sit at the repo root). The documented fix is to re-init / publish `medical-platform/` itself as the repository root before publishing. *(Discovered during the June 2026 fix sweep; flagged, not yet resolved at the time of writing.)*
- **The development disk (E:) was essentially full** — it broke a Git operation mid-write at one point. A 2.5 GB backup zip was removed to free ~3 GB; moving `data/hms` (1.6 GB) off E: is still advised.

### 6.3 Scientific shortfalls (the most important)

| # | Shortfall | Why it matters |
|---|---|---|
| 1 | **EEG accuracy is modest (0.278 balanced acc).** Frozen encoder, CPU, 1,451-EEG subset. | The weakest modality — it screens, it does not diagnose. The fix needs a GPU full fine-tune. |
| 2 | **MRI segmentation and classification use *different* datasets** (U-Net on LGG, ViT on Kaggle Brain-Tumor — different MRI modalities). | A single uploaded image is **not** validated end-to-end through both tasks; the two models can **disagree on the same input**. *(A "models_agree / uncertain" verdict + PDF caution is now implemented; common-dataset validation is still open.)* |
| 3 | **Possible ECG data leakage** — ecglib's unpublished corpus may include PTB-XL, so ~0.98 AUC could be optimistic. | The headline ECG number might be inflated; the external Chapman-Shaoxing-Ningbo check exists precisely to quantify this. |
| 4 | **ECG thresholds are calibrated for PTB-XL-like data only.** | They will mis-fire on a different recorder/population; per-site re-tuning (ideally learned calibration) is needed. |
| 5 | **Only 7 ECG pathologies, not a full diagnostic panel.** | Coverage is partial by design (what ecglib pretrained). |
| 6 | **The "combined interpretation" is rule-based template text, not a learned neuro-cardiac correlation.** | The multimodal "fusion" is presentation-level, not data-driven — the project's principal scientific gap and future work. |
| 7 | **Validated on public benchmarks, never on a clinical cohort.** | No evidence of real-world prospective performance yet. |

### 6.4 Engineering debt / shortfalls

| # | Shortfall | Status |
|---|---|---|
| 1 | **Inference is synchronous in the request thread** — no Celery/RQ queue; a slow model blocks the HTTP worker; two simultaneous uploads queue on one worker. | Open (deliberate for a demo; documented architecture decision). |
| 2 | **Stuck on Django 3.2 LTS + Python 3.10/3.11 because of djongo 1.3.6.** The build spec asked for Django 4.2; djongo forced the downgrade. Django 3.2 support has ended and djongo is barely maintained. | Open (big migration; replace djongo to upgrade). |
| 3 | **No Jest / no Python linter.** | Partially fixed — ESLint 9 + GitHub Actions CI (check/compileall/lint/build) added June 2026; Jest + ruff still TODO. |
| 4 | **`docker-compose.yml` is explicitly NOT tested end-to-end.** | Open — finish-and-test or remove to avoid over-claiming. |
| 5 | **Fragile local coupling** — frontend hard-pinned to port 3000 (`strictPort`), backend CORS pinned to the same; JWT in `localStorage` (XSS-readable). | Partially fixed — DRF auth throttling added (login 10/min, register 5/min, refresh 30/min); httpOnly-cookie tokens + single-place port config still open. |
| 6 | **Heavy first run** — ~700 MB MRI/ECG weights download on first call; Echo/EEG weights not bundled at all. | Fixed — `tools/download_weights.py` (`--check-only` status; default pre-warms MRI+ECG, prints Echo/EEG steps). |
| 7 | **djongo handles the test DB awkwardly** — `APITestCase` runs sometimes refuse to create the test DB; only the no-DB pipeline tests are reliable daily. | Open (same root fix as #2). |

### 6.5 Security / ethics gaps (must disclose)

- **PHI exposure:** result images and uploads are served from `/media/` **without authentication**, bypassing the per-doctor access control enforced in the API — a real medical-data-protection gap.
- **No GDPR controls:** no consent capture, no pseudonymisation, no retention-expiry, no access audit log. JWT stored in browser `localStorage`; no encryption at rest. These are noted as **future work, not claimed as delivered**. The platform is explicitly a **research/educational prototype, not a certified medical device**.

### 6.6 Conflicts / things that *look* like bugs but are not

| Apparent conflict | Resolution |
|---|---|
| Colab ECG macro F1 (≈0.57–0.60) vs VALIDATION.md (0.711/0.727) | Different threshold objective (balanced-acc vs F1) on the same models/fold — not a contradiction (§4.3). |
| Echo 40-video MAE 3.19 % vs 400-video 4.01 % | The 400-video figure is the headline; 3.19 % is small-sample optimism kept only for transparency. |
| EEG 396-EEG 0.31 vs 1,451-EEG 0.278 | The larger run is more reliable; the earlier higher number was 303-window small-sample optimism — and the convergence proves the frozen-encoder ceiling. |
| ecglib startup warning about IRBBB/CRBBB | Those codes don't exist in ecglib 1.0.1; the loader requests RBBB/LBBB instead, so all 7 pathologies load 7/7. Not a failure. |
| Echo/EEG endpoint "weights not found" on fresh checkout | By design — weights are not bundled; the loader fails honestly with a clear error rather than serving an untrained model. |

### 6.7 The honest one-line summary for the defence

- **Strongest:** ECG (AUC 0.980, F1 0.727, leakage check, calibration contribution), MRI classification (95.4 %), Echo (matches the paper), the plug-in architecture, and the reproducible validation.
- **Weakest:** EEG (0.278 balanced acc, frozen encoder, CPU) — present it as a **working pipeline whose model needs a GPU fine-tune**, not a finished classifier.
- **Biggest structural debt:** djongo (freezes Django + Python versions) and synchronous inference (blocks scaling).
- **Biggest scientific gap:** the multimodal combination is presentational, not learned — closing it needs a paired clinical dataset, the natural continuation of this PFE.

---

*Compiled from the repository's own documentation. All figures are reproducible via the `tools/eval_*.py` harnesses and cross-referenced in [VALIDATION.md](maybe%20read/VALIDATION.md). This is a research/educational prototype — not a certified medical device, not for clinical use.*
