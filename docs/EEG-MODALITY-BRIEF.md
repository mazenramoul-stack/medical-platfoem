# Implementation Brief — Add an EEG modality (BIOT + TUEV, 6-class) like ECG/MRI/Echo

> ⚠️ **SUPERSEDED — this is NOT what was built.** This brief describes an earlier
> plan: BIOT **TUEV** 6-class (SPSW/PLED/GPED/EYEM/ARTF/BCKG), "pretrained, no
> training". The platform actually ships BIOT **IIIC** 6-class harmful-brain-activity
> screening (SZ/LPD/GPD/LRDA/GRDA/Other) with a head **fine-tuned in-repo** on Kaggle
> HMS (the encoder is frozen; BIOT does not release an IIIC head). For the real design
> see **[EEG-IIIC-MODALITY-BRIEF.md](EEG-IIIC-MODALITY-BRIEF.md)** and VALIDATION.md §5.
> This file is kept only as a historical planning artifact — ignore its model/class/
> "no training" claims.

> Paste this whole file into a fresh Claude Code chat in this repo, **or** say:
> *"Read docs/EEG-MODALITY-BRIEF.md and implement the EEG modality exactly as
> specified, mirroring the existing Echo modality."*

## Goal
Add a fourth analysis modality, **EEG**, to this multimodal medical platform using a
**pretrained** model (no training), wired end-to-end exactly like the existing
**ECG, MRI, and Echo** modalities: backend pipeline + Django app + React frontend +
combined-PDF report + a reproducible validation harness.

## Chosen model: BIOT, multi-class EEG event classification (TUEV, 6 classes)
- **Model:** **BIOT** — Biosignal Transformer (Yang et al., NeurIPS 2023).
  Repo + **pretrained checkpoints**: https://github.com/ycq091044/BIOT
- **Task / head:** the **TUEV** 6-class EEG-event classifier. Classes:
  1. **SPSW** — spike & sharp wave (epileptiform)
  2. **PLED** — periodic lateralized epileptiform discharges (focal)
  3. **GPED** — generalized periodic epileptiform discharges
  4. **EYEM** — eye movement (artifact)
  5. **ARTF** — artifact
  6. **BCKG** — background (normal activity)
- **Pretrained, no training.** Load BIOT's released TUEV checkpoint; this is the
  EEG analog of using `ecglib` / EchoNet weights.
- **Input:** an EEG `.edf` (read with **MNE**). BIOT classifies fixed-length
  multi-channel segments → a class per segment. Aggregate over the recording to
  report which event types are present and their proportions.

### How BIOT works (so the pipeline is correct)
Resample every channel to **200 Hz** → split each channel into 1-second patches →
each patch becomes a token (linear embedding) + **channel embedding** +
**positional embedding** → **Transformer encoder** → classification head → class
probabilities. It handles variable channels/length via this tokenization.

> ⚠️ **Do not invent the preprocessing constants.** Channel selection (the 16-channel
> TUH montage), segment length, resampling, and normalization **must match BIOT's
> TUEV pipeline exactly** — read the BIOT repo's TUEV dataset/preprocessing code and
> replicate it. Guessing will silently wreck accuracy.

## Tumor framing (honest — state it this way)
EEG is the **functional** complement to the **structural** MRI tumor analysis:
MRI answers "is there a mass and what type?"; EEG answers "is brain *function*
disturbed?". Two of the TUEV classes — **SPSW** and **PLED** — are exactly the
focal/epileptiform patterns a brain tumor can produce (tumor-related epilepsy,
focal irritative activity). **EEG never diagnoses the tumor** — it flags abnormal
function that a tumor (among other causes: stroke, encephalitis…) can cause. Do not
claim EEG detects tumors. TUEV is general clinical EEG, **not** a tumor cohort, so
report it as functional-abnormality screening, not tumor classification.

## Hard project constraints (do NOT break these)
- **Python 3.10 / 3.11**, **Django 3.2.25 LTS**, MongoDB via djongo (see CLAUDE.md).
- **Result-envelope contract:** every pipeline fn returns `{status, ...fields,
  error?, error_type?}` and **never raises into the view**.
- **Doctor isolation:** every queryset filters by `patient__doctor=request.user`.
- **Dark-neon 3D UI theme** is already in place — reuse the shared components.
- 8-step modality recipe is in `CONTRIBUTING.md`.

## Mirror the Echo modality — freshest, closest template
- Backend pipeline:  `backend/apps/inference/echo_pipeline.py`
- Loader pattern:    `backend/apps/inference/model_loader.py`  (add a `get_eeg_model()`
  that builds the BIOT model and loads the TUEV checkpoint from a configurable path,
  like `get_echo_models`; env var `BIOT_TUEV_WEIGHTS`, default
  `backend/models_weights/biot/`)
- Django app:        `backend/apps/echo/`  (models, serializers, views, urls, admin,
  migrations/0001_initial.py, apps.py)
- Registration:      `backend/core/settings.py` (LOCAL_APPS) + `backend/core/urls.py`
- Inference exports: `backend/apps/inference/__init__.py`
- Frontend module:   `frontend/src/modules/Echo/` + `frontend/src/services/echoService.js`
- Reports:           `backend/apps/reports/` + `frontend/src/modules/Reports/ReportGenerator.jsx`
- Validation harness: `tools/eval_echo.py`

## Concrete tasks (the 8-step recipe)

### Backend
1. **`backend/apps/inference/eeg_pipeline.py`** — `analyze_eeg(file_path) -> dict`.
   Read EDF (mne) → preprocess to BIOT/TUEV format (16-ch, 200 Hz, segment) → run
   BIOT TUEV head per segment → aggregate to per-class counts/percentages over the
   recording, a dominant/abnormal-finding summary, a class-distribution PNG
   (matplotlib via `save_visualization`), and a report. Return the envelope dict;
   wrap everything in try/except → `{status:'failed', ...}`.
2. **`backend/apps/inference/model_loader.py`** — add `get_eeg_model()` (build BIOT,
   load TUEV checkpoint, eval, to(device); raise a clear FileNotFoundError if the
   checkpoint is missing). Include the BIOT model code in the repo
   (`backend/apps/inference/biot/` or vendored) since there's no pip package.
3. **`backend/apps/inference/__init__.py`** — export `analyze_eeg`.
4. **`backend/apps/eeg/`** Django app — `EEGAnalysis` model (patient FK CASCADE,
   `file`, `status`, `model_used`, result fields: `result_dominant_event`,
   `result_epileptiform` (Bool: any SPSW/PLED/GPED), `result_class_distribution`
   (JSONField), `result_plot_path`, `result_report`, `created_at`). Serializer
   (+`file_url`,`plot_url`), views (`EEGUploadView/ListView/DetailView`, doctor-scoped,
   validate `.edf` + size, run via `run_inference_with_timeout`), urls, admin,
   migration `0001_initial.py` (dep `('patients','0001_initial')`), apps.py
   (`name='apps.eeg'`, `label='eeg'`).
5. **Register**: add `'apps.eeg'` to LOCAL_APPS; add
   `path('api/eeg/', include('apps.eeg.urls'))` to `core/urls.py`.
6. **`backend/requirements.txt`** — add `mne` (and any BIOT deps: typically `torch`
   already present, plus whatever BIOT needs, e.g. `linear_attention_transformer` —
   check the BIOT repo's requirements).

### Frontend (reuse dark-neon components)
7. **`frontend/src/services/eegService.js`** — mirror `echoService.js` (`/eeg/...`).
8. **EEG module** under `frontend/src/modules/EEG/`:
   - `EEGUpload.jsx` (dropzone for `.edf`),
   - `EEGHistory.jsx` (list; badge = dominant event / "epileptiform" flag),
   - `EEGResult.jsx` (class-distribution chart + per-class table + report; highlight
     epileptiform classes SPSW/PLED/GPED),
   - `EEGLanding.jsx` via shared `components/ModalityLanding.jsx`
     (accent `#a855f7` violet, `model="brain"`, metrics = 6 classes / epileptiform,
     CTA `/patients`).
   - **Replace** the placeholder `frontend/src/modules/EEG/EEGPage.jsx`.
9. **Wire**: `App.jsx` routes `/eeg`→`EEGLanding`, `/eeg/:id`→`EEGResult`;
   `PatientDetail.jsx` add an **EEG tab** + upload modal + `eegList` state/fetch/delete
   (mirror how `echo` was added); `Dashboard.jsx` make the EEG tile functional (live
   count, drop `soon:true`). Sidebar already links `/eeg`.

### Reports
10. `Report.eeg_analysis` FK (SET_NULL) + migration; `ReportGenerateView` accepts
    `eeg_analysis_id`; serializer adds `eeg_analysis`; `pdf_generator.py` gets
    `_eeg_section` (dominant event, % per class, epileptiform flag, distribution
    image) and `__init__` accepts `eeg_analysis`; `ReportGenerator.jsx` +
    `reportService.js` add an EEG selector/param; `PatientDetail` passes `eegOptions`.

### Validation
11. **`tools/eval_eeg.py`** — validate on **TUEV test split**: run the pipeline on
    test segments, compare to labels → **balanced accuracy, Cohen's κ, weighted-F1,
    per-class precision/recall/F1, 6×6 confusion matrix**. Mirror `tools/eval_echo.py`
    (argparse, `--limit`, reproduce line). Note class imbalance — headline
    balanced-accuracy / weighted-F1 / κ, not raw accuracy.

## Data & weights
- **Weights:** BIOT TUEV checkpoint from the **BIOT GitHub** (no agreement). Place in
  `backend/models_weights/biot/` (add a README like the echonet one) or set
  `BIOT_TUEV_WEIGHTS`.
- **Validation dataset:** **TUH EEG Events (TUEV)** —
  https://isip.piconepress.com/projects/tuh_eeg/ (free **TUH data-use agreement**).
  Download, give the new chat the path, run `python tools/eval_eeg.py <TUEV root>`.
- **Smoke-test sample:** any `.edf` with EEG channels (MNE sample data, or one TUEV
  record). Verify `analyze_eeg(<edf>)` returns `status: success` with a class
  distribution + plot **before** claiming done.

## Definition of done (match the other modalities)
- `manage.py check` → no issues; `npm run build` → clean.
- `analyze_eeg` verified on a real `.edf` (status success, sensible class output).
- EEG appears in sidebar, dashboard (count), patient detail (tab + upload), result
  page, and the combined PDF report.
- `tools/eval_eeg.py` prints balanced-acc / κ / per-class F1 / confusion on TUEV.
- Update **VALIDATION.md** (new EEG section: balanced-acc, κ, per-class F1, confusion,
  dataset, reproduce cmd) and **METHODOLOGY.md** (data-sources + models tables: BIOT =
  pretrained biosignal transformer, TUEV 6-class; tools list adds mne + BIOT deps).

## Honesty rules (non-negotiable)
- EEG is the **functional complement to MRI**, not a tumor detector. Say so.
- TUEV is general clinical EEG — **report real TUEV metrics**, do not fabricate, and
  do not claim a tumor-specific cohort.
- Hardest modality to integrate (BIOT has no pip package — vendor its model code +
  replicate its exact preprocessing). Budget for that.

## One-line definition of done
A pretrained 6-class EEG-event classifier (BIOT/TUEV), wrapped in the same modular
pipeline + Django app + dark-neon React module + PDF report + a TUEV validation
harness, framed as the functional brain-screen complementing the MRI tumor analysis,
with **real** metrics and honest scope.
