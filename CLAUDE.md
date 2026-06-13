# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Multimodal medical AI platform (Master's PFE, Constantine 2). Web app that runs pre-trained deep-learning models on brain MRI, 12-lead ECG, echocardiogram, and EEG inputs and emits a combined PDF report. (EEG = BIOT/IIIC 6-class harmful-brain-activity screening; its fine-tuned head is **not bundled** — see below.) Architecture, model provenance, API surface, and known limitations are documented in [README.md](README.md). End-to-end manual test scenario and troubleshooting matrix are in [TESTING.md](maybe%20read/TESTING.md). Read both before non-trivial changes — they encode constraints (model preprocessing mismatch, partial ECG pathology coverage, version pins) that are easy to "fix" but are deliberate.

## Common commands

Backend (run from `backend/`, with venv activated):

```bash
python manage.py runserver                      # dev server on :8000
python manage.py migrate                        # apply migrations
python manage.py makemigrations                 # after model changes
python manage.py test tests                     # full test suite
python manage.py test tests.test_pipelines      # inference tests only — no DB; daily-use escape hatch when djongo refuses the test DB
python manage.py test tests.test_pipelines.MRIPipelineTest.test_<name>  # single test
python apps/inference/test_pipelines.py         # pre-warm model weight caches (~700 MB first run)
python tests/seed_database.py                   # seed doctor@test.com / TestPass123! + 5 patients
python manage.py cleanup_media --days N         # media retention: dry-run list; add --delete to remove (reports/ skipped by default)
```

Frontend (run from `frontend/`):

```bash
npm install
npm run dev                                     # Vite dev server on :3000 (strictPort)
npm run build                                   # production build
npm run preview                                 # preview built output
npm run lint                                    # ESLint 9 flat config (eslint.config.js); must exit 0
```

Frontend port and backend CORS are coupled in two places — see [Hard version constraints](#hard-version-constraints) before changing the port.

Sample data generators (run from project root):

```bash
python tools/download_sample_mri.py
python tools/generate_sample_ecg.py
python tools/generate_sample_eeg.py
python tools/download_weights.py --check-only   # report which model weights are present; default mode pre-warms MRI+ECG and prints Echo/EEG instructions
```

Validation / eval + EEG-training scripts also live in `tools/` (run from project root). These back the accuracy numbers in [VALIDATION.md](maybe%20read/VALIDATION.md) and the model notes below — use them, don't re-derive metrics by hand:

```bash
python tools/eval_mri_segmentation.py     # Dice on LGG (validates the U-Net double-sigmoid fix)
python tools/eval_mri_classifier.py       # 4-class Swin accuracy (Kaggle brain-tumor)
python tools/eval_ecg_classifier.py       # ecglib pathology models (PTB-XL fold 10)
python tools/eval_ecg_external.py         # ECG models on Chapman-Shaoxing-Ningbo — PTB-XL-independent leakage check, see tools/EXTERNAL_ECG_EVAL.md
python tools/eval_echo.py                 # EchoNet EF / segmentation
python tools/eval_eeg.py                  # BIOT/IIIC head (after training)
python tools/train_eeg_head.py            # fine-tune IIIC head on Kaggle HMS (encoder frozen)
python tools/tune_ecg_recall.py           # recall-first ECG thresholds (reads cached scores from eval_ecg_classifier.py --save-scores)
python tools/eval_mri_recall.py           # tumor-vs-notumor detection recall + notumor confidence-gate sweep
python tools/eval_echo_recall.py          # reduced-EF detection recall vs safety margin
# tools/eeg_hms.py — HMS dataset helpers shared by EEG train/eval (not a standalone entry point)
```

EEG-head training and echo eval can also run on GPU in Colab — see [tools/COLAB.md](tools/COLAB.md) and the `tools/colab_echo.ipynb` / `tools/colab_eeg.ipynb` notebooks (the local CPU path above is the default).

[Colab PFE/](Colab%20PFE/) is the newer GPU **fine-tune** workflow: one self-contained Colab notebook per accuracy fix (EEG full fine-tune — still pending; MRI Swin — done June 2026, 95.4%; per-pathology ECG — done June 2026, 3/7 kept, macro F1 0.727). `python "Colab PFE/make_lean_zip.py"` builds the lean repo zip the EEG/ECG notebooks consume from Drive. Returned weights drop into `backend/models_weights/` and are auto-detected by the loaders; after pasting Colab results back, always re-verify locally with the `tools/eval_*.py` harnesses — never trust Colab numbers unverified. Round-trip details, honest accuracy targets (EEG ≈0.5 balanced accuracy is the *ceiling*, not a shortfall), and why Echo/U-Net have no notebook: [Colab PFE/README.md](Colab%20PFE/README.md).

Windows one-click launchers: `start.bat` / `stop.bat` (also `.ps1` variants).

Frontend linting is **ESLint 9** (flat config in [frontend/eslint.config.js](frontend/eslint.config.js), run `npm run lint` — react-three-fiber props are allowlisted for `react/no-unknown-property`). There is still **no Jest and no Python linter**. CI lives in [.github/workflows/ci.yml](.github/workflows/ci.yml): Django `check` + `compileall` for the backend, lint + build for the frontend — it deliberately does **not** run the inference tests (they download ~700 MB of weights); run `manage.py test` locally. GitHub only honors that workflow if `medical-platform/` itself is the repository root (see the header comment in ci.yml).

`docker-compose.yml` exists but is **explicitly NOT tested end-to-end** (see its header comment). It's a starting point, not a supported path — don't assume `docker compose up` works or treat its config as authoritative. Local dev is the `runserver` + `npm run dev` flow above.

Backend deps are split: [backend/requirements-core.txt](backend/requirements-core.txt) is the lightweight Django/DRF/djongo stack; [backend/requirements.txt](backend/requirements.txt) adds the heavy ML stack (torch, torchvision, monai, transformers, huggingface-hub, ecglib). Install `requirements.txt` to run inference; `requirements-core.txt` alone boots the API but the pipelines will fail to import.

## Reference docs

Non-runtime docs live under [maybe read/](maybe%20read/) — moving or deleting that folder never affects the running app. Beyond README/TESTING/CONTRIBUTING (cited above), deeper context lives in: [VALIDATION.md](maybe%20read/VALIDATION.md) (how each model's accuracy was measured), [METHODOLOGY.md](maybe%20read/METHODOLOGY.md), [CHANGELOG.md](maybe%20read/CHANGELOG.md), and the per-modality briefs under [docs/](docs/) (`EEG-MODALITY-BRIEF.md`, `EEG-IIIC-MODALITY-BRIEF.md`, `HOW-IT-WORKS.md`, `PROJECT_FUNCTIONALITY_A_TO_Z.md` — a full end-to-end functionality walkthrough — and `THE-WAY-THE-PROJECT-WORKS-AND-LIVES.md` — plain-language runtime/model-provenance walkthrough). [tools/EXTERNAL_ECG_EVAL.md](tools/EXTERNAL_ECG_EVAL.md) documents the PTB-XL-independent ECG evaluation procedure. [DEPLOYMENT.md](maybe%20read/DEPLOYMENT.md) covers deployment notes.

Thesis-support folders (not code docs): `maybe read/PFE_REPORT_OUTLINE.md` is the thesis outline; [Mazen_PFE/](Mazen_PFE/) holds the defence narrative (`My Project – The End.md`) and its honest-limitations companion (`Problems of My Project.md`) — keep both in sync when accuracy numbers or limitations change; [SCREENSHOTS/](SCREENSHOTS/) is a numbered checklist of platform captures for the report's results chapter.

## Hard version constraints

These are not arbitrary; changing them breaks the stack:

- **Python 3.10 or 3.11** — `djongo 1.3.6` does not load on 3.12+.
- **Django 3.2.25 LTS** — `djongo` is incompatible with Django 4.x. The build spec asked for 4.2; we deliberately downgraded. Don't "upgrade" without replacing djongo.
- **ecglib 1.0.1** — exact pin. Other versions change the `create_model` import path.
- **Frontend on port 3000** with `strictPort: true` in [frontend/vite.config.js](frontend/vite.config.js). Backend CORS in `backend/.env` is pinned to `:3000`. If you need a different port, change both.

## Architecture

Monorepo with two independent apps:

- `backend/` — Django 3.2 + DRF + SimpleJWT, MongoDB via djongo. Django apps live under `backend/apps/` and are registered as `apps.<name>` (note the dotted prefix — `apps.py` sets `name = 'apps.<name>'`). The Django project config (settings, root URLconf, WSGI/ASGI) is in `backend/core/`.
- `frontend/` — React 19 + Vite 8 + Tailwind + Redux Toolkit. Per-domain code under `frontend/src/modules/{Auth,Dashboard,Patients,MRI,ECG,Echo,EEG,Reports}/`. (Routes are registered in [frontend/src/App.jsx](frontend/src/App.jsx); `react-three-fiber` 3D scenes live in `components/three/`.) `ComingSoonModality.jsx` still exists as a generic placeholder component for future modalities, but nothing imports it now.

Secrets and DB/CORS config are read from `backend/.env` via **python-decouple** (`config(...)` in `core/settings.py`) — `SECRET_KEY` is required, others have defaults. Copy `backend/.env.example` to start.

### Backend slicing

| App | Responsibility |
|---|---|
| `apps/authentication` | Custom User (email login), JWT views |
| `apps/patients` | Doctor-scoped CRUD + `/history/` aggregate endpoint |
| `apps/mri` | Upload + synchronous inference + result URLs |
| `apps/ecg` | Upload + synchronous inference + plot URL |
| `apps/echo` | Upload + synchronous EchoNet inference (LV segmentation + EF regression) |
| `apps/eeg` | Upload (.edf) + synchronous BIOT/IIIC inference (6-class harmful-brain-activity) |
| `apps/reports` | ReportLab PDF generation with combined interpretation |
| `apps/inference` | Lazy singleton model loader + MRI/ECG/Echo/EEG pipelines + utils. BIOT model code is vendored under `apps/inference/biot/`; `eeg_preprocess.py` is the shared train/inference-parity preprocessing. |

URL prefixes (`core/urls.py`): `api/auth/`, `api/` (patients), `api/mri/`, `api/ecg/`, `api/echo/`, `api/eeg/`, `api/reports/`.

Inference is **synchronous in the request thread**. There is no Celery / RQ. First call downloads ~700 MB of MRI/ECG weights; subsequent calls hit the local cache (`~/.cache/torch/hub/`, `~/.cache/huggingface/`). EchoNet weights are the exception — they are **not auto-downloaded** (see below).

### Two contracts to preserve when touching backend code

1. **Doctor isolation.** Every queryset in `patients`, `mri`, `ecg`, `echo`, `reports` filters by the requesting doctor. A new endpoint that returns another doctor's data is a bug. The FK chain is `<Analysis> → patient → doctor`.
2. **Pipeline result envelope.** Inference functions return a plain dict shaped `{status, ...result_fields, error?, error_type?}`. They must never raise into the view — structured failure is part of the contract so the API can report partial results (e.g. ECG with 5/7 pathology models loaded).

### Adding a new modality

Follow the 8-step recipe in [CONTRIBUTING.md](maybe%20read/CONTRIBUTING.md#adding-a-new-modality): pipeline → loader → app → model+migration → serializer+views → URL → frontend module → reports section. The platform is designed for plug-in addition without editing existing modality code.

### Frontend wiring

- Axios instance in `services/` attaches the JWT and intercepts 401 → `/login`.
- Redux slices live in `store/` (`auth`, `patients`, `notifications`). Per-resource service modules wrap REST calls; components consume via `hooks/` (`useAuth`, `usePatients`, `useApi`).
- Functional components only. `ErrorBoundary` is the documented exception (class component allowed).
- Tailwind utility classes inline; add custom CSS only when Tailwind genuinely can't express it.
- **Light/dark theme + EN/FR i18n** (June 2026): CSS-variable palettes live in [frontend/src/index.css](frontend/src/index.css) (`:root` = light, `.dark` = dark-neon; the old dark shim is scoped under `.dark`); `ThemeProvider`/`useTokens` (`src/theme/ThemeContext.jsx`) and `LanguageProvider`/`useI18n` (`src/i18n/LanguageContext.jsx`, per-namespace dictionaries in `src/i18n/locales/`). When adding or editing components, follow [frontend/THEME-I18N-CONVENTIONS.md](frontend/THEME-I18N-CONVENTIONS.md) — it encodes the conversion rules (text-ink vs text-hi, era-dependent grey classes, accent hexes via useTokens, EN/FR key-tree parity).

## Things that look like bugs but aren't

- **MRI U-Net segmentation works (Dice ~0.85 on LGG) — but it USED to look broken due to a double-sigmoid bug, now fixed.** The `mateuszbuda/brain-segmentation-pytorch` U-Net applies sigmoid *inside* its `forward()`, so its output is already a probability map in [0,1]. An earlier `mri_pipeline.py` applied `torch.sigmoid()` **again**, squashing [0,1] into [0.5, 0.73] so every pixel crossed the 0.5 threshold → the mask saturated (marked ~100% of the image), which the **saturation guard** then suppressed to `tumor_detected: false`. The fix (use the U-Net output directly, no second sigmoid) is in `apps/inference/mri_pipeline.py` and is verified: Dice ≈ 0.85 on the LGG dataset via `tools/eval_mri_segmentation.py`. The saturation guard remains as a harmless safety net (real masks cover ~2–5%, far below the 75% trigger). Note: segmentation is validated on LGG (which has masks); the 4-class **Swin classifier** (Swin-T, `Devarshi/Brain_Tumor_Classification`, a fine-tune of `microsoft/swin-tiny-patch4-window7-224`; Liu et al. 2021, Swin Transformer, ICCV — arXiv:2103.14030) is validated on the Kaggle brain-tumor set (95.4% after the June 2026 fine-tune; the stock hub model scored 80.4%) — different datasets, see `VALIDATION.md`. The fine-tuned classifier weights live in `backend/models_weights/vit_brain_tumor/` (the folder name is historical; the model is a Swin-T) and are auto-detected by `get_mri_classifier()`.
- **`ecglib` may warn about `IRBBB` / `CRBBB` at startup, but all 7 pathologies load.** The build spec asked for `IRBBB`/`CRBBB`, which don't exist in ecglib 1.0.1; the loader requests `RBBB`/`LBBB` instead, so the actual set `[AFIB, 1AVB, STACH, SBRAD, RBBB, LBBB, PVC]` loads **7/7** at startup. (The older "degrades to 5/7" wording referred to superseded code that requested the nonexistent codes — it is no longer accurate as steady state.) The result envelope can still *report* a runtime partial (e.g. 6/7) **only if a model fails mid-request** — that's the partial-result contract, not normal operation. Fine-tuned per-pathology checkpoints (`<PATHOLOGY>.pt` under `backend/models_weights/ecg_finetuned/`, overridable via `ECG_FINETUNED_DIR`) are auto-detected by `get_ecg_models()` and take precedence over stock ecglib weights; with none present, behavior is unchanged.
- **EchoNet weights are NOT bundled and NOT auto-downloaded.** `model_loader.get_echo_models()` loads two checkpoints from disk (`backend/models_weights/echonet/echonet_seg.pt` + `echonet_ef.pt`, overridable via `ECHONET_SEG_WEIGHTS` / `ECHONET_EF_WEIGHTS` env vars) and raises a clear `FileNotFoundError` if absent. So the echo endpoint failing with "weights not found" on a fresh checkout is expected, not a bug — download the EchoNet-Dynamic checkpoints first. Note `warmup()` only pre-loads MRI + ECG, **not** echo, for this reason.
- **The EEG (BIOT/IIIC) head is NOT bundled — same pattern as EchoNet.** BIOT only releases a pretrained *encoder* (`models_weights/biot/EEG-PREST-16-channels.ckpt`, bundled), **not** an IIIC classification head. `model_loader.get_eeg_model()` builds `BIOTClassifier`, loads that encoder, then loads the fine-tuned head from `BIOT_IIIC_WEIGHTS` (default `models_weights/biot/biot_iiic.pt`) — raising a clear `FileNotFoundError` if absent. The head is produced by `tools/train_eeg_head.py` (fine-tune on Kaggle HMS, encoder frozen); validate with `tools/eval_eeg.py`. So the EEG endpoint failing with "IIIC head not found" on a fresh checkout is expected, not a bug. `warmup()` does **not** pre-load EEG either.
- **All four pipelines run a recall-first / screening operating point by default (June 2026) — low precision and liberal flagging are deliberate, not miscalibration.** The clinical posture: a screening tool must never silently clear a sick patient; false alarms route to human review. Concretely: **ECG** uses recall-first thresholds (every pathology recall ≥ 0.95 on the held-out fold, macro precision ~0.35 — switch to the balanced macro-F1-0.727 set with `ECG_THRESHOLD_MODE=f1`; both tables in `ecg_pipeline.py` and VALIDATION.md §1). **MRI** accepts a `notumor` verdict only when Swin confidence ≥ 0.99 *and* the U-Net found no tissue, else returns `screening_flag: possible_tumor_review` (lifts tumor-detection recall 0.983 → 0.998). **Echo** flags EF < 55% for review (`REDUCED_EF_SCREEN_CUTOFF`, a +5% margin over the 50% clinical cutoff — recall 0.783 → 0.952). **EEG** reports `screen_positive` when *any* IIIC pattern appears; it has near-zero benign specificity by design — it's a routing signal, never a rule-out. Don't "rebalance" any of these toward F1/precision without being asked; the numbers are reproduced by `tools/tune_ecg_recall.py`, `tools/eval_mri_recall.py`, `tools/eval_echo_recall.py`, and VALIDATION.md documents both operating points.
- **PDF generator runs everything through `_ascii()` in [backend/apps/reports/pdf_generator.py](backend/apps/reports/pdf_generator.py).** Helvetica lacks box-drawing glyphs; the substitution prevents `?` rendering. Don't remove it.
- **Reports survive patient deletion via null FK.** Patient cascade removes MRI/ECG/Echo records but keeps the generated PDF.

## Testing notes

- `SimpleTestCase`-based pipeline tests under `backend/tests/test_pipelines.py` always run (no DB).
- `APITestCase` tests need the test DB, which djongo+Mongo handles awkwardly. If the runner refuses to create the test DB, run the pipeline tests in isolation (command above).
- First test run downloads model weights — budget 5–10 minutes on a fresh checkout. Pre-warm with `python apps/inference/test_pipelines.py`.
- `backend/tests/test_apis.sh` is a curl/jq end-to-end API smoke test — needs the dev server running, a registered user, and sample files in `backend/media/`.
- Auth endpoints are rate-limited (DRF `ScopedRateThrottle`, LocMemCache: login 10/min, register 5/min, refresh 30/min). A test that hammers login more than 10×/min in one process will see 429s.

## Code style

Per [CONTRIBUTING.md](maybe%20read/CONTRIBUTING.md): PEP 8 + Google-style docstrings on public `apps/inference/` functions, 2-space JS (Prettier defaults), functional React components only. Keep DRF view methods thin — push logic into serializers or pipelines.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
