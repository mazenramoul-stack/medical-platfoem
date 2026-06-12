# Changelog

All notable changes to the Multimodal Medical AI Platform are tracked here.
Format loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased] — GPU fine-tunes + hardening (June 2026)

### Changed
- **MRI ViT classifier fine-tuned** (Colab T4, `Colab PFE/colab_mri_vit_finetune.ipynb`):
  accuracy 80.4 % → **95.4 %** on the Kaggle Brain-Tumor `Testing/` split,
  re-verified locally with `tools/eval_mri_classifier.py`. Weights auto-detected
  from `backend/models_weights/vit_brain_tumor/` (`VIT_BRAIN_TUMOR_WEIGHTS` overrides).
- **ECG: 3 of 7 pathology models fine-tuned** (1AVB, RBBB, PVC — Colab T4,
  `Colab PFE/colab_ecg_finetune.ipynb`, kept under a no-regression rule):
  macro F1 0.711 → **0.727**, mean AUC 0.978 → 0.980, macro balanced-acc
  0.884 → 0.887 on PTB-XL fold 10, re-verified locally with
  `tools/eval_ecg_classifier.py`. Checkpoints auto-detected from
  `backend/models_weights/ecg_finetuned/` (`ECG_FINETUNED_DIR` overrides);
  `DETECTION_THRESHOLDS` re-tuned for the new ensemble (notably PVC 0.69 → 0.96).
- **MRI cross-model verdict** — new `models_agree` / `overall_verdict` pipeline
  fields; the PDF prints a radiologist-review caution when U-Net and ViT disagree.

### Added
- `Colab PFE/` — one self-contained GPU fine-tune notebook per accuracy fix
  (EEG full fine-tune still pending) + `make_lean_zip.py`.
- Auth rate limiting (DRF `ScopedRateThrottle`: login 10/min, register 5/min,
  refresh 30/min).
- ESLint 9 flat config + `npm run lint`; GitHub Actions CI (Django check +
  compileall, frontend lint + build).
- `manage.py cleanup_media --days N` media-retention command (dry-run default).
- `tools/download_weights.py` (`--check-only` weight-status report).
- `maybe read/DEPLOYMENT.md` production deployment guide.

## [Unreleased] — EEG modality (BIOT / IIIC)

Adds a fourth analysis modality, **EEG**, wired end-to-end like MRI/ECG/Echo:
backend pipeline + Django app + React module + combined-PDF section + a
reproducible training/validation harness.

### Added
- **`apps/eeg`** Django app — `.edf` upload + synchronous BIOT/IIIC inference,
  doctor-scoped, `EEGAnalysis` model + migration (`/api/eeg/`).
- **Vendored BIOT** model code (`apps/inference/biot/`, MIT) + `eeg_pipeline.py`
  (`analyze_eeg`) + `model_loader.get_eeg_model()`.
- **`eeg_preprocess.py`** — shared train/inference-parity preprocessing (16-ch
  bipolar montage, 200 Hz, 10 s segments, 95th-pct normalisation), replicating
  BIOT's IIIC pipeline exactly.
- **Frontend EEG module** (`modules/EEG/`: Landing/Upload/History/Result),
  dashboard tile (live count), patient-detail EEG tab + upload, report selector;
  replaced the old `EEGPage` "coming soon" placeholder.
- **Reports** — `Report.eeg_analysis` FK + migration, `_eeg_section` in the PDF.
- **Tooling** — `tools/train_eeg_head.py` (fine-tune the IIIC head on Kaggle HMS,
  encoder frozen; KGAT-token downloader with rate-limit backoff), `tools/eval_eeg.py`
  (balanced-acc / κ / macro-F1 / per-class / 6×6 confusion / KL), `tools/eeg_hms.py`,
  `tools/generate_sample_eeg.py`.
- Deps: `mne`, `edfio`, `linear-attention-transformer`, `pyarrow`.

### Notes (honest scope)
- BIOT releases only a pretrained **encoder**, not an IIIC head; the 6-class head is
  fine-tuned in-repo on Kaggle HMS. Endpoint raises a clear `FileNotFoundError` until
  a head is present (same "weights not bundled" pattern as EchoNet).
- Validated metrics are honest-but-modest (balanced-acc ~0.28 on a 1,451-EEG subset,
  frozen encoder, CPU) — see [VALIDATION.md](VALIDATION.md) §5. EEG is functional
  harmful-brain-activity screening, **not** a tumour detector.

## [1.0.0] — 2026-05-17 — Initial PFE release

First end-to-end release covering MRI + ECG analysis, combined PDF reports,
and a polished React frontend. Suitable for thesis defence.

### Added

**Backend (Django 3.2.25 + DRF + djongo + MongoDB)**
- Custom email-based `User` model with SimpleJWT authentication (`/api/auth/`)
- Doctor-scoped patient management with `/history/` aggregation (`/api/patients/`)
- Synchronous MRI inference endpoint with file validation and 5-minute timeout
  (`/api/mri/upload/`)
- Synchronous ECG inference endpoint with the same contract (`/api/ecg/upload/`)
- Combined PDF report generation via ReportLab, including a neuro-cardiac
  correlation interpretation when both modalities are present (`/api/reports/`)
- File serving for media URLs in DEBUG mode

**Inference engine (`apps/inference/`)**
- Thread-safe `ModelLoader` singleton with lazy weight downloads
- MRI pipeline: U-Net segmentation + ViT classification + 3-panel visualisation
- ECG pipeline: bandpass filter + 7-pathology DenseNet-1D ensemble + NeuroKit2 HRV
- Universal image loader (PNG / JPG / TIFF / BMP / DICOM / NIfTI)
- Universal ECG loader (CSV / EDF / WFDB) with auto-resample and pad/trim
- NaN/Inf sanitisation so JSON serialisation never crashes on degenerate inputs

**Frontend (React 19 + Vite + TailwindCSS + Redux Toolkit)**
- Authenticated routes guarded by `<ProtectedRoute>` with redirect-after-login
- Responsive sidebar layout with off-canvas mobile drawer
- Login + Register with live validation and icon-prefixed inputs
- Dashboard with live counts from four list endpoints and recent-activity feed
- Patient list with search, gender filter, and client-side pagination
- Patient form (create + edit modes)
- Patient detail with tabbed MRI / ECG / Reports view and three action modals
- MRI upload (drag-and-drop, progress bar, "Running U-Net + ViT…" stage)
- MRI result viewer with Original / Mask / Overlay tabs and per-image download
- ECG upload with the same UX
- ECG result with prominent diagnosis card, HRV reference-range cards,
  per-pathology probability table with horizontal bars
- Report list with in-modal PDF preview and download
- Report generator modal with completed-analysis filtering
- Custom `TumorBadge` with type-specific colours and tooltips

**Testing infrastructure**
- `tools/download_sample_mri.py` — fetches the TCGA-LGG test slice
- `tools/generate_sample_ecg.py` — generates normal / tachy / brady / afib CSVs
- `backend/tests/test_pipelines.py` — 7-test Django suite (inference + API)
- `backend/tests/seed_database.py` — idempotent demo-data loader
- `backend/tests/test_apis.sh` — bash curl smoke test for the REST endpoints

**Documentation**
- `README.md` — full architecture, models, endpoint reference, references
- `TESTING.md` — manual + automated test guide with troubleshooting table
- `PFE_REPORT_OUTLINE.md` — thesis chapter mapping
- `SCREENSHOTS/README.md` — checklist for thesis figures

**Tooling**
- `start.bat` / `start.ps1` — one-click Windows launcher (backend + frontend + browser)
- `stop.bat` / `stop.ps1` — graceful shutdown that only targets this project's processes
- `backend/.env.example` — environment variable template
- `docker-compose.yml` + `Dockerfile`s — optional containerised demo

### Known limitations

> **State at 1.0.0 — both #1 and #2 below have since been resolved (see Unreleased / current docs).**

1. **U-Net preprocessing mismatch** — `image / 255.0` instead of the model's expected
   channel-wise z-score. Produced saturated masks on the TCGA test sample.
   *(Resolved: the real cause was a double-sigmoid; the pipeline now uses the U-Net
   output directly and applies per-channel z-score — Dice ~0.85 on LGG.)*
2. **ECG pathology coverage = 5/7** — `IRBBB` and `CRBBB` don't exist in `ecglib`'s
   pretrained set; the loader originally requested them and got only 5 models.
   *(Resolved: the loader now requests `RBBB`/`LBBB` instead, so all **7/7** load —
   `[AFIB, 1AVB, STACH, SBRAD, RBBB, LBBB, PVC]`.)*
3. **Django 3.2 instead of 4.2** — djongo 1.3.6 does not work on Django 4.x.
4. **No GPU support tested** — all timings are CPU-only.
5. **No clinical validation** — confidence scores are not calibrated.

See `README.md` → Known Limitations for the full discussion and recommended fixes.

### Migration notes

The project moved from the originally-specified Django 4.2 to Django 3.2.25 LTS
during Step 4 because of the djongo + sqlparse pin conflict. Documented at the
time, preserved here as the canonical version baseline.
