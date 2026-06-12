# Methodology & Tools (Chapter 2 reference)

> **Honesty note.** This file documents what the platform **actually implements**,
> with exact library versions. Some items in a generic Chapter-2 template do
> **not** exist in this system (agentic AI, LSTM, spectrograms, entropy/chaos,
> non-parametric outlier statistics, TensorFlow). Those are flagged in §2.5 so
> you don't claim them. Validation numbers live in [VALIDATION.md](VALIDATION.md).

---

## 2.1 Data Acquisition and Preprocessing

### Data sources (all public benchmarks — no clinical collaboration)

| Modality | Dataset | Source | Used for |
|---|---|---|---|
| ECG | **PTB-XL v1.0.3** (21,837 × 12-lead, 500 Hz) | PhysioNet | ECG validation + threshold tuning |
| MRI (classification) | **Brain Tumor MRI Dataset** (~7k images, 4 classes) | Kaggle (M. Nickparvar) | ViT training/eval (Testing split) |
| MRI (segmentation) | **LGG MRI Segmentation** (TCGA, 3,929 slices + masks) | Kaggle (M. Buda) | U-Net Dice validation |
| Echo | **EchoNet-Dynamic** (10,030 echo videos + EF + LV tracings) | Stanford AIMI | EF (MAE/R²) + LV Dice validation |
| EEG | **HMS — Harmful Brain Activity** (IIIC 6-class, expert vote labels) | Kaggle | BIOT IIIC head fine-tuning + validation |

Pretrained model weights are pulled from **torch.hub** (U-Net), **HuggingFace Hub**
(ViT), **ecglib** (ECG ensemble), and **vendored BIOT** (EEG encoder). No model is
trained from scratch — the one fine-tuned component is the BIOT **IIIC head only**
(encoder frozen), because BIOT does not release an IIIC classification head.

### ECG signal preprocessing (`apps/inference/utils.py`, `ecg_pipeline.py`)

1. **Load & standardize** any input (`.csv`, `.edf`, `.dat/.hea` WFDB) to a fixed
   `(12 leads, 5000 samples)` array — resampled to **500 Hz**, padded/trimmed to a
   **10-second** window; missing leads are broadcast from lead I.
2. **Band-pass filtering** — 4th-order **Butterworth, 0.5–40 Hz**, zero-phase
   (`scipy.signal.butter` + `filtfilt`). This removes **baseline wander** (drift
   below 0.5 Hz) and **high-frequency / EMG noise** above 40 Hz.
3. **Per-lead z-score normalization** — `(x − μ_lead) / (σ_lead + 1e-8)` so every
   lead has zero mean / unit variance (matches ecglib's training normalization).

```
butter(4, [0.5, 40], btype='bandpass', fs=500) → filtfilt(axis=1)
x_norm = (x − mean_per_lead) / (std_per_lead + 1e-8)
```

### MRI image preprocessing (`apps/inference/mri_pipeline.py`)

- Any input (PNG/JPG/TIFF/BMP/DICOM/NIfTI) → RGB array.
- **U-Net:** resize to **256×256**, **per-channel z-score**, tensor `(1,3,256,256)`.
- **ViT:** HuggingFace image processor (resize + normalize) on the full image (or a
  bounding-box crop around the detected tumour).

### EEG signal preprocessing (`apps/inference/eeg_preprocess.py`)

Replicates BIOT's IIIC pipeline exactly (one shared module used by training,
evaluation, and inference, so they cannot drift):

1. **Montage** — read the `.edf` (MNE), build the **16-channel longitudinal-bipolar**
   montage ("double banana") in BIOT's own channel order, deriving it from the
   referential 10-20 electrodes (old/new aliases handled: T3→T7, T5→P7, …).
2. **Resample** every channel to **200 Hz**.
3. **Segment** into consecutive **10 s = 2000-sample** windows (the PREST-16 encoder
   was pretrained on "16 montages × 2000 time points").
4. **Normalise** per channel by the **95th-percentile amplitude**:
   `x / (q95(|x|) + 1e-8)` (scale-invariant, so EDF V-vs-µV scaling is moot).

```
edf → bipolar(16) → resample 200 Hz → 10 s windows → x / (q95(|x|)+1e-8)
BIOT: STFT(n_fft=200, hop=100) per channel → linear-attention Transformer → 6-class head
```

---

## 2.2 Mathematical / Signal Modeling (what is actually implemented)

> The generic outline lists "non-parametric outlier statistics" and
> "entropy/chaos/complexity." **These are NOT implemented.** Below is what the
> system really does — describe this instead.

- **Heart-rate variability (time-domain)** via **NeuroKit2** on lead II:
  mean **HR**, **RMSSD**, **SDNN**, **pNN50**, computed from R-peak detection.
- **Rule-based physiological cross-check** — bradycardia (HR < 60) / tachycardia
  (HR > 100) flags that corroborate the deep-learning output (e.g. STACH vs HR).
- **Decision-threshold calibration** — per-pathology thresholds chosen to maximise
  F1 on a held-out validation fold (PTB-XL fold 9), applied to the test fold
  (no leakage). This raised ECG macro-F1 from 0.51 → 0.71 (re-tuned June 2026 for
  the fine-tuned ensemble: 0.54 → 0.73). *(This is the real "statistical
  modeling" contribution.)*
- **Degenerate-output guards** — NaN/Inf sanitization before JSON; an MRI
  **saturation guard** (mask covering > 75 % of the image is rejected as a model
  failure). *(This is the honest version of "outlier handling.")*

*Optional (not yet built):* NeuroKit2 can also compute **sample/approximate
entropy** and nonlinear HRV — add these only if you want the "complexity" claim to
be true.

---

## 2.3 AI System Architecture (modular pipeline — NOT agentic)

> The outline says "Agentic AI framework / feature-extraction agent vs
> classification agent." **There are no agents.** The real design is a **modular,
> synchronous inference pipeline**. Describe it as such.

### Models actually used

| Modality | Model | Type | Params | Source |
|---|---|---|---|---|
| MRI segmentation | **U-Net** | 2-D CNN encoder–decoder | ~7.7 M | `mateuszbuda/brain-segmentation-pytorch` (torch.hub) |
| MRI classification | **ViT-B/16** | Vision Transformer | ~86 M | `Devarshi/Brain_Tumor_Classification` (HF) |
| ECG (×7) | **DenseNet-1D-121** | **1-D CNN** | ~8 M each | `ecglib` (ISP RAS) |
| ECG (HRV) | **NeuroKit2** | classical DSP (no NN) | — | `neurokit2` |
| Echo segmentation | **DeepLabV3-ResNet50** | 2-D CNN | ~40 M | EchoNet-Dynamic (GitHub) |
| Echo EF | **R(2+1)D-18** | 3-D (video) CNN | ~31 M | EchoNet-Dynamic (GitHub) |
| EEG | **BIOT** (Biosignal Transformer) | linear-attention Transformer on STFT tokens | ~3 M | `ycq091044/BIOT` (vendored); IIIC 6-class head fine-tuned on HMS |

> Note: the ECG models are **1-D CNNs on the raw 12-lead signal** — **not**
> spectrograms, **not** LSTM. The MRI models are a **CNN (U-Net)** and a
> **Transformer (ViT)**. Echo uses a **2-D CNN** (segmentation) + a **3-D
> spatiotemporal CNN** (EF regression on the video clip). EEG uses **BIOT**, a
> linear-attention **Transformer** over per-channel STFT tokens (a genuinely
> pretrained encoder; only its 6-class IIIC head is fine-tuned).

### Pipeline flow

```
Upload (DRF view, JWT, doctor-scoped)
        │
        ▼
ModelLoader (thread-safe lazy singleton, CUDA/CPU auto-select, weights cached)
        │
        ▼
Preprocess ──▶ Model inference ──▶ Post-process (threshold / argmax / HRV)
                                          │
                                          ▼
                       Structured result envelope {status, …}  ← never raises
                                          │
                          ┌───────────────┴───────────────┐
                          ▼                                ▼
                  MongoDB record                   ReportLab PDF (combined)
```

Key design properties (all real, all defensible):
- **Lazy singleton loader** — first call downloads weights (~700 MB), cached after.
- **Synchronous inference** in the request thread, wrapped in a 5-minute timeout.
  *(Celery/Redis appear in requirements but are **not active** — no task queue.)*
- **Result-envelope contract** — every pipeline returns a plain dict
  `{status, …fields, error?}` and never raises into the view, enabling partial
  results (e.g. ECG reporting 5/7 if a model fails).
- **Doctor isolation** — every database query is scoped to the requesting doctor.

---

## 2.4 Development Environment

### Backend & ML (Python 3.10 / 3.11) — from `requirements.txt`

| Purpose | Library | Version |
|---|---|---|
| Web framework | Django | 3.2.25 (LTS) |
| REST API | djangorestframework | 3.14.0 |
| Auth (JWT) | djangorestframework-simplejwt | 5.3.1 |
| CORS | django-cors-headers | 4.3.1 |
| MongoDB ORM | djongo / pymongo | 1.3.6 / 3.12.3 |
| Config | python-decouple | 3.8 |
| Deep learning | **PyTorch** / torchvision | 2.2.0 / 0.17.0 |
| Transformers | transformers / huggingface-hub | 4.38.0 / 0.20.3 |
| ECG models | **ecglib** | 1.0.1 |
| EEG I/O + models | **MNE** / edfio / linear-attention-transformer (BIOT dep) | 1.12.1 / 0.4.13 / 0.19.1 |
| Signal processing | **SciPy** / NeuroKit2 | 1.11.4 / 0.2.7 |
| Numerics / data | NumPy / pandas | 1.26.4 / 2.1.4 |
| Medical I/O | pydicom / nibabel / wfdb | 2.4.4 / 5.2.0 / 4.1.2 |
| Video decoding (echo) | OpenCV (opencv-python-headless) | 4.9.0 |
| Imaging | Pillow / matplotlib | 10.2.0 / 3.8.2 |
| Medical imaging utils | MONAI | 1.3.0 *(available; pipelines use torch.hub + HF)* |
| PDF reports | ReportLab | 4.0.9 |
| (present, inactive) | Celery / Redis | 5.3.6 / 5.0.1 |

> ❌ **TensorFlow is not used** — the stack is **PyTorch** only.

### Frontend — from `package.json`

| Purpose | Library | Version |
|---|---|---|
| UI framework | React | 19.2 |
| Build tool | Vite | 8.0 |
| Styling | TailwindCSS | 3.4 |
| State | Redux Toolkit / react-redux | 2.12 / 9.3 |
| Routing | react-router-dom | 6.30 |
| HTTP | axios | 1.16 |
| **3D graphics** | **three.js / @react-three/fiber / drei** | 0.184 / 9.6 / 10.7 |
| Charts | chart.js / react-chartjs-2 | 4.5 / 5.3 |
| DICOM (browser) | cornerstone-core / wado-image-loader / dicom-parser | 2.6 / 4.13 / 1.8 |
| Uploads / UX | react-dropzone / react-hot-toast / lucide-react / date-fns | — |

### Datasets & tooling
- Public datasets: PTB-XL, Kaggle Brain-Tumor, LGG, EchoNet-Dynamic, Kaggle HMS (above).
- Reproducible evaluation harnesses (this repo, `tools/`):
  `eval_ecg_classifier.py`, `eval_mri_classifier.py`, `eval_mri_segmentation.py`,
  `eval_echo.py`, and `eval_eeg.py` (+ `train_eeg_head.py` to fine-tune the BIOT
  IIIC head; `eeg_hms.py` shared HMS loader).
- No HDL/hardware simulation tools are used. Sample-data generators
  (`tools/generate_sample_ecg.py`, `download_sample_mri.py`, `generate_sample_eeg.py`)
  produce test inputs.

---

## 2.5 Corrections to a generic Chapter-2 outline (do NOT claim these)

| Generic claim | Reality in this project |
|---|---|
| Clinical-collaboration data | ❌ Only public datasets (PhysioNet/Kaggle) |
| Non-parametric outlier statistics | ❌ → input sanitization + saturation guard |
| Entropy / chaos / complexity | ❌ → time-domain HRV only (entropy optional add-on) |
| Agentic AI framework (agents) | ❌ → modular synchronous pipeline |
| CNN on spectrograms | ❌ → 1-D CNN on raw 12-lead signal |
| LSTM for time series | ❌ → not used |
| TensorFlow | ❌ → PyTorch |
| Simulation tools | ❌ → none (web app + eval scripts) |

**Defensible one-line summary:** *"A modular, PyTorch-based multimodal pipeline
that applies pretrained deep-learning models (U-Net + ViT for brain MRI, a
DenseNet-1D ensemble for 12-lead ECG) on public benchmark data, with SciPy/
NeuroKit2 signal preprocessing and HRV analysis, served through a Django/DRF +
MongoDB backend and a React/Three.js frontend."*
