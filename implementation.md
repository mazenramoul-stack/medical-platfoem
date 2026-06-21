# Implementation — Multimodal Medical AI Platform

> **Complete implementation reference** for the PFE platform: every layer (frontend + backend),
> every AI model and where it lives, every pipeline and its functions, the file locations, the
> data flow, the weights, the tests and the tooling. This is the "where is everything and how is it
> wired" map — for runtime *behaviour/accuracy* see `maybe read/VALIDATION.md`, for the *narrative*
> see [The Final Result - Mazen PFE.md](The%20Final%20Result%20-%20Mazen%20PFE.md).

---

## 0. Tech stack (pinned)

| Layer | Tech | Notes |
|---|---|---|
| Backend framework | **Django 3.2.25 LTS** + **DRF 3.14** | Django 4.x is incompatible with djongo — deliberate downgrade |
| Auth | **SimpleJWT** (email login, 1 h access / 7 d refresh) | role embedded in the token |
| Database | **MongoDB** via **djongo 1.3.6** | needs **Python 3.10 / 3.11** (djongo breaks on 3.12+) |
| ML | **PyTorch**, **torchvision**, **monai**, **transformers**, **huggingface-hub**, **ecglib 1.0.1**, **captum 0.7.x**, **mne**, **neurokit2** | CPU-compatible, GPU auto-detected |
| Frontend | **React 19 + Vite 8 + Tailwind 3.4 + Redux Toolkit** | port **3000** (`strictPort`) |
| 3D | **react-three-fiber** + **drei** + **three** | procedural Brain/Heart scenes |
| PDF | **ReportLab** | combined report generator |
| Deploy | HF Docker Space (backend :7860) · Vercel (frontend) · MongoDB Atlas | local dev = `runserver` + `npm run dev` |

Backend deps are split: `backend/requirements-core.txt` (Django/DRF/djongo) + `backend/requirements.txt`
(the heavy ML stack). Install `requirements.txt` to run inference.

---

## 1. Repository layout (top level)

```
medical-platform/
├── backend/                 Django project (API + inference engine)
│   ├── core/                project config (settings, urls, wsgi/asgi, media, health)
│   ├── apps/                the Django apps (one per concern) — see §3
│   ├── models_weights/      on-disk model checkpoints (Echo/EEG/finetuned — not all bundled)
│   ├── media/               uploads + generated artefacts (overlays, plots, PDFs)
│   ├── tests/               DB-backed test suites + seed_database.py
│   ├── manage.py            Django entry point
│   ├── requirements*.txt    core vs full(ML) deps
│   └── venv/                local virtualenv (Scripts/python.exe)
├── frontend/                React + Vite SPA
│   └── src/                 modules, services, store, hooks, theme, i18n, components — see §8
├── tools/                   eval_*.py harnesses + sample generators + training scripts
├── Colab PFE/               GPU fine-tune notebooks (MRI Swin, ECG, EEG) + lean-zip builder
├── maybe read/              non-runtime docs (VALIDATION, TESTING, METHODOLOGY, …)
├── docs/                    per-modality briefs + functionality walkthroughs
├── deploy/huggingface/      Dockerfile + Space README (cloud backend)
├── Test Samples/            sample MRI/ECG/etc. inputs
├── start.bat / stop.bat     Windows one-click launchers (+ .ps1)
└── *.md                     thesis/report prose drafts
```

---

# PART A — BACKEND

## 2. Project config — `backend/core/`

| File | Responsibility |
|---|---|
| [core/settings.py](backend/core/settings.py) | All config via **python-decouple** (`config(...)` reads `backend/.env`). Registers apps as `apps.<name>`; SimpleJWT lifetimes; DRF throttles; **swaps DB to in-memory SQLite when `'test' in sys.argv`**; `MONGO_URI` (Atlas `mongodb+srv://`) detection vs local host/port |
| [core/urls.py](backend/core/urls.py) | Root URLconf — mounts every app prefix (see §2.1) + the signed-media route + drf-spectacular schema/docs |
| [core/media.py](backend/core/media.py) | **HMAC-signed, time-limited media** — `signed_media_url(request, rel)` mints short-lived URLs; `serve_signed_media` validates the signature. The API **never** returns a raw `/media/` path |
| [core/health.py](backend/core/health.py) | `GET /api/health/` liveness probe |
| [core/wsgi.py](backend/core/wsgi.py) / [core/asgi.py](backend/core/asgi.py) | servers (gunicorn binds wsgi in prod) |

### 2.1 URL prefixes (`core/urls.py`)

```
api/health/                health
api/auth/                  → apps.authentication   (login, register, refresh, me, doctors)
api/                       → apps.patients         (patient CRUD + /history/)
api/mri/                   → apps.mri              (upload, list, detail, explain)
api/ecg/                   → apps.ecg
api/echo/                  → apps.echo
api/eeg/                   → apps.eeg
api/convert/               → apps.conversion       (technician-only file conversion)
api/reports/               → apps.reports
api/schema/ api/docs/ api/redoc/   OpenAPI (drf-spectacular)
media/<path>               serve_signed_media (signature-checked PHI)
```

## 3. The request lifecycle (how one analysis flows)

```
1. AUTH      Doctor/tech logs in → JWT (role + email + full_name claims). Axios attaches it.
2. UPLOAD    POST /api/<modality>/upload/  multipart {patient_id, file}
3. SCOPE     get_patient_or_404(user, patient_id)  ← apps/patients/access.py (assignment-based)
4. PERSIST   create <Modality>Analysis(status=PROCESSING)
5. INFERENCE run_inference_with_timeout(analyze_<modality>, file_path, TIMEOUT)
                → lazy ModelLoader singleton returns cached model(s)
                → pipeline returns the ENVELOPE dict {status, ...fields, error?, error_type?}
6. SAVE      copy envelope fields onto the record; status=COMPLETED|FAILED; save artefact paths
7. RESPOND   serializer returns the record (artefact paths → signed URLs); 201 or 202
8. EXPLAIN   (optional) POST /api/<modality>/{id}/explain/ → explain_<modality>() → signed SHAP URL
9. REPORT    POST /api/reports/generate/ {patient_id, analysis ids} → ReportLab PDF (streamed)
```

**Two invariants enforced everywhere:**
1. **Assignment-based isolation** — every queryset over patient-owned data is scoped through
   [apps/patients/access.py](backend/apps/patients/access.py); a foreign id → **404**.
2. **Result envelope** — pipelines return `{status, ...}` and **never raise into the view**, so the API
   reports partial/failed results instead of 500-ing.

---

## 4. App-by-app reference — `backend/apps/`

Every app is registered as `apps.<name>` (its `apps.py` sets `name = 'apps.<name>'`).

### 4.1 `apps/authentication` — users, roles, JWT

| File | Contents |
|---|---|
| [models.py](backend/apps/authentication/models.py) | `User(AbstractBaseUser, PermissionsMixin)` — email login, `full_name`, **`role`** (`Role.DOCTOR` / `Role.TECHNICIAN`), `is_active`, `is_staff`. `UserManager.create_user` / `create_superuser` (superuser defaults to **technician** app role; `is_staff`/`is_superuser` gate Django admin only) |
| [serializers.py](backend/apps/authentication/serializers.py) | `UserSerializer`, `DoctorSerializer` (assignment picker), `UserRegistrationSerializer` (role = `ChoiceField{doctor,technician}`, strips staff/superuser), `EmailTokenObtainPairSerializer` (embeds `role`/`email`/`full_name` in the JWT) |
| [permissions.py](backend/apps/authentication/permissions.py) | **`IsTechnician`** — the real server-side gate for technician-only endpoints |
| [views.py](backend/apps/authentication/views.py) | `RegisterView`, `LoginView`, `RefreshView`, `LogoutView` (blacklist refresh), `MeView`, `DoctorListView` (`GET /api/auth/doctors/`, `IsTechnician`) |
| migrations | `0001_initial`, `0002_rename_admin_role_to_technician` (data-migrates old `admin` rows → `technician`) |

### 4.2 `apps/patients` — patients + the isolation contract

| File | Contents |
|---|---|
| [models.py](backend/apps/patients/models.py) | `Patient` (full_name, age, gender, medical_history, `created_by` = lineage only) + **`PatientAssignment`** (plain join: `patient` ↔ `doctor`, `assigned_by`, `assigned_at`, `unique_together`) |
| [access.py](backend/apps/patients/access.py) | ⭐ **single source of truth for visibility**: `visible_patient_ids(user)` (None = technician = all), `scope_patients`, `scope_by_patient`, `get_patient_or_404`. Uses shallow `id__in` (djongo-safe) |
| [serializers.py](backend/apps/patients/serializers.py) | `PatientSerializer` — read `doctors`; write `doctor_ids` (**technician-only**, validated; doctor self-registering auto-assigns to self) |
| [views.py](backend/apps/patients/views.py) | `PatientViewSet` (queryset = `scope_patients(user)`) + `@action history` (per-patient MRI/ECG/Echo/EEG aggregate) |

### 4.3 The four modality apps — `apps/{mri,ecg,echo,eeg}`

All four share the same shape. Files: `models.py`, `serializers.py`, `views.py`, `urls.py`, `admin.py`.

**Endpoints (each modality):**
```
POST   /api/<m>/upload/        multipart {patient_id, file} → synchronous inference
GET    /api/<m>/?patient_id=   list (scoped)
GET    /api/<m>/{id}/          retrieve
DELETE /api/<m>/{id}/          delete record + on-disk artefacts
POST   /api/<m>/{id}/explain/  on-demand SHAP (signed URL)   ← all four
```

**Views (class names):**
- MRI: `MRIUploadView`, `MRIListView`, `MRIDetailView`, **`MRIExplainView`** ([views.py](backend/apps/mri/views.py))
- ECG: `ECGUploadView`, `ECGListView`, `ECGDetailView`, **`ECGExplainView`** ([views.py](backend/apps/ecg/views.py))
- Echo: `EchoUploadView`, `EchoListView`, `EchoDetailView`, **`EchoExplainView`** ([views.py](backend/apps/echo/views.py))
- EEG: `EEGUploadView`, `EEGListView`, `EEGDetailView`, **`EEGExplainView`** ([views.py](backend/apps/eeg/views.py))

**Models (result fields persisted from the envelope):**

| App | Model | Key result fields |
|---|---|---|
| mri | `MRIAnalysis` | `result_tumor_detected`, `result_tumor_type`, `result_confidence`, `result_segmentation_confidence`, `result_class_probabilities` (JSON), `result_mask_path`, `result_overlay_path`, `result_analysis_path`, **`result_gradcam_path`**, `result_report`, `status`, `model_used` |
| ecg | `ECGAnalysis` | `result_arrhythmia_detected`, `result_arrhythmia_type`, `result_confidence`, `result_hrv_metrics` (JSON), `result_pathology_probabilities` (JSON), `result_plot_path`, `result_report` |
| echo | `EchoAnalysis` | `result_ef`, `result_ef_category`, `result_ed_area`, `result_es_area`, `result_overlay_path`, `result_report` |
| eeg | `EEGAnalysis` | `result_dominant_pattern`, `result_harmful`, `result_class_distribution` (JSON), `result_plot_path`, `result_report` |

All four have a `Status` TextChoices (`PENDING/PROCESSING/COMPLETED/FAILED`), a `patient` FK, an upload
`file`, and `created_at`. Upload caps/timeouts live as constants in each `views.py`
(e.g. EEG: `.edf` only, 200 MB, 600 s; MRI/ECG smaller).

### 4.4 `apps/conversion` — technician-only file conversion (NEW)

| File | Contents |
|---|---|
| [views.py](backend/apps/conversion/views.py) | `ConvertView` (`IsTechnician`, multipart). `POST /api/convert/<modality>/` → dispatches to a converter, returns the standardized file as an **attachment download** (no DB record). 500 MB cap; temp-dir; structured error envelope on bad input (never 500) |
| [urls.py](backend/apps/conversion/urls.py) | regex route restricts modality to `mri\|ecg\|echo\|eeg` |
| [converters/base.py](backend/apps/conversion/converters/base.py) | `ConversionError`, `detected_extension`, `output_path_for`, `to_uint8`, `unzip_to_dir` (zip-slip guard), `find_files` |
| [converters/__init__.py](backend/apps/conversion/converters/__init__.py) | `CONVERTERS = {mri, ecg, echo, eeg}` dispatch map |
| [converters/mri.py](backend/apps/conversion/converters/mri.py) | DICOM (`.dcm` / `.zip` series) · NIfTI → **8-bit PNG** (slice select, rescale slope/intercept) |
| [converters/ecg.py](backend/apps/conversion/converters/ecg.py) | DICOM ECG `WaveformSequence` → **12-lead CSV @ 500 Hz** (derives III/aVR/aVL/aVF from I & II) |
| [converters/echo.py](backend/apps/conversion/converters/echo.py) | DICOM cine / video → **MP4** (pydicom/OpenCV, YBR→RGB) |
| [converters/eeg.py](backend/apps/conversion/converters/eeg.py) | BrainVision/.bdf/.set (or `.zip`) → **EDF** (via MNE) |

Each converter is a pure function `convert(input_path, **params) -> (out_path, meta)`; heavy libs
imported lazily.

### 4.5 `apps/reports` — combined PDF

| File | Contents |
|---|---|
| [views.py](backend/apps/reports/views.py) | `ReportGenerateView` (`POST /generate/` — composes a PDF from a patient + chosen analysis ids), `ReportListView`, `ReportDetailView`, `ReportDownloadView` |
| [models.py](backend/apps/reports/models.py) | `Report` — `patient` FK + nullable `mri/ecg/echo/eeg_analysis` FKs + `pdf_file`. **Survives patient deletion** (null FK) |
| [pdf_generator.py](backend/apps/reports/pdf_generator.py) | `MedicalReportGenerator` (the builder), `NumberedCanvas`, **`_ascii()`** (Helvetica box-glyph substitution — don't remove), `_sized_image`, `_parse_mri_extras`, `_mri_recommendation` |
| [management/commands/cleanup_media.py](backend/apps/reports/management/commands/cleanup_media.py) | `manage.py cleanup_media --days N [--delete]` retention |

### 4.6 `apps/inference` — the inference engine ⭐

The heart of the platform. Files:

| File | Contents |
|---|---|
| [__init__.py](backend/apps/inference/__init__.py) | Public API: re-exports `analyze_*`/`explain_*`, `ModelLoader`, and **`run_inference_with_timeout(func, file_path, timeout=300)`** (runs the pipeline on a worker thread with a hard wall-clock timeout) |
| [model_loader.py](backend/apps/inference/model_loader.py) | **`ModelLoader`** process-wide singleton (see §5) — lazy, cached, device-aware getters + `warmup()` |
| [mri_pipeline.py](backend/apps/inference/mri_pipeline.py) | `analyze_mri`, `explain_mri` + helpers (see §6.1) |
| [ecg_pipeline.py](backend/apps/inference/ecg_pipeline.py) | `analyze_ecg`, `explain_ecg` + helpers (see §6.2) |
| [echo_pipeline.py](backend/apps/inference/echo_pipeline.py) | `analyze_echo`, `explain_echo` + helpers (see §6.3) |
| [eeg_pipeline.py](backend/apps/inference/eeg_pipeline.py) | `analyze_eeg`, `explain_eeg` + helpers (see §6.4) |
| [utils.py](backend/apps/inference/utils.py) | `load_image_universal`, `load_ecg_signal` (+ `_canon_lead`, `_reorder_to_canonical`), `generate_unique_filename`, `save_visualization` |
| [eeg_preprocess.py](backend/apps/inference/eeg_preprocess.py) | BIOT train/inference-parity preprocessing: `edf_to_bipolar`, `normalize_segment`, `central_segment`, `segment_recording`, `stack_segments`, `hms_parquet_to_bipolar` |
| [biot/biot.py](backend/apps/inference/biot/biot.py) | Vendored BIOT: `BIOTEncoder`, `BIOTClassifier`, `PatchFrequencyEmbedding`, `ClassificationHead`, `PositionalEncoding` |
| [explainers/](backend/apps/inference/explainers/) | Grad-CAM + SHAP (see §7) |

---

## 5. The AI models — what, where, how loaded

All models are owned by the **`ModelLoader`** singleton ([model_loader.py](backend/apps/inference/model_loader.py)):
one process-wide instance, **lazy** (loads on first request), **cached**, **device-aware** (`get_device()`
→ cuda/cpu). `warmup()` pre-loads **MRI + ECG only** (Echo/EEG weights aren't bundled).

| Modality | Model(s) | Type / params | Loader method | Weights source / path | Fine-tuned? |
|---|---|---|---|---|---|
| **MRI seg** | U-Net | 2-D CNN, ~7.7M | `get_mri_segmentation_model()` | torch.hub `mateuszbuda/brain-segmentation-pytorch` (~30 MB, auto-download) | No (bug-fixed) |
| **MRI cls** | Swin-T | Transformer, ~28M, 4-class | `get_mri_classifier()` → `(processor, model)` | HF `Devarshi/Brain_Tumor_Classification`; **local override** `models_weights/vit_brain_tumor/` (`VIT_BRAIN_TUMOR_WEIGHTS`) | **Yes** (95.4%) |
| **ECG ×7** | DenseNet-1D-121 | 1-D CNN, ~8M each | `get_ecg_models()` → `{code: model}` | ecglib 1.0.1 pretrained; **local override** `models_weights/ecg_finetuned/<P>.pt` (`ECG_FINETUNED_DIR`) | **6/7** |
| **Echo seg** | DeepLabV3-ResNet50 | 2-D CNN, ~40M | `get_echo_models()` → `(seg, ef)` | **not bundled** `models_weights/echonet/echonet_seg.pt` (`ECHONET_SEG_WEIGHTS`) | No |
| **Echo EF** | R(2+1)D-18 | 3-D CNN regressor | `get_echo_models()` | **not bundled** `echonet_ef.pt` (`ECHONET_EF_WEIGHTS`) | No |
| **EEG** | BIOT + IIIC head | linear-attn Transformer, ~3M, 6-class | `get_eeg_model()` | encoder bundled `models_weights/biot/EEG-PREST-16-channels.ckpt` (`BIOT_ENCODER_WEIGHTS`); **head not bundled** `biot_iiic.pt` (`BIOT_IIIC_WEIGHTS`) | **head only** |

**Pathology codes (ECG, in load order):** `AFIB, 1AVB, STACH, SBRAD, RBBB, LBBB, PVC` (7/7 load).
**Swin classes (fixed id2label):** `glioma=0, meningioma=1, no_tumor=2, pituitary=3`.
**IIIC classes (EEG):** `SZ, LPD, GPD, LRDA, GRDA, Other` (first three = "harmful").

> **Local-weights rule (all 3 fine-tunable models):** a local checkpoint is used **only if it exists and
> is valid**, else the loader falls back to stock and logs a warning — fine-tuning can never break a
> deploy. Missing Echo/EEG head weights raise a clear `FileNotFoundError` (expected on a fresh checkout).
> Caches: `~/.cache/torch/hub/`, `~/.cache/huggingface/`.

---

## 6. The pipelines — function by function

Every `analyze_*` returns the envelope `{status, ...fields, error?, error_type?}`; every `explain_*`
returns `{status, ..., shap_path/gradcam_path}`. None raise into the view.

### 6.1 MRI — [mri_pipeline.py](backend/apps/inference/mri_pipeline.py)

| Function | Role |
|---|---|
| **`analyze_mri(file_path, mode='full')`** | Full two-stage pipeline → envelope |
| `extract_bounding_box_crop(image_rgb, mask)` | crop the tumour region from the U-Net mask before classifying |
| `_normalize_tumor_label(t)` | canonicalise class names |
| `generate_clinical_note(type, detected, conf)` | textual report line |
| `compute_model_agreement(...)` | cross-check seg vs cls |
| **`explain_mri(file_path)`** | Grad-CAM **+** SHAP pass → signed overlays |

**Flow:** `load_image_universal` → U-Net forward (**no second sigmoid** — the fix) → probability mask →
`extract_bounding_box_crop` → Swin processor (224², ImageNet norm) → 4-class argmax + confidence →
inline Grad-CAM overlay + normalized peak `{nx, ny}`.

### 6.2 ECG — [ecg_pipeline.py](backend/apps/inference/ecg_pipeline.py)

| Function | Role |
|---|---|
| **`analyze_ecg(file_path)`** | run 7 classifiers + HRV + plot → envelope |
| `classify_hr(hr)` | heart-rate band |
| `format_pathology_table(results)` | textual table |
| `_scalar_probability(out)` | squeeze model output → float |
| `_safe_number` / `_sanitize` | JSON-safe envelope |
| `_render_ecg_shap_figure(...)` | SHAP plot |
| **`explain_ecg(file_path, pathology=None)`** | per-pathology GradientShap + per-lead importance |

**Flow:** `load_ecg_signal` (canonical 12-lead order, 500 Hz) → each DenseNet-1D → probability →
**per-pathology calibrated threshold** (`ECG_THRESHOLD_MODE=f1|recall`) → NeuroKit2 HRV
(RMSSD/SDNN/pNN50, lead II) → signal plot with R-peaks.

### 6.3 Echo — [echo_pipeline.py](backend/apps/inference/echo_pipeline.py)

| Function | Role |
|---|---|
| **`analyze_echo(file_path)`** | EF + LV segmentation → envelope |
| `load_echo_video(path, size=112)` / `_normalize` | decode + EchoNet normalisation |
| `_predict_ef(ef_model, ...)` | R(2+1)D-18 EF over clips (averaged) |
| `_predict_segmentation(seg_model, ...)` | DeepLabV3 LV mask (batched) |
| `_ef_category(ef)` / `_reduced_ef_screen(ef)` | clinical band / screen flag (`REDUCED_EF_SCREEN_CUTOFF`) |
| `_build_ef_clip` / `_render_echo_shap_figure` | clip builder / SHAP montage |
| **`explain_echo(file_path, n_samples=8)`** | spatiotemporal GradientShap + per-frame importance |

### 6.4 EEG — [eeg_pipeline.py](backend/apps/inference/eeg_pipeline.py)

| Function | Role |
|---|---|
| **`analyze_eeg(file_path)`** | per-10 s 6-class → aggregate distribution + dominant + harmful flag |
| `_predict_segments(model, x, device)` | classify every segment |
| `_build_visualization(...)` | class distribution / timeline plot |
| `_resolve_target_class(value)` | name/index → IIIC class index |
| `_render_eeg_shap_figure(...)` | SHAP plot |
| **`explain_eeg(file_path, target_class=None)`** | GradientShap + per-channel importance |

**Preprocessing parity** ([eeg_preprocess.py](backend/apps/inference/eeg_preprocess.py)): 16-channel
longitudinal-bipolar montage → resample 200 Hz → 10 s = 2000-sample segments → per-channel
95th-percentile amplitude normalisation. Same code used by training and inference.

---

## 7. The explainers — [apps/inference/explainers/](backend/apps/inference/explainers/)

| File | Functions | What |
|---|---|---|
| [gradcam.py](backend/apps/inference/explainers/gradcam.py) | `swin_gradcam(processor, model, pil, target)`, `_resolve_target_layer` | Grad-CAM on the Swin **final LayerNorm** (token seq `[B,L,C]` → `side×side` grid; no conv map) |
| [shap_attr.py](backend/apps/inference/explainers/shap_attr.py) | `swin_gradient_shap(...)` | MRI Captum GradientShap (multi-class target) |
| [ecg_shap.py](backend/apps/inference/explainers/ecg_shap.py) | `ecg_gradient_shap(model, signal)`, `per_lead_importance` | 1-D ECG, single-sigmoid `target=0`, → per-lead |
| [echo_shap.py](backend/apps/inference/explainers/echo_shap.py) | `echo_gradient_shap(ef_model, clip)`, `frame_importance` | 3-D EF regressor `target=0`, → per-frame |
| [eeg_shap.py](backend/apps/inference/explainers/eeg_shap.py) | `eeg_gradient_shap(model, signal, target_class)`, `per_channel_importance` | 6-class BIOT (STFT differentiable), → per-channel |
| [base.py](backend/apps/inference/explainers/base.py) | `resize_to`, `heatmap_peak_xy`, `attribution_agreement` (Spearman + top-k IoU at coarser grid), `gradcam_overlay_figure` | shared helpers |

**Shared design:** Captum **GradientShap** (KernelSHAP/LIME infeasible on CPU at these dims); two-point
baseline (zeros + signal-mean); **must run outside `torch.no_grad()`**; **not thread-safe** (backprops on
the shared singleton — safe only because inference is synchronous); output = normalised [0,1] saliency.

---

# PART B — FRONTEND (`frontend/src/`)

## 8.1 Entry, routing, layout

| File | Role |
|---|---|
| [main.jsx](frontend/src/main.jsx) | React root; wraps Redux `store`, `ThemeProvider`, `LanguageProvider`, router |
| [App.jsx](frontend/src/App.jsx) | **Routes**. Public `/login`, `/register`; protected (via `ProtectedRoute` + `DashboardLayout`): `/`, `/patients[...]`, `/mri[/:id]`, `/ecg`, `/eeg`, `/echo`, `/reports[...]`; **`/convert` rendered only for technicians** |
| [components/ProtectedRoute.jsx](frontend/src/components/ProtectedRoute.jsx) | redirect to `/login` if unauthenticated |
| [components/Layout/DashboardLayout.jsx](frontend/src/components/Layout/DashboardLayout.jsx), [Sidebar.jsx](frontend/src/components/Layout/Sidebar.jsx), [Navbar.jsx](frontend/src/components/Layout/Navbar.jsx) | shell; Sidebar adds the **Convert** link only for `role==='technician'` |
| [components/ErrorBoundary.jsx](frontend/src/components/ErrorBoundary.jsx) | the one allowed class component |

## 8.2 Services (`frontend/src/services/`) — REST wrappers

| File | Wraps |
|---|---|
| [api.js](frontend/src/services/api.js) | Axios instance: attaches JWT, intercepts **401 → /login**, base = `VITE_API_URL` |
| [authService.js](frontend/src/services/authService.js) | login / register / refresh / me / logout |
| [patientService.js](frontend/src/services/patientService.js) | patient CRUD + `/history/` |
| [doctorService.js](frontend/src/services/doctorService.js) | `GET /api/auth/doctors/` (technician) |
| [mriService.js](frontend/src/services/mriService.js) / [ecgService.js](frontend/src/services/ecgService.js) / [echoService.js](frontend/src/services/echoService.js) / [eegService.js](frontend/src/services/eegService.js) | per-modality upload / list / get / delete / **explain** |
| [conversionService.js](frontend/src/services/conversionService.js) | `convert(modality, file, params)` + `downloadBlob` |
| [reportService.js](frontend/src/services/reportService.js) | generate / list / download PDF |

## 8.3 State + hooks

| File | Role |
|---|---|
| [store/store.js](frontend/src/store/store.js) | Redux Toolkit store |
| [store/slices/authSlice.js](frontend/src/store/slices/authSlice.js) | user + tokens |
| [store/slices/patientsSlice.js](frontend/src/store/slices/patientsSlice.js) | patient list state |
| [hooks/useAuth.js](frontend/src/hooks/useAuth.js) | `{user, login, logout, …}` |
| [hooks/usePatients.js](frontend/src/hooks/usePatients.js) | patient data hook |
| [hooks/useApi.js](frontend/src/hooks/useApi.js) | generic async/request hook |
| [hooks/useFileDropzone.js](frontend/src/hooks/useFileDropzone.js) | drag-drop upload helper |

## 8.4 Theme + i18n

- **Theme:** [theme/ThemeContext.jsx](frontend/src/theme/ThemeContext.jsx) (`ThemeProvider`/`useTokens`) +
  [theme/tokens.js](frontend/src/theme/tokens.js); CSS-variable palettes (`:root` light, `.dark` dark-neon)
  in `frontend/src/index.css`.
- **i18n:** [i18n/LanguageContext.jsx](frontend/src/i18n/LanguageContext.jsx) (`LanguageProvider`/`useI18n`)
  + per-namespace dictionaries in [i18n/locales/](frontend/src/i18n/locales/) (`nav, auth, common, ui,
  dashboard, patients, mri, ecg, echo, eeg, reports, convert, anatomy3d`) — **EN/FR**.
- Conventions: `frontend/THEME-I18N-CONVENTIONS.md`.

## 8.5 3D + effects

| File | Role |
|---|---|
| [components/three/Scene3D.jsx](frontend/src/components/three/Scene3D.jsx) | canvas/lighting wrapper |
| [components/three/Heart3D.jsx](frontend/src/components/three/Heart3D.jsx) | procedural beating heart; per-structure glow (chambers, SA/AV nodes, bundle branches) |
| [components/three/Anatomy3DPanel.jsx](frontend/src/components/three/Anatomy3DPanel.jsx) | result → highlight panel (Brain/Heart) |
| [components/fx/](frontend/src/components/fx/) | `ParticleField`, `AmbientBackground`, `TiltCard` |

## 8.6 Per-modality modules (`frontend/src/modules/`)

Each modality has a **Landing** (upload), **Result** (view), **History**, and pure mapping/util files:

| Module | Key files |
|---|---|
| **MRI** | `MRILanding`, `MRIUpload`, `MRIResult`, `MRIHistory`, `ClassProbabilities`, `TumorBadge`, `tumorType.js`, **`mriAnatomy.js`** |
| **ECG** | `ECGLanding`, `ECGUpload`, `ECGResult`, `ECGHistory`, `PathologyTable`, `HRVMetrics`, **`diagnosis.js`** (primary/maybe pick), **`ecgAnatomy.js`** (`mapEcgToHighlight`) |
| **Echo** | `EchoLanding`, `EchoUpload`, `EchoResult`, `EchoHistory`, `EFGauge`, **`echoAnatomy.js`** |
| **EEG** | `EEGLanding`, `EEGUpload`, `EEGResult`, `EEGHistory`, **`eegAnatomy.js`** |
| **Patients** | `PatientList`, `PatientCard`, `PatientForm`, `PatientDetail` |
| **Convert** | `ConvertPage` (technician tool: modality tabs, dropzone, params, download) |
| **Reports** | `ReportList`, `ReportGenerator`, `ReportViewer` |
| **Auth / Dashboard** | `Login`, `Register` · `Dashboard`, `StatsCard`, `RecentActivity` |

The `*Anatomy.js` files are **pure, unit-tested** functions that turn a result envelope into a 3D
highlight descriptor — kept separate from the scene components.

---

# PART C — DATA, TESTS, TOOLS, RUN

## 9. Model weights & caches — `backend/models_weights/`

```
models_weights/
├── vit_brain_tumor/     Swin fine-tune (config + processor sidecars; large weights gitignored)
├── ecg_finetuned/       <PATHOLOGY>.pt fine-tuned ECG checkpoints (6/7)
├── echonet/             echonet_seg.pt + echonet_ef.pt  (NOT bundled)
└── biot/                EEG-PREST-16-channels.ckpt (bundled) + biot_iiic.pt (NOT bundled)
```
Auto-download caches: `~/.cache/torch/hub/` (U-Net), `~/.cache/huggingface/` (Swin, stock).

## 10. Tests

| Where | Suites |
|---|---|
| `backend/tests/` (DB-backed, in-memory SQLite) | `test_doctor_isolation.py`, `test_ecg_reject.py`, `test_health.py`, `test_media_security.py` |
| `backend/tests/test_pipelines.py` | `SimpleTestCase` inference tests (no DB; downloads weights on first run) |
| per-app `tests.py` | auth, patients, mri, echo (incl. `ECGExplainViewTest`, `EchoExplainViewTest` — isolation + happy path), conversion (`test_permissions`, `test_converters`), explainers (`test_explainers*.py`) |
| Frontend (Vitest, jsdom) | `*.test.{js,jsx}` — formatters, slices, api, anatomy mappers, `ConvertPage`/`ConvertNav` |
| CI | [.github/workflows/ci.yml](.github/workflows/ci.yml) — backend `check`+`compileall`+weight-free tests; frontend lint+vitest+build |

Seed: `python backend/tests/seed_database.py` → `doctor@test.com` / `TestPass123!` + 5 patients
(auto-assigned via `PatientAssignment`).

## 11. Tools — `tools/` (run from project root)

- **Eval harnesses:** `eval_mri_segmentation.py`, `eval_mri_classifier.py`, `eval_mri_explainer.py`,
  `eval_ecg_classifier.py`, `eval_ecg_external.py`, `eval_echo.py`, `eval_eeg.py`, plus recall sweeps
  (`eval_mri_recall.py`, `eval_echo_recall.py`, `tune_ecg_recall.py`) and `bootstrap_cis.py` (CIs + EEG
  permutation test).
- **Sample generators:** `download_sample_mri.py`, `generate_sample_ecg.py`, `generate_sample_eeg.py`.
- **Training:** `train_eeg_head.py`; GPU fine-tunes live in `Colab PFE/`.
- **Weights check:** `download_weights.py --check-only`.

## 12. Config & run

**Backend** (`backend/`, venv active):
```bash
python manage.py migrate
python manage.py runserver            # :8000
python manage.py test tests           # full suite (auto in-memory SQLite)
```
`backend/.env` (python-decouple): `SECRET_KEY` (required), `DEBUG`, `ALLOWED_HOSTS`, `MONGO_URI`/`DB_NAME`,
`CORS_ALLOWED_ORIGINS` (pinned to `:3000`), plus model env overrides + operating-point switches
(`ECG_THRESHOLD_MODE`, `MRI_NOTUMOR_MIN_CONFIDENCE`, `REDUCED_EF_SCREEN_CUTOFF`).

**Frontend** (`frontend/`):
```bash
npm install && npm run dev            # :3000 (strictPort)
npm run build / npm run lint / npm test
```

**Windows:** `start.bat` / `stop.bat` launch both + MongoDB.

---

### Quick "where is X" index
- **Add a modality:** 8-step recipe in `maybe read/CONTRIBUTING.md`.
- **Isolation logic:** [apps/patients/access.py](backend/apps/patients/access.py).
- **Model loading / weights:** [apps/inference/model_loader.py](backend/apps/inference/model_loader.py).
- **A pipeline's `analyze_*` / `explain_*`:** `apps/inference/<modality>_pipeline.py`.
- **SHAP for a modality:** `apps/inference/explainers/<modality>_shap.py`.
- **3D heart mapping:** [frontend/src/modules/ECG/ecgAnatomy.js](frontend/src/modules/ECG/ecgAnatomy.js).
- **Signed media:** [backend/core/media.py](backend/core/media.py).
