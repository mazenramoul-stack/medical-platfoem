# Implementation Brief — Add an EEG modality (BIOT + IIIC, 6-class) like ECG/MRI/Echo

> Paste this whole file into a fresh Claude Code chat in this repo, **or** say:
> *"Read docs/EEG-IIIC-MODALITY-BRIEF.md and implement the EEG modality exactly as
> specified, mirroring the existing Echo modality."*
> NOTE: there is also `docs/EEG-MODALITY-BRIEF.md` (a TUEV variant). Use **one**
> EEG brief, not both.

## Goal
Add a fourth analysis modality, **EEG**, to this multimodal medical platform using a
**pretrained** model (no training), wired end-to-end exactly like the existing
**ECG, MRI, and Echo** modalities: backend pipeline + Django app + React frontend +
combined-PDF report + a reproducible validation harness.

## Chosen model: BIOT, multi-class IIIC classification (6 classes)
- **Model:** **BIOT** — Biosignal Transformer (Yang et al., NeurIPS 2023).
  Repo + **pretrained checkpoints**: https://github.com/ycq091044/BIOT
- **Task / head:** the **IIIC** (Ictal–Interictal–Injury Continuum) 6-class
  classifier — the patterns of "harmful brain activity" on continuous EEG:
  1. **SZ** — Seizure
  2. **LPD** — Lateralized Periodic Discharges (focal)
  3. **GPD** — Generalized Periodic Discharges
  4. **LRDA** — Lateralized Rhythmic Delta Activity (focal)
  5. **GRDA** — Generalized Rhythmic Delta Activity
  6. **Other** — none of the above / background
- **Pretrained, no training.** Load BIOT's released IIIC checkpoint; this is the EEG
  analog of using `ecglib` / EchoNet weights.
- **Input:** an EEG `.edf` (read with **MNE**). BIOT classifies fixed-length
  multi-channel segments → a class per segment; aggregate over the recording to
  report which IIIC patterns are present and their proportions over time.

### How BIOT works (so the pipeline is correct)
Resample every channel to **200 Hz** → split each channel into 1-second patches →
each patch becomes a token (linear embedding) + **channel embedding** +
**positional embedding** → **Transformer encoder** → classification head → class
probabilities. It handles variable channels/length via this tokenization.

> ⚠️ **Do not invent preprocessing constants.** Channel montage, segment length,
> resampling and normalization **must match BIOT's IIIC pipeline exactly** — read the
> BIOT repo's IIIC dataset/preprocessing code and replicate it. Guessing wrecks
> accuracy.

## Tumor framing (honest — state it this way)
EEG is the **functional** complement to the **structural** MRI tumor analysis:
MRI answers "is there a mass and what type?"; EEG answers "is brain *function*
disturbed, and how harmful is the pattern?". The **SZ** and **LPD** classes are the
focal/ictal patterns a brain tumor can drive (tumor-related seizures, focal periodic
discharges). **EEG never diagnoses the tumor** — it flags harmful electrical activity
that a tumor (among other acute causes) can cause.

> Extra honesty for IIIC specifically: the IIIC continuum is **critical-care /
> acute-brain-injury EEG** (ICU monitoring), so it is **less tumor-specific** than a
> focal-epileptiform task. Report it as "harmful-brain-activity / functional
> screening that complements MRI," NOT as tumor detection, and note the cohort is
> general critically-ill EEG — not a tumor cohort. (If you want the more directly
> tumor-linked option, the TUEV variant emphasises focal epileptiform patterns.)

## Hard project constraints (do NOT break these)
- **Python 3.10 / 3.11**, **Django 3.2.25 LTS**, MongoDB via djongo (see CLAUDE.md).
- **Result-envelope contract:** every pipeline fn returns `{status, ...fields,
  error?, error_type?}` and **never raises into the view**.
- **Doctor isolation:** every queryset filters by `patient__doctor=request.user`.
- **Dark-neon 3D UI theme** is already in place — reuse the shared components.
- 8-step modality recipe is in `CONTRIBUTING.md`.

## Mirror the Echo modality — freshest, closest template
- Backend pipeline:  `backend/apps/inference/echo_pipeline.py`
- Loader pattern:    `backend/apps/inference/model_loader.py`  (add `get_eeg_model()`
  that builds BIOT and loads the IIIC checkpoint from a configurable path, like
  `get_echo_models`; env var `BIOT_IIIC_WEIGHTS`, default `backend/models_weights/biot/`)
- Django app:        `backend/apps/echo/`
- Registration:      `backend/core/settings.py` (LOCAL_APPS) + `backend/core/urls.py`
- Inference exports: `backend/apps/inference/__init__.py`
- Frontend module:   `frontend/src/modules/Echo/` + `frontend/src/services/echoService.js`
- Reports:           `backend/apps/reports/` + `frontend/src/modules/Reports/ReportGenerator.jsx`
- Validation harness: `tools/eval_echo.py`

## Concrete tasks (the 8-step recipe)

### Backend
1. **`backend/apps/inference/eeg_pipeline.py`** — `analyze_eeg(file_path) -> dict`.
   Read EDF (mne) → preprocess to BIOT/IIIC format (montage, 200 Hz, segment) → run
   BIOT IIIC head per segment → aggregate to per-class proportions over the recording,
   a dominant-pattern summary, an `epileptiform/harmful` flag (any SZ/LPD/GPD), a
   class-distribution + over-time PNG (matplotlib via `save_visualization`), and a
   report. Return the envelope dict; wrap everything in try/except → `{status:'failed',…}`.
2. **`backend/apps/inference/model_loader.py`** — add `get_eeg_model()` (build BIOT,
   load IIIC checkpoint, eval, to(device); clear FileNotFoundError if missing). Vendor
   BIOT's model code into the repo (`backend/apps/inference/biot/`) — no pip package.
3. **`backend/apps/inference/__init__.py`** — export `analyze_eeg`.
4. **`backend/apps/eeg/`** Django app — `EEGAnalysis` model (patient FK CASCADE,
   `file`, `status`, `model_used`, result fields: `result_dominant_pattern`,
   `result_harmful` (Bool: any SZ/LPD/GPD), `result_class_distribution` (JSONField),
   `result_plot_path`, `result_report`, `created_at`). Serializer (+`file_url`,
   `plot_url`), views (`EEGUpload/List/DetailView`, doctor-scoped, validate `.edf` +
   size, run via `run_inference_with_timeout`), urls, admin, migration
   `0001_initial.py` (dep `('patients','0001_initial')`), apps.py (`name='apps.eeg'`,
   `label='eeg'`).
5. **Register**: add `'apps.eeg'` to LOCAL_APPS; add
   `path('api/eeg/', include('apps.eeg.urls'))` to `core/urls.py`.
6. **`backend/requirements.txt`** — add `mne` (+ any BIOT deps from the BIOT repo).

### Frontend (reuse dark-neon components)
7. **`frontend/src/services/eegService.js`** — mirror `echoService.js` (`/eeg/...`).
8. **EEG module** under `frontend/src/modules/EEG/`:
   - `EEGUpload.jsx` (dropzone for `.edf`),
   - `EEGHistory.jsx` (list; badge = dominant pattern / "harmful" flag),
   - `EEGResult.jsx` (class-distribution chart + over-time timeline + per-class table +
     report; highlight harmful classes SZ/LPD/GPD),
   - `EEGLanding.jsx` via shared `components/ModalityLanding.jsx`
     (accent `#a855f7` violet, `model="brain"`, metrics = 6 IIIC patterns / harmful,
     CTA `/patients`).
   - **Replace** the placeholder `frontend/src/modules/EEG/EEGPage.jsx`.
9. **Wire**: `App.jsx` routes `/eeg`→`EEGLanding`, `/eeg/:id`→`EEGResult`;
   `PatientDetail.jsx` add an **EEG tab** + upload modal + `eegList` state/fetch/delete
   (mirror how `echo` was added); `Dashboard.jsx` make the EEG tile functional (live
   count, drop `soon:true`). Sidebar already links `/eeg`.

### Reports
10. `Report.eeg_analysis` FK (SET_NULL) + migration; `ReportGenerateView` accepts
    `eeg_analysis_id`; serializer adds `eeg_analysis`; `pdf_generator.py` gets
    `_eeg_section` (dominant pattern, % per class, harmful flag, distribution image)
    and `__init__` accepts `eeg_analysis`; `ReportGenerator.jsx` + `reportService.js`
    add an EEG selector/param; `PatientDetail` passes `eegOptions`.

### Validation
11. **`tools/eval_eeg.py`** — validate on the **IIIC test set**: run the pipeline on
    test segments, compare to labels → **balanced accuracy, Cohen's κ, macro/weighted
    F1, per-class precision/recall/F1, 6×6 confusion matrix**. If labels are expert
    **vote distributions** (soft labels), also report **KL divergence** (the standard
    IIIC/HMS metric). Mirror `tools/eval_echo.py` (argparse, `--limit`, reproduce line).
    Headline balanced-acc / κ / macro-F1 — not raw accuracy (class imbalance).

## Data & weights
- **Weights:** BIOT IIIC checkpoint from the **BIOT GitHub** (no agreement). Place in
  `backend/models_weights/biot/` (add a README like the echonet one) or set
  `BIOT_IIIC_WEIGHTS`.
- **Validation dataset (pick what matches BIOT's IIIC pipeline):**
  - **Kaggle "HMS – Harmful Brain Activity Classification"** (same 6 classes, expert
    vote labels) — public with a Kaggle account:
    https://www.kaggle.com/competitions/hms-harmful-brain-activity-classification
  - or the original **IIIC dataset** (Westover lab, MGH) if you have access.
  Confirm the format/montage matches BIOT's IIIC preprocessing before trusting numbers.
- **Smoke-test sample:** any `.edf` with EEG channels (MNE sample data, or one IIIC
  record). Verify `analyze_eeg(<edf>)` returns `status: success` with a class
  distribution + plot **before** claiming done.

## Definition of done (match the other modalities)
- `manage.py check` → no issues; `npm run build` → clean.
- `analyze_eeg` verified on a real `.edf` (status success, sensible class output).
- EEG appears in sidebar, dashboard (count), patient detail (tab + upload), result
  page, and the combined PDF report.
- `tools/eval_eeg.py` prints balanced-acc / κ / per-class F1 / confusion (+ KL if soft
  labels) on the IIIC test set.
- Update **VALIDATION.md** (new EEG section: metrics, confusion, dataset, reproduce
  cmd) and **METHODOLOGY.md** (data-sources + models tables: BIOT = pretrained
  biosignal transformer, IIIC 6-class; tools list adds mne + BIOT deps).

## Honesty rules (non-negotiable)
- EEG is the **functional complement to MRI**, not a tumor detector. Say so.
- IIIC is **critical-care EEG**, less tumor-specific than focal-epileptiform tasks —
  report it as harmful-brain-activity screening on a general cohort, not a tumor cohort.
- Hardest modality to integrate (BIOT has no pip package — vendor its model code +
  replicate its exact IIIC preprocessing). Budget for that.

## One-line definition of done
A pretrained 6-class IIIC classifier (BIOT), wrapped in the same modular pipeline +
Django app + dark-neon React module + PDF report + an IIIC validation harness, framed
as the functional brain-screen complementing the MRI tumor analysis, with **real**
metrics and honest scope.
