# The Way the Project Works and Lives

> A single, plain-language walkthrough of **how the platform runs end to end**, **every
> method and model it uses**, **where each model comes from**, **what data it was trained
> on**, and **how my version differs from the original model**.
>
> Everything here is taken from the actual code (`backend/apps/inference/`) and from
> [README.md](../README.md) / [VALIDATION.md](../maybe%20read/VALIDATION.md) — no numbers are invented.
> If a value here ever disagrees with the code, the code wins.

---

## 1. How the project "lives" — the runtime flow

The platform is two independent apps that talk over a REST API:

```
Doctor's browser
   │  (JWT bearer token on every call)
   ▼
React 19 + Vite + Tailwind  (frontend/, port 3000)
   │  axios → /api/*
   ▼
Django 3.2 + DRF + SimpleJWT  (backend/, port 8000)
   │
   ├─ apps/authentication   email login, JWT issue/refresh
   ├─ apps/patients         doctor-scoped CRUD + /history/
   ├─ apps/mri ecg echo eeg  upload → run model → save result
   ├─ apps/reports          ReportLab PDF (combined interpretation)
   └─ apps/inference        the model loader + all 4 pipelines  ◄── the "brain"
   │
   ▼
MongoDB (via djongo)   users · patients · mri · ecg · echo · eeg · reports
```

### The life of one analysis request

1. The doctor logs in → backend returns a **JWT access token** (1 h) + refresh token (7 days).
2. The doctor opens a patient and uploads a file (MRI image / ECG file / echo video / `.edf` EEG).
3. The matching app (e.g. `apps/mri`) saves the upload, then calls the **inference pipeline
   synchronously — in the same request thread**. There is no Celery / job queue. The browser
   waits (~5–60 s) for the answer.
4. The pipeline asks `ModelLoader` for the model. The **first** call downloads / loads the
   weights (~700 MB total across MRI+ECG) and keeps them in memory; **every later call reuses
   the same in-memory model** (lazy singleton). GPU is used automatically if present, else CPU.
5. The pipeline returns a plain dict shaped `{status, ...results, error?}`. It **never raises
   into the view** — a failure is reported as structured data so the API can still return
   partial results (e.g. ECG with 5 of 7 pathology models loaded).
6. The result + any generated images are stored, and the doctor's result page renders them.
7. **+ Generate report** combines any completed analyses into one PDF via ReportLab, with a
   rule-based "combined interpretation" section.

### Two rules the backend always keeps

- **Doctor isolation** — every database query filters by the requesting doctor. The chain is
  `Analysis → patient → doctor`. One doctor can never see another's data.
- **Result envelope** — pipelines return `{status, ...fields, error?, error_type?}` and never
  crash the API.

---

## 2. The models — what, from where, trained on what, and how mine differs

The honest one-line summary: **the platform's contribution is the integration architecture,
not the models.** Most models are taken pre-trained and used as-is. Only **two** components are
not turnkey: **EchoNet** weights are downloaded separately, and **BIOT** ships only an encoder so
**I fine-tuned its classification head myself**.

| Modality | Model | Where I got it | Trained on | Mine vs. original |
|---|---|---|---|---|
| MRI segmentation | U-Net (~7.7M) | `torch.hub: mateuszbuda/brain-segmentation-pytorch` | TCGA-LGG, 110 patients, FLAIR MRI | **Same weights**, used as-is. My change is a *usage fix* (no double sigmoid). |
| MRI classification | Swin Transformer (Swin-T) (~28M) | HuggingFace `Devarshi/Brain_Tumor_Classification` | Kaggle Brain-Tumor MRI, ~7 000 images, 4 classes | **Same weights**, used as-is. |
| ECG | DenseNet-1D-121 ×7 (~8M each) | `ecglib` (ISPRAS) `create_model(pretrained=True)` | 500 000+ 12-lead ECG records | **Same weights**, used as-is. My change is *per-pathology decision thresholds*. |
| ECG (HRV) | NeuroKit2 | `neurokit2` library | none — classical/rule-based DSP | unchanged library. |
| Echo | DeepLabV3-ResNet50 + R(2+1)D-18 | EchoNet-Dynamic checkpoints (Stanford), loaded from disk | EchoNet-Dynamic echo videos | **Same weights**, but I **swap the final layer** to load them onto torchvision backbones. |
| EEG | BIOT (~3M) | encoder from `ycq091044/BIOT` (vendored); **head trained by me** | encoder: ~5M MGH resting EEG; **head: Kaggle HMS, by me** | **Encoder = original. The 6-class IIIC head is mine** (fine-tuned in-repo). |

The sections below explain each one and the exact method used.

---

### 2.1 MRI — two-stage analysis

**Method (`mri_pipeline.py`):** the uploaded image runs through **two** pre-trained models:

1. **U-Net** → pixel-level tumor **segmentation** mask → tumor area + a saturation guard.
2. **Swin** → 4-class tumor **type** (`glioma`, `meningioma`, `no_tumor`, `pituitary`).

**Models & source:**
- U-Net: `torch.hub.load('mateuszbuda/brain-segmentation-pytorch', 'unet', pretrained=True)`,
  ~30 MB download. Trained on **TCGA-LGG** (110 patients, FLAIR MRI). Reference: Buda et al., 2019.
- Swin: `Devarshi/Brain_Tumor_Classification` from HuggingFace, ~110 MB. Trained on the **Kaggle
  Brain-Tumor MRI** dataset (~7 000 images, 4 classes). Base backbone `microsoft/swin-tiny-patch4-window7-224`;
  architecture from Liu et al., 2021 (Swin Transformer, ICCV).

**Difference vs. the original model — the double-sigmoid fix (this is the key one):**
The `mateuszbuda` U-Net already applies `sigmoid` **inside its own `forward()`**, so its output
is already a probability map in `[0, 1]`. An earlier version of my pipeline applied
`torch.sigmoid()` a **second** time, which squashed `[0,1]` into `[0.5, 0.73]` — pushing *every*
pixel past the 0.5 threshold, so the mask covered ~100% of the image. A "saturation guard" then
suppressed that to `tumor_detected: false`, making segmentation look completely broken.
**The fix: use the U-Net output directly (no second sigmoid).** That took Dice from **0.02 → 0.85**
on the LGG dataset. The saturation guard stays as a harmless safety net (real masks cover 2–5%,
far below its 75% trigger). The weights themselves are unchanged — this was a usage bug, not a
retrain.

**Validation:** segmentation Dice **0.85** on LGG; classifier accuracy **95.4%** on the Kaggle test split (fine-tuned June 2026 — the stock hub model scored 80.4%).
Note these are *different datasets* — a single uploaded image is not validated through both tasks
end to end.

---

### 2.2 ECG — pathology ensemble + classical HRV

**Method (`ecg_pipeline.py`):** two parallel streams on the 12-lead signal:

1. **DenseNet-1D-121 × 7** (one binary classifier per pathology) → per-pathology probability →
   `detected` decision using a tuned threshold.
2. **NeuroKit2** on Lead II → time-domain **HRV** metrics (mean HR, RMSSD, SDNN, pNN50) with
   reference-range flags. The signal is also bandpass-filtered (Butterworth, 0.5–40 Hz).

**Models & source:** `ecglib` (ISPRAS), `create_model(model_name='densenet1d121', pathology=p,
pretrained=True)`. Trained on **500 000+ 12-lead ECG records**. Reference: Avetisyan et al., 2023;
the public benchmark behind it is **PTB-XL** (Wagner et al., 2020).

The 7 pathologies that load: `AFIB`, `1AVB`, `STACH`, `SBRAD`, `RBBB`, `LBBB`, `PVC`.

**Difference vs. the original model — per-pathology decision thresholds:**
The `ecglib` models are excellent at *ranking* (per-pathology AUC ~0.97–1.00) but a flat
`prob > 0.5` cutoff **massively over-flags** (many false positives). The first contribution was
pure calibration: I **tuned a separate decision threshold per pathology** to maximize F1 on the
PTB-XL validation fold (no test leakage), raising macro F1 from **0.51 → 0.71** with no
retraining. In June 2026 I additionally **fine-tuned three of the seven models** (1AVB, RBBB,
PVC — Colab T4, kept only where they beat baseline), re-tuned the thresholds, and the deployed
ensemble reaches macro F1 **0.727**. The thresholds live in `DETECTION_THRESHOLDS` in
`ecg_pipeline.py`, with a `0.5` fallback for any untuned code.

> Note on the build spec: it asked for `IRBBB`/`CRBBB`, but those don't exist in `ecglib 1.0.1` —
> it ships `RBBB`/`LBBB` (general bundle branch block) instead. That's why you'll see a harmless
> startup warning. This is by design, not a bug.

**Validation:** mean ROC-AUC **0.980**, macro balanced accuracy **0.887**, macro F1 **0.727** on
PTB-XL fold 10 (verified locally June 2026; stock baseline 0.978 / 0.884 / 0.711). Caveat:
`ecglib` may have trained on PTB-XL, so the AUC could be optimistic.

---

### 2.3 Echo — EchoNet-Dynamic (EF + LV segmentation)

**Method (`echo_pipeline.py`):** the input is an echo **video**. Two pretrained models:

1. **DeepLabV3-ResNet50** → per-frame **left-ventricle segmentation**; end-diastole = max LV area,
   end-systole = min LV area.
2. **R(2+1)D-18** (3D spatiotemporal CNN) → **ejection-fraction (EF) regression**, averaged over
   sampled 32-frame clips, plus a clinical category (reduced / mildly reduced / normal).

Frames are resized to 112×112 and normalized with EchoNet's own training mean/std.

**Models & source:** EchoNet-Dynamic (Stanford; Ouyang et al., *Nature* 2020,
github.com/echonet/dynamic). Trained on the **EchoNet-Dynamic** echocardiogram video dataset.

**Difference vs. the original model — backbone surgery to load the checkpoints:**
I build standard **torchvision** backbones with **no pretrained weights**, then **replace the final
layer** to match EchoNet's task before loading the published checkpoints:
- segmentation: `seg.classifier[-1] = nn.Conv2d(256, 1, kernel_size=1)` (1 output channel = LV),
- EF: `ef.fc = nn.Linear(ef.fc.in_features, 1)` (1 output = EF regression).

I also strip the `module.` prefix from the checkpoint keys (they were saved from `DataParallel`).
**The learned weights are EchoNet's** — I only reshape the heads so the official checkpoints load.

**Weights are NOT bundled.** `get_echo_models()` reads `echonet_seg.pt` + `echonet_ef.pt` from
`backend/models_weights/echonet/` (overridable via `ECHONET_SEG_WEIGHTS` / `ECHONET_EF_WEIGHTS`)
and raises a clear `FileNotFoundError` if they're missing. So the echo endpoint failing on a fresh
checkout is **expected**, not a bug.

**Validation:** EF **MAE 3.19%**, R² 0.86; LV segmentation **Dice 0.90** on the EchoNet test split.

---

### 2.4 EEG — BIOT (this is the one I actually trained)

**Method (`eeg_pipeline.py` + `eeg_preprocess.py`):** the whole `.edf` recording is split into
consecutive **10-second segments (2000 samples @ 200 Hz)**. **BIOT** classifies each segment into
the **IIIC 6-class** scheme, and the pipeline aggregates to per-class proportions over time, a
dominant pattern, and a harmful-activity flag (any `SZ`/`LPD`/`GPD`).

The 6 classes (Ictal–Interictal–Injury Continuum): `SZ` (Seizure), `LPD`, `GPD`
(Lateralized/Generalized Periodic Discharges), `LRDA`, `GRDA` (Lateralized/Generalized Rhythmic
Delta Activity), and `Other`.

**Preprocessing must match training exactly** (`eeg_preprocess.py`, shared by train + inference):
16-channel longitudinal-bipolar "double-banana" montage in BIOT's exact channel order, resample
every channel to 200 Hz, 10 s windows, per-channel 95th-percentile amplitude normalization. These
constants are **not** to be "tidied" — they are what the pretrained encoder expects.

**Models & source:** BIOT — Biosignal Transformer (Yang et al., *NeurIPS* 2023,
github.com/ycq091044/BIOT). The model code is **vendored** under `apps/inference/biot/`.

**Difference vs. the original model — I fine-tuned the classification head myself:**
This is the single biggest "mine vs. original" difference in the whole project.
- BIOT **releases only a pretrained encoder** (`EEG-PREST-16-channels.ckpt`, pretrained on ~5M
  MGH resting EEG). It is bundled in the repo.
- BIOT **does NOT release an IIIC classification head.** So `get_eeg_model()` builds a
  `BIOTClassifier`, loads BIOT's encoder, then loads a **6-class head that I fine-tuned in-repo**
  on the **Kaggle HMS** dataset via `tools/train_eeg_head.py` (**encoder frozen, trained on CPU**).
- If that head file (`biot_iiic.pt`) is missing, the endpoint raises a clear `FileNotFoundError`
  pointing at the trainer — so it fails honestly rather than returning the predictions of a random,
  untrained head.

**Validation (honest-but-modest, by design):** balanced accuracy **0.278**, κ 0.147, macro F1 0.265
on a patient-disjoint Kaggle HMS subset (1,883 windows). This is **above the 0.167 chance floor**
but **below BIOT's full-data ~0.5** — because my head was trained on a small subset (1,451 EEGs)
with the encoder frozen on CPU. The documented path to close the gap is a **GPU full-fine-tune**.

**Scope honesty:** EEG here is **functional** critical-care screening (the complement to the
*structural* MRI tumor analysis). It flags harmful electrical patterns; **it never diagnoses or
localizes a tumor.**

---

## 3. The "combined interpretation" — what it is and is NOT

The PDF report (`apps/reports/pdf_generator.py`) merges any completed analyses and adds a
**combined clinical interpretation**. This is **rule-based template text**, motivated by the
neuro-cardiac coupling literature — it is **NOT a learned or measured correlation** between brain
pathology and ECG. Testing that hypothesis would need a paired imaging+ECG cohort, which is the
project's main future work.

(Implementation note: the PDF runs all text through `_ascii()` because Helvetica lacks box-drawing
glyphs — don't remove it.)

---

## 4. Quick map: which datasets train what, and where validation comes from

| Model | Trained on (origin) | Validated on (held-out) | Headline number |
|---|---|---|---|
| U-Net (MRI seg) | TCGA-LGG (110 patients, FLAIR) | LGG MRI Segmentation (3,929 slices) | Dice **0.85** |
| Swin (MRI 4-class, fine-tuned June 2026) | Kaggle Brain-Tumor (~7k images) | Kaggle Brain-Tumor `Testing/` (1,600) | acc **95.4%** (stock: 80.4%) |
| DenseNet-1D ×7 (ECG; 1AVB/RBBB/PVC fine-tuned June 2026) | 500k+ ECGs (ecglib) + PTB-XL folds 1–8 (fine-tune) | PTB-XL fold 10 (2,198) | ROC-AUC **0.980**, F1 0.727 |
| EchoNet (EF + seg) | EchoNet-Dynamic videos | EchoNet-Dynamic TEST | EF MAE **3.19%**; Dice 0.90 |
| BIOT (EEG IIIC) | encoder: 5M MGH EEG; **head: Kaggle HMS (mine)** | Kaggle HMS, patient-disjoint (1,883) | bal-acc **0.278** |

> **Safety-first (June 2026):** each model also has a high-recall operating point to
> minimize false negatives — ECG ≥0.95 (all 7), MRI tumour-detection 0.998, Echo
> reduced-EF 0.95, EEG seizure-routing 0.966. Threshold/decision-rule change, no GPU
> retraining; precision is the traded cost. See `maybe read/VALIDATION.md` §0.

Reproduce any of these with the harnesses in `tools/` (`eval_mri_segmentation.py`,
`eval_mri_classifier.py`, `eval_ecg_classifier.py`, `eval_echo.py`, `eval_eeg.py`). Full per-class
tables and confusion matrices are in [VALIDATION.md](../maybe%20read/VALIDATION.md).

---

## 5. One-paragraph summary for the defence

The platform takes **five open, peer-reviewed deep-learning models** and integrates them behind a
single Django + MongoDB API with a React frontend, strict doctor-scoped data isolation, synchronous
lazy-loaded inference, and a combined PDF report. **Four of the models are used with their original
published weights** — my engineering contribution there is correct *usage* (the MRI double-sigmoid
fix), correct *calibration* (the ECG per-pathology thresholds), and correct *loading* (the EchoNet
head reshaping). **One model, BIOT for EEG, I fine-tuned myself**: BIOT releases only an encoder, so
I trained the 6-class IIIC head in-repo on the Kaggle HMS dataset. Every model is validated on a
held-out public dataset, with all numbers reproducible from `tools/` and documented honestly —
including the modest EEG score and the leakage caveats — in `VALIDATION.md`.
