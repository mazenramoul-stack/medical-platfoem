# Project Functionality: From A to Z

> Thesis section draft for the PFE report. Formal academic / IEEE style.
> Citation placeholders `[n]` map to the reference list in `README.md`.
> All quantitative results are taken verbatim from `VALIDATION.md` — no result is invented.

---

## 1. Overview

This section describes, end to end, how the proposed multimodal clinical
decision-support platform operates — from the moment a clinician authenticates
to the moment a combined, explainable PDF report is produced. The platform
ingests four independent classes of medical data — brain Magnetic Resonance
Imaging (MRI), 12-lead Electrocardiogram (ECG), Echocardiography (ECHO) video,
and Electroencephalography (EEG) — runs a dedicated deep-learning pipeline on
each, and aggregates the per-modality findings into a single document. A central
methodological statement frames everything that follows: the four pipelines are
**independent**, and the "combined interpretation" is **rule-based template
text**, not a learned cross-modal correlation. The neuro-cardiac coupling that
motivates the multimodal design is stated as a hypothesis and future work, not as
a measured result [11], [13].

---

## 2. Project Architecture

### 2.1 Architectural style

The system follows a **three-tier, layered client–server architecture** with a
**modular, plug-in inference layer**:

1. **Presentation tier** — a single-page React 19 application (Vite, TailwindCSS,
   Redux Toolkit) running in the clinician's browser.
2. **Application / service tier** — a Django 3.2 + Django REST Framework (DRF)
   backend exposing a typed REST API secured with JSON Web Tokens (SimpleJWT).
   This tier contains the modality apps and the **inference engine**, a lazily
   instantiated singleton that holds the deep-learning models in memory.
3. **Data tier** — a MongoDB database (accessed through the `djongo` object–
   document mapper) for structured records, plus a filesystem media store for
   uploaded inputs and generated artefacts (masks, overlays, plots, PDFs).

The design is deliberately **modality-agnostic**: each medical domain is an
isolated module (a backend Django app + an inference pipeline + a frontend
module), so a new domain (e.g., CT or genomics) can be added without modifying
existing modality code. Inference is **synchronous within the request thread**
(there is no Celery/RQ task queue); this is a documented simplification with
direct implications for scalability (Section 7).

### 2.2 Architecture diagram (text description — *insert Figure 1 here*)

```
┌──────────────────────────────────────────────────────────────┐
│  PRESENTATION TIER — Browser (clinician)                      │
│  React 19 · Vite · TailwindCSS · Redux Toolkit · Axios        │
│  Modules: Auth · Dashboard · Patients · MRI · ECG · Echo ·    │
│           EEG · Reports                                       │
└───────────────────────────┬──────────────────────────────────┘
                            │  HTTPS  —  REST /api/*  (JWT bearer)
┌───────────────────────────▼──────────────────────────────────┐
│  APPLICATION TIER — Django 3.2 + DRF + SimpleJWT              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Modality apps (thin views): authentication · patients · │  │
│  │ mri · ecg · echo · eeg · reports                        │  │
│  └───────────────────────────┬────────────────────────────┘  │
│  ┌───────────────────────────▼────────────────────────────┐  │
│  │ INFERENCE ENGINE  (apps/inference — lazy singleton)     │  │
│  │   • MRI  : U-Net (seg) + ViT-B/16 (4-class)             │  │
│  │   • ECG  : DenseNet-1D-121 ×7 + NeuroKit2 (HRV)         │  │
│  │   • ECHO : DeepLabV3-R50 (seg) + R(2+1)D-18 (EF)        │  │
│  │   • EEG  : BIOT encoder (frozen) + IIIC head (fine-tuned)│ │
│  └─────────────────────────────────────────────────────────┘  │
└───────────────────────────┬──────────────────────────────────┘
                            │  djongo ODM
┌───────────────────────────▼──────────────────────────────────┐
│  DATA TIER — MongoDB (medical_platform DB)                    │
│  users · patients · mri · ecg · echo · eeg · reports          │
│  + media/ filesystem store (uploads + result artefacts)       │
└──────────────────────────────────────────────────────────────┘
```

A key cross-cutting invariant is **doctor isolation**: every database query in
the `patients`, `mri`, `ecg`, `echo`, and `reports` apps is filtered by the
authenticated doctor, enforced along the foreign-key chain
`<Analysis> → patient → doctor`. Returning another doctor's data is treated as a
defect, not a feature.

---

## 3. Components and Modules

*Insert Table 1 (Component Description Table) here.*

| # | Component / module | Tier | Role |
|---|---|---|---|
| 1 | `authentication` | App | Custom email-based `User` model; JWT issue/refresh (1 h access, 7 d refresh). |
| 2 | `patients` | App | Doctor-scoped patient CRUD and the `/history/` aggregate endpoint. |
| 3 | `mri` | App | MRI upload, synchronous inference orchestration, result-image URLs. |
| 4 | `ecg` | App | ECG upload, inference orchestration, HRV + pathology probability storage. |
| 5 | `echo` | App | Echo-video upload, EchoNet inference (EF + LV segmentation). |
| 6 | `eeg` | App | `.edf` upload, BIOT/IIIC 6-class inference over 10 s segments. |
| 7 | `reports` | App | ReportLab PDF generation with a combined, rule-based interpretation. |
| 8 | `inference.model_loader` | Engine | Lazy singleton that loads/caches every model; raises a clear `FileNotFoundError` when non-bundled weights are absent. |
| 9 | `inference.*_pipeline` | Engine | Per-modality pipelines returning a uniform result envelope. |
| 10 | `inference.biot/` + `eeg_preprocess.py` | Engine | Vendored BIOT model code and shared train/inference-parity EEG preprocessing. |
| 11 | Frontend `modules/` | UI | Per-domain React modules (Auth, Dashboard, Patients, MRI, ECG, Echo, EEG, Reports). |
| 12 | Frontend `services/` + `store/` | UI | Axios instance (attaches JWT, intercepts `401 → /login`) and Redux slices. |
| 13 | MongoDB + `media/` | Data | Document persistence and artefact storage. |

### 3.1 The two backend contracts

Two contracts hold the architecture together and must be preserved by any new
modality:

- **Doctor isolation** (Section 2.2).
- **Pipeline result envelope.** Every inference function returns a plain
  dictionary shaped `{status, …result_fields, error?, error_type?}` and **never
  raises into the view**. Structured failure is part of the contract: the API can
  therefore report *partial* results (for example, an ECG analysis with 5 of 7
  pathology models successfully loaded) instead of returning an opaque HTTP 500.

---

## 4. Step-by-Step Workflow (End to End)

*Insert Figure 2 (end-to-end flowchart) and Figure 3 (UML sequence diagram) here.*

The following describes one complete clinical session. Steps 1–3 are common to all
modalities; Step 4 details the per-pipeline processing; Steps 5–7 cover
persistence, rendering, and reporting.

**Step 1 — Authentication.** The clinician submits email + password to
`POST /api/auth/login/`. The backend returns an `access` + `refresh` JWT pair.
The frontend stores the token and the Axios interceptor attaches it as a
`Bearer` header to every subsequent request; a `401` response redirects to
`/login`.

**Step 2 — Patient selection.** The clinician creates or opens a patient via
`/api/patients/`. The `doctor` field is auto-set from the JWT, and every list/detail
query is filtered to the requesting doctor (isolation invariant).

**Step 3 — Upload + dispatch.** From the patient detail page the clinician starts a
new analysis and drag-drops a file to the modality endpoint
(`POST /api/{mri|ecg|echo|eeg}/upload/`, multipart `{patient_id, file}`). The thin
DRF view validates ownership and file type, persists the upload to `media/`,
creates a database record in `processing` state, and calls the corresponding
pipeline **synchronously**.

**Step 4 — Per-modality inference.** Each pipeline loads its models lazily from the
singleton `ModelLoader`, processes the input, writes visual artefacts to
`media/<modality>/results/`, and returns the result envelope.

- **MRI** (`analyze_mri`, two-stage):
  1. *Load* the image (universal loader: PNG/JPG/DICOM/NIfTI).
  2. *Preprocess for U-Net*: resize to 256×256, **per-channel z-score**
     normalisation (the upstream U-Net expects 3 channels = 3 MRI sequences with
     independent intensity distributions).
  3. *Segmentation*: the U-Net outputs a probability map already in `[0,1]`
     (sigmoid is applied **inside** its `forward()`); the pipeline thresholds at
     0.5 to obtain a binary mask. **Decision point — saturation guard:** if the
     mask covers > 75 % of the image, the output is treated as degenerate and
     `tumor_detected = False`; otherwise a tumour is reported only if the mask
     exceeds a 50-pixel noise floor.
  4. *Classification*: if a tumour was detected, the image is cropped to the
     mask bounding box (10-px padding) — a **crop-then-classify** path — and fed
     to the Vision Transformer; otherwise the full image is classified. A softmax
     gives the 4-class label and confidence.
  5. *Fusion (rule-based)*: `generate_clinical_note` combines the U-Net and ViT
     verdicts into one of four recommendations (confirmed / ambiguous /
     classifier-only / no tumour).
  6. *Artefacts*: a three-panel figure (original | mask | overlay), plus the mask
     and overlay alone, are saved.

- **ECG** (`analyze_ecg`): load the 12-lead record (shape 12 × 5000 at 500 Hz,
  i.e. ~10 s) → **preprocess** with a 4th-order Butterworth band-pass (0.5–40 Hz)
  and per-lead z-score normalisation → run the 7 DenseNet-1D pathology classifiers
  and apply **per-pathology calibrated thresholds** (Section 6) → in parallel,
  compute NeuroKit2 heart-rate and HRV time-domain metrics (mean HR, RMSSD, SDNN,
  pNN50) **on Lead II** → derive a primary diagnosis (highest-probability detected
  pathology, else *Normal Sinus Rhythm*) and rule-based cross-check flags (e.g.
  HR < 60 → bradycardia) → render a 6×2 grid plot of all 12 leads with R-peaks
  marked on Lead II.

- **ECHO** (`analyze_echo`): decode the echo video (.avi/.mp4) to 112×112 RGB
  frames, normalise with the EchoNet training statistics → R(2+1)D-18 regresses
  ejection fraction, averaged over up to 4 clips of 32 frames (the EF is clamped to
  [0, 100]) → DeepLabV3-ResNet50 segments the left ventricle per frame, locating
  end-diastole (largest LV area) and end-systole (smallest non-zero LV area) →
  map EF to a clinical category (Reduced/HFrEF < 40 %, Mildly reduced < 50 %,
  else Normal).

- **EEG** (`analyze_eeg`): parse the `.edf` → apply the BIOT-exact preprocessing
  (16-channel longitudinal-bipolar montage, resample to 200 Hz, 10 s = 2000-sample
  segments, per-channel 95th-percentile amplitude normalisation) → classify every
  10 s segment with the frozen encoder + fine-tuned IIIC head → aggregate to
  per-class proportions, a dominant pattern, and a harmful-activity flag
  (any SZ/LPD/GPD).

**Step 5 — Persistence.** The view stores the envelope fields on the modality
record, sets status to `completed` (or `failed` with the structured error), and
saves artefact paths. Visual results are served from `media/`.

**Step 6 — Rendering.** The frontend polls/refetches the record and renders the
modality-specific result view (segmentation overlay, HRV table, per-pathology
probability table, EF + LV segmentation, EEG IIIC class distribution/timeline)
plus the raw textual report.

**Step 7 — Combined report.** The clinician calls
`POST /api/reports/generate/` with the patient ID and any subset of completed
analysis IDs (≥ 1 required). The `reports` app composes a multi-section ReportLab
PDF with a rule-based combined interpretation and streams it for download.
*(Note: all PDF text passes through an ASCII substitution because Helvetica lacks
box-drawing glyphs.)*

### 4.1 Output fields (full names)

*Insert Table 2 (Modality Output / Data-Mapping Table) here.*

Each pipeline returns an in-memory **result envelope** (unprefixed keys, e.g.
`tumor_type`, `ejection_fraction`); the modality view maps these onto the
persisted **model fields** (prefixed `result_*`). URL fields exposed by the REST
API (`*_url`) are derived by the serializer from the stored `*_path` fields. The
table below lists the persisted model fields.

| Modality | Primary outputs (full names) | Persisted model fields |
|---|---|---|
| **MRI** | Tumour detected (boolean); Tumour type ∈ {glioma, meningioma, no-tumour, pituitary}; Classification confidence. *(Tumour area in pixels and segmentation confidence are computed by the pipeline and appear in the report text, but are **not** persisted as model fields.)* | `result_tumor_detected`, `result_tumor_type`, `result_confidence`, `result_mask_path`, `result_overlay_path`, `result_analysis_path`, `result_report` |
| **ECG** | Primary diagnosis (arrhythmia detected + type + confidence); per-pathology probabilities for AFIB (Atrial Fibrillation), 1AVB (1st-degree AV Block), STACH (Sinus Tachycardia), SBRAD (Sinus Bradycardia), RBBB (Right Bundle-Branch Block), LBBB (Left Bundle-Branch Block), PVC (Premature Ventricular Complex); mean heart rate + classification; HRV metrics (RMSSD, SDNN, pNN50) | `result_arrhythmia_detected`, `result_arrhythmia_type`, `result_confidence`, `result_pathology_probabilities`, `result_hrv_metrics`, `result_plot_path`, `result_report` |
| **ECHO** | Left-Ventricular Ejection Fraction (EF, %); EF clinical category; End-Diastolic / End-Systolic LV area; LV segmentation overlay | `result_ef`, `result_ef_category`, `result_ed_area`, `result_es_area`, `result_overlay_path`, `result_report` |
| **EEG** | IIIC 6-class distribution — SZ (Seizure), LPD (Lateralized Periodic Discharges), GPD (Generalized Periodic Discharges), LRDA (Lateralized Rhythmic Delta Activity), GRDA (Generalized Rhythmic Delta Activity), Other; Dominant pattern; Harmful-activity flag (any SZ/LPD/GPD) | `result_dominant_pattern`, `result_harmful`, `result_class_distribution`, `result_plot_path`, `result_report` |

---

## 5. Suggested Figures and Tables

**Figures**

- **Figure 1 — System architecture diagram.** The three-tier layout of
  Section 2.2, annotated with protocols (HTTPS/JWT, REST, djongo ODM).
- **Figure 2 — End-to-end workflow flowchart.** Login → patient → upload →
  inference → persistence → render → report, with the MRI saturation guard and
  the report ≥ 1-analysis gate shown as decision diamonds.
- **Figure 3 — UML sequence diagram.** Browser ↔ DRF view ↔ ModelLoader ↔
  pipeline ↔ MongoDB/media for a single MRI upload.
- **Figure 4 — MRI two-stage pipeline.** U-Net segmentation → mask → bounding-box
  crop → ViT classification → rule-based fusion.
- **Figure 5 — Inference-engine class diagram.** The lazy-singleton `ModelLoader`
  and the four pipeline modules sharing the result-envelope contract.
- **Figure 6 — Sample report.** A rendered multi-section combined PDF.

**Tables**

- **Table 1 — Component description** (Section 3).
- **Table 2 — Modality output / data mapping** (Section 4.1).
- **Table 3 — Model provenance** (Section 6.1).
- **Table 4 — Pretrained vs. project results, per modality** (Section 6.2).

---

## 6. Pretrained Models vs. the Project's Contribution

A central honesty requirement for this thesis is to separate **what was reused**
(open, peer-reviewed pretrained models) from **what the project contributes**.
The contribution is **not the models themselves but the architecture that
integrates them**, plus three concrete model-level interventions: an ECG
threshold calibration, an MRI segmentation bug-fix, and one genuine in-repo
fine-tuning (the EEG IIIC head).

### 6.1 Provenance — where the pretrained models were obtained

*Insert Table 3 here.*

| Modality | Pretrained component (full name) | Source | Pretrained on |
|---|---|---|---|
| MRI segmentation | U-Net (CNN encoder–decoder) | `mateuszbuda/brain-segmentation-pytorch` via `torch.hub` [1], [3] | TCGA-LGG (110 patients, FLAIR MRI) |
| MRI classification | Vision Transformer ViT-B/16 | `Devarshi/Brain_Tumor_Classification` (HuggingFace) [2] | Kaggle Brain-Tumor MRI Dataset (~7 000 images, 4 classes) |
| ECG | DenseNet-1D-121 ensemble (×7) | `ecglib` (ISPRAS), exact pin 1.0.1 [4], [6] | 500 000+ 12-lead ECG records |
| ECG (HRV) | NeuroKit2 (classical DSP) | `neurokit2` library [7] | Rule-based / validated, not learned |
| ECHO | DeepLabV3-ResNet50 (LV seg) + R(2+1)D-18 (EF regression) | EchoNet-Dynamic, Stanford [11] | EchoNet-Dynamic echo videos |
| EEG | BIOT biosignal transformer — **encoder only** | `ycq091044/BIOT` (vendored) [12] | 5 M MGH resting-EEG samples (self-supervised) |

Two components are **not turnkey**: EchoNet weights are downloaded separately
(not bundled), and BIOT releases only a self-supervised encoder — its IIIC
classification head **does not exist upstream** and was produced in-repo
(`tools/train_eeg_head.py`). Both fail with a clear `FileNotFoundError` until
their weights are present (honest failure rather than serving an untrained model).

### 6.2 What each model outputs, how it was improved, and where it falls short

*Insert Table 4 here. All numbers are from `VALIDATION.md`; reproduce commands are listed there.*

#### (a) ECG — DenseNet-1D-121 ensemble

- **Output (full names):** independent presence probabilities for the seven
  pathologies AFIB, 1AVB, STACH, SBRAD, RBBB, LBBB, PVC.
- **Project improvements:** (1) *threshold calibration, no retraining* — the
  original pipeline used a flat `p > 0.5` decision threshold that over-flagged
  severely; tuning a **per-pathology threshold on PTB-XL validation fold 9** (then
  applied unchanged to held-out test fold 10 — no leakage) raised **macro F1 from
  0.514 → 0.711**. (2) *fine-tuning (June 2026)* — three of the seven models
  (1AVB, RBBB, PVC) were continue-trained on Colab T4 under a no-regression rule
  (`Colab PFE/colab_ecg_finetune.ipynb`); with re-tuned thresholds the deployed
  ensemble reaches **macro F1 0.727** (calibration on the new ensemble:
  0.544 → 0.727). ROC-AUC is essentially unchanged (threshold-independent),
  confirming the calibration gain is not a different model.
- **Reported performance:** mean ROC-AUC **0.980**, macro balanced accuracy
  **0.887**, macro F1 **0.727** on PTB-XL fold 10 (2 198 records) — verified
  locally June 11 2026; stock baseline 0.978 / 0.884 / 0.711.
- **Where it falls short:** SBRAD remains weak (F1 0.47; its fine-tune did not
  beat baseline and was not kept) and 1AVB moderate even after its fine-tune
  (F1 0.61), both limited by *precision* (many false positives) despite high AUC. There is also a possible
  **train/test overlap** caveat: `ecglib` may have trained on a corpus including
  PTB-XL, so the AUC may be optimistic — to be confirmed on an independent set
  (Chapman-Shaoxing / Georgia).

#### (b) MRI segmentation — U-Net

- **Output:** a pixel-level binary tumour mask, tumour area (pixels), and
  segmentation confidence.
- **Project improvement (bug-fix):** a **double-sigmoid bug** was diagnosed and
  fixed. The upstream U-Net applies sigmoid inside `forward()`; the pipeline
  applied `torch.sigmoid()` again, squashing the `[0,1]` map into `[0.5, 0.73]` so
  every pixel crossed threshold and the mask saturated (then suppressed by the
  saturation guard). Removing the redundant sigmoid took **Dice from ~0.02 → 0.85**.
- **Reported performance:** Dice **0.852** on tumour-positive LGG slices (0.827 all
  slices), IoU 0.78, 0 % saturated predictions — close to the source paper's
  ~0.89 mean DSC (the gap is per-image vs per-volume normalisation).
- **Where it falls short:** validated on LGG (which provides masks), a **different
  MRI modality** from the Kaggle classification set; a single uploaded image is
  therefore not validated end-to-end through both segmentation and classification.

#### (c) MRI classification — Vision Transformer (ViT-B/16)

- **Output:** 4-class label ∈ {glioma, meningioma, no-tumour, pituitary} with a
  softmax confidence.
- **Project use:** **continue-trained in this project** (Colab T4, June 2026,
  `Colab PFE/colab_mri_vit_finetune.ipynb`; weights auto-detected from
  `backend/models_weights/vit_brain_tumor/`), with a **crop-then-classify**
  path enabled by the now-working segmentation.
- **Reported performance:** accuracy **95.4 %** (1 527/1 600), macro F1 **0.954**
  on the Kaggle Brain-Tumor `Testing/` split — the stock hub model scored
  80.4 % / 0.794 (both confusion matrices in VALIDATION.md §2).
- **Where it falls short:** remaining errors concentrate on **glioma recall
  (0.83)** — gliomas misread as meningioma. The evaluation runs on the full
  image (the Kaggle set has no masks), so the crop-then-classify gain is still
  unmeasured, and cross-dataset validation with the LGG-validated U-Net stays open.

#### (d) Echocardiography — EchoNet-Dynamic

- **Output (full names):** Left-Ventricular Ejection Fraction (EF, regression) and
  a Left-Ventricle segmentation mask at end-diastole/end-systole; EF mapped to a
  clinical category.
- **Project use:** deployed as-is; weights downloaded separately (Section 6.1).
- **Reported performance:** EF **MAE 3.19 %**, RMSE 4.01 %, **R² 0.860**, Pearson
  r 0.932; LV segmentation **Dice 0.897** — matching published EchoNet-Dynamic
  performance, confirming correct integration.
- **Where it falls short:** numbers are on **TEST-split subsets** (40 videos for
  EF, 30 traced frames for Dice) because CPU video inference is slow
  (~10–40 s/video); the full 1 277-video figure requires a longer run.

#### (e) EEG — BIOT encoder + IIIC head *(the project's genuinely trained model)*

- **Output (full names):** IIIC 6-class harmful-brain-activity distribution — SZ
  (Seizure), LPD (Lateralized Periodic Discharges), GPD (Generalized Periodic
  Discharges), LRDA (Lateralized Rhythmic Delta Activity), GRDA (Generalized
  Rhythmic Delta Activity), Other — plus a dominant pattern and a harmful flag.
- **Project contribution (genuine fine-tuning):** because BIOT ships **no** IIIC
  head, the project attaches BIOT's `ClassificationHead` and **fine-tunes only that
  head** on the public Kaggle HMS dataset, encoder **frozen**
  (`tools/train_eeg_head.py`). The encoder loads with a byte-exact key match
  (0 missing/0 unexpected), and a shared preprocessing module guarantees
  train/inference parity.
- **Reported performance:** balanced accuracy **0.278** (vs 0.167 chance), Cohen's
  κ **0.147**, macro F1 **0.265**, KL divergence 1.333, on a **patient-disjoint**
  held-out split (1 883 windows). Best classes: GPD (F1 0.44), GRDA, LRDA.
- **Where it falls short (the most important honesty point):** these results are
  **above chance but modest**. Increasing the training data 3.7× did **not** move
  the headline (~0.28) — the signature of a **frozen-encoder ceiling**: a small
  linear head over fixed features plateaus regardless of data volume. The rare
  *Other* class (n = 33) collapses to F1 0.00 and SZ precision is low (class
  imbalance). BIOT's published IIIC-range numbers (~0.5 balanced accuracy) come
  from fine-tuning the **whole** model; the documented next step — unfreezing the
  encoder for a full fine-tune — is impractical on CPU and requires a GPU. EEG is
  also a **critical-care** screening task (functional), **not** a tumour detector;
  it never localises or diagnoses a tumour.

### 6.3 Summary of the distinction

For two of the five model families (MRI U-Net and the two EchoNet models) the
**weights are reused unchanged**. The **MRI ViT** and **three of the seven ECG
classifiers** (1AVB, RBBB, PVC) were **continue-trained in this project**
(Colab T4, June 2026), and the **EEG IIIC head** is trained entirely in-repo.
The project's value remains the integrating architecture plus targeted
interventions — the ECG **threshold calibration** (macro F1 0.51 → 0.71 stock;
0.54 → 0.73 after the fine-tune), the MRI **double-sigmoid fix**
(Dice 0.02 → 0.85), and the fine-tunes themselves (MRI 80.4 % → 95.4 %; ECG
macro F1 0.711 → 0.727). The EEG head's honest, below-state-of-the-art result is
a direct and explainable consequence of a deliberate constraint (frozen encoder,
CPU-only) rather than a methodological error.

---

## 7. Functional Limitations (carried into the workflow)

These limitations are inseparable from how the platform functions and should be
disclosed at the defence:

1. **No data-driven multimodal fusion** — the combined interpretation is template
   logic; no neuro-cardiac correlation is learned or measured [13].
2. **Synchronous inference** — no task queue; echo video inference is especially
   slow on CPU, bounding throughput.
3. **Cross-dataset MRI validation** — segmentation (LGG) and classification
   (Kaggle) use different datasets/modalities; one image is not validated through
   both tasks, and the two models can disagree without resolution.
4. **Threshold sensitivity (ECG)** — calibrated for PTB-XL-like data; a new source
   may require re-tuning.
5. **Non-bundled weights** — EchoNet and the BIOT IIIC head must be provided
   before their endpoints function.
6. **Security gap to disclose** — result images and uploads are served from
   `/media/` without authentication, bypassing the per-doctor API access control
   (a real medical-data-protection issue and an ethics talking point).

---

## 8. Section Conclusion

End to end, the platform realises a clean separation of concerns: a stateless,
doctor-isolated REST API drives four independent, contract-bound inference
pipelines, whose structured outputs are persisted, visualised, and finally fused
into a single clinician-facing PDF. The engineering contribution — modular
plug-in modality design, a uniform failure-safe result envelope, an ECG
calibration that lifted macro F1 by ~0.20 without retraining (plus June 2026
fine-tunes of three ECG models and the MRI classifier), a segmentation
bug-fix that restored Dice from 0.02 to 0.85, and a June 2026 **safety-first
recall pass** (ECG ≥0.95 all 7, MRI tumour-detection 0.998, Echo reduced-EF 0.95,
EEG seizure-routing 0.966 — decision-rule changes, no GPU; see VALIDATION.md §0)
— is demonstrable and reproducible.
The one model trained in-repo (the BIOT IIIC head) is reported with full honesty,
including its frozen-encoder ceiling and the GPU full-fine-tune that would close
the gap. The principal scientific frontier — a *learned* neuro-cardiac
correlation requiring a paired imaging + ECG cohort — is articulated as the
project's main future work.
```

