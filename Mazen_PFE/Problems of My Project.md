# Problems of My Project
### Where it falls short, why, and what to improve

> Companion to *My Project – The End.md*. Every point here is real and verifiable in the repo (sources: README *Known Limitations*, `maybe read/VALIDATION.md`, `maybe read/TESTING.md`, CLAUDE.md). Knowing these is a strength at the defence, not a weakness.

---

## 0. Status update — fix sweep of June 10, 2026

A repair pass went through every fixable item below; each fix was implemented and then independently re-verified (tests/lint/build actually run, output checked).

### Safety-first / false-negative minimization pass (June 12, 2026)

Per supervisor guidance that the platform must not produce false negatives (never miss a sick patient), every model was re-calibrated for **high recall**, with precision tracked as a secondary cost. The key insight: the **decision threshold / decision rule — not the weights — controls recall**, so this needed **no GPU retraining**. All numbers verified locally.

| Model | Don't-miss recall | False negatives | Precision cost | How |
|---|---|---|---|---|
| **ECG** (7 pathologies) | all 7 **≥0.95** (macro 0.982) | 13 / 2,198 (was ~62) | macro 0.69 → 0.35 | recall-first thresholds (`ECG_THRESHOLD_MODE=recall`, default); `f1` set kept and switchable |
| **MRI** (tumour vs healthy) | **0.998** (1.000 zero-miss mode) | 2 / 1,200 (0 in zero-miss) | 2–17 / 400 healthy flagged | `notumor`-confidence safety gate + U-Net cross-check in `mri_pipeline.py` |
| **EEG** (screen) | seizure-routing **0.966** ✓; general abnormal **0.931** | 128 / 1,850 windows | benign specificity ≈0 | `screen_positive` field; general ≥0.95 needs the GPU full fine-tune (the one place GPU is warranted) |
| **Echo** (reduced EF) | **0.952** (flag EF<55 %) | 4 / 83 reduced | precision 0.88 → 0.68 | +5 % safety-margin screen in `echo_pipeline.py` |

Reproduce: `tools/tune_ecg_recall.py`, `tools/eval_mri_recall.py`, `tools/eval_echo_recall.py`, `tools/eval_eeg.py` (binary-screen block). Detail in `maybe read/VALIDATION.md` §0. **No GPU was needed for ECG/MRI/Echo;** EEG general-screen ≥0.95 is the only item that would benefit from the pending EEG full fine-tune.

| Status | Item | What was done |
|---|---|---|
| ✅ Fixed | MRI model disagreement (Sci #2, partially) | New `models_agree` / `overall_verdict` fields in `mri_pipeline.py`; the PDF now prints a radiologist-review caution when U-Net and ViT disagree. Full 7-test pipeline suite passes. |
| ✅ Fixed | No auth rate limiting (Eng #5, partially) | DRF `ScopedRateThrottle`: login 10/min, register 5/min, refresh 30/min. Verified: 11th login attempt in a minute is rejected. |
| ✅ Fixed | No linter / no CI (Eng #3, mostly) | ESLint 9 flat config + `npm run lint` (passes, 0 errors); GitHub Actions CI (`.github/workflows/ci.yml`): Django check + compileall + frontend lint/build. Jest and a Python linter remain TODO. |
| ✅ Fixed | Heavy/confusing first run (Eng #6) | `tools/download_weights.py`: `--check-only` reports per-modality weight status; default mode pre-warms MRI+ECG and prints Echo/EEG instructions. |
| ✅ Fixed | No media cleanup policy (Prac #2) | `python manage.py cleanup_media --days N` — dry-run by default, `--delete` to remove, skips `reports/` by design, no DB needed, hardened against Windows junction tricks. |
| ✅ Fixed | No deployment story (Prac #3) | `maybe read/DEPLOYMENT.md`: production .env, gunicorn/waitress, nginx block (500M upload cap matching the echo limit), weights placement, honest constraints. |
| ✅ Fixed | Disk full (Prac #1) | 2.5 GB backup zip removed from E:; ~3 GB free again. |
| ⚠ NEW — found during the sweep | **Git repo root is `E:\MASTER`, not `medical-platform/`** | The repo was initialised one level above the project, has zero commits, and no remote. Pushed as-is, GitHub would ignore `.github/workflows/ci.yml` (it must sit at the repo root). Fix before publishing: re-init / publish `medical-platform/` itself as the repository root. |
| ✅ Fixed + verified | **MRI classifier accuracy: 80.4 % → 95.4 %** | Fine-tuned on Colab T4 (`Colab PFE/colab_mri_vit_finetune.ipynb`, June 11 2026), weights in `backend/models_weights/vit_brain_tumor/`, auto-detected. **Re-verified locally**: `tools/eval_mri_classifier.py` on the full 1,600-image Testing split → 95.4 % / macro F1 0.954, confusion matrix identical to the Colab run; pipeline tests 7/7. |
| ✅ Fixed + verified | **ECG weak-class F1 (Sci #4/#5 partially): 3/7 models fine-tuned** | Colab T4 (`Colab PFE/colab_ecg_finetune.ipynb`, June 11 2026), kept under a no-regression rule: 1AVB F1 0.521→0.606, RBBB 0.844→0.864, PVC 0.821→0.828. **Re-verified locally** on PTB-XL fold 10: macro F1 0.711→**0.727**, mean AUC 0.980, macro bal-acc 0.887; `DETECTION_THRESHOLDS` re-tuned; pipeline tests 7/7. |
| 🚀 Ready to run (needs GPU) | EEG accuracy (Sci #1) | **GPU fix kit prepared in `Colab PFE/` (June 10, 2026):** notebook + auto-detect loader wired. Honest target: EEG 0.278→0.45-0.55 (90 % is impossible for IIIC — see `Colab PFE/README.md`). |
| ◌ Open (needs data) | Common-dataset MRI validation (Sci #2 rest), threshold re-calibration (Sci #4), learned fusion (Sci #6), clinical cohort (Sci #7) | All require datasets/cohorts that don't exist in this repo. |
| ◌ Open (big migration, deliberate) | djongo/Django 3.2 lock-in (Eng #2), synchronous inference (Eng #1), JWT in localStorage + port coupling (Eng #5 rest), docker-compose (Eng #4), djongo test DB (Eng #7) | Architecture-level decisions documented in CLAUDE.md; changing them is a project decision, not a bug fix. |

---

## 1. Scientific / model problems (the most important ones)

| # | Problem | Why it matters | Improvement |
|---|---|---|---|
| 1 | **EEG accuracy is modest: balanced-acc 0.278** (chance = 0.167, BIOT's published full-data ≈ 0.5). The IIIC head was trained on CPU on only a 1,451-EEG subset with the encoder frozen. | EEG is the weakest modality; it screens, it does not diagnose. | **GPU full fine-tune** (unfreeze the encoder) on the complete HMS dataset — the documented path to close the gap. Colab notebooks already exist in `tools/`. |
| 2 | **MRI segmentation and classification are validated on different datasets** (U-Net on LGG, ViT on Kaggle Brain-Tumor — different MRI modalities). A single uploaded image is *not* validated end-to-end through both. | The two models can **disagree on the same input**, and the report shows both without resolving the conflict. | ✅ The "uncertain" verdict is implemented (June 2026) — pipeline + PDF caution. Still open: validate both models on one common dataset. |
| 3 | **Possible ECG data leakage.** ecglib's 500k+ training corpus is unpublished and *may* include PTB-XL, so the ~0.98 AUC could be optimistic. (The June 2026 fine-tune deliberately *does* train on PTB-XL folds 1–8 — that part is disclosed, fold-separated, and leakage-free by construction.) | The headline ECG number might be inflated. | Already partially addressed: independent re-evaluation on Chapman-Shaoxing-Ningbo (`tools/eval_ecg_external.py`). Quote the external macro-AUC alongside the PTB-XL one. |
| 4 | **ECG thresholds are calibrated for PTB-XL-like data only.** Per-pathology thresholds raised macro F1 from 0.51 → 0.71 (0.54 → 0.73 with the June 2026 fine-tuned ensemble), but they will mis-fire on data from a different recorder/population. | Over- or under-flagging on hospital data. | Re-tune thresholds per data source; ideally learn calibration (Platt/isotonic) per deployment site. |
| 5 | **Only 5–7 ECG pathologies, not a full diagnostic panel.** | Coverage is partial by design (what ecglib pretrained). | Train/add more pathology heads, or swap in a broader pretrained set. |
| 6 | **The "combined interpretation" in the PDF is rule-based template text**, not a learned neuro-cardiac correlation. | The multimodal "fusion" is presentation-level, not data-driven. | The project's principal future work: collect a *paired* imaging+ECG cohort and test the correlation hypothesis statistically. |
| 7 | **Validated on public benchmarks, never on a clinical cohort.** | No evidence yet of real-world, prospective performance. | Pilot study with a hospital partner; per-site recalibration before any clinical claim. |

---

## 2. Engineering problems

| # | Problem | Why it matters | Improvement |
|---|---|---|---|
| 1 | **Inference is synchronous in the request thread** — no Celery/RQ queue, no progress bar; a slow model blocks the HTTP worker. | Doesn't scale beyond a demo; two simultaneous uploads queue on one worker. | Add a task queue (Celery + Redis) and a polling/WebSocket status endpoint. |
| 2 | **Stuck on Django 3.2 LTS and Python 3.10/3.11 because of djongo 1.3.6.** Django 3.2 support has ended; djongo is barely maintained. | Security updates and ecosystem compatibility erode over time. | Replace djongo (e.g. PostgreSQL + JSONField, or MongoEngine without Django ORM) — then upgrade to Django 5.x. |
| 3 | **No CI, no linter, no frontend tests.** No ESLint config, no Jest, no Python linter; only backend tests exist. | Regressions are caught manually or not at all. | ✅ Mostly done (June 2026): ESLint 9 + `npm run lint` + GitHub Actions CI (check/compileall/lint/build). Still open: Jest component tests, ruff. |
| 4 | **`docker-compose.yml` is not tested end-to-end** (stated in its own header). | "Containerised demo" can't be promised. | Finish and test the compose stack, or remove it to avoid over-claiming. |
| 5 | **Fragile local coupling:** frontend hard-pinned to port 3000 (`strictPort`) and backend CORS pinned to the same; JWT stored in `localStorage` (XSS-readable); no rate limiting on auth endpoints. | Demo-grade security posture. | ✅ DRF throttling added (June 2026: login 10/min, register 5/min, refresh 30/min). Still open: httpOnly-cookie tokens, single-place port config. |
| 6 | **Heavy first-run experience:** ~700 MB of MRI/ECG weights download on the first call, and Echo/EEG weights are not bundled at all (manual download / in-repo training required). | A fresh checkout fails Echo/EEG until weights are placed — confusing for new users even though it's by design. | ✅ Done (June 2026): `tools/download_weights.py` (`--check-only` status report; default pre-warms MRI+ECG, prints Echo/EEG steps). |
| 7 | **djongo handles the test database awkwardly** — `APITestCase` runs sometimes refuse to create the test DB; only the no-DB pipeline tests are reliable daily. | Part of the test suite is second-class. | Same root fix as #2 (replace djongo); meanwhile keep the documented pipeline-tests escape hatch. |

---

## 3. Practical / housekeeping problems

| # | Problem | Improvement |
|---|---|---|
| 1 | **The development disk (E:) is essentially full** — it already broke a git operation mid-write. `backend/` = 2.6 GB (venv + weights), `data/hms` = 1.6 GB, plus a 2.5 GB `medical-platform.zip` backup at `E:\MASTER\`. | ✅ Zip removed (June 2026) — ~3 GB free again. Still worth doing: move `data/hms` (1.6 GB) off E:. |
| 2 | **Generated artefacts accumulate in `media/`** (uploads, overlays, plots, PDFs) with no cleanup policy. | ✅ Done (June 2026): `python manage.py cleanup_media --days N` (dry-run default, `--delete` to remove, skips `reports/`). |
| 3 | **No deployment story** — the project runs as two dev servers (`runserver` + `npm run dev`). | ✅ Done (June 2026): `maybe read/DEPLOYMENT.md` — gunicorn/waitress + nginx + built frontend, weights placement, honest constraints. |

---

## 4. Honest summary for the defence

- **Strongest parts:** ECG (AUC 0.980 + macro F1 0.727 after the June 2026 fine-tune of 3/7 models + external leakage check + threshold-calibration contribution), MRI classification (95.4 % after fine-tune), Echo (matches the published EchoNet paper), the plug-in modality architecture, and the honest, reproducible validation methodology (`tools/eval_*`).
- **Weakest part:** EEG (0.278 balanced accuracy, frozen encoder, CPU-trained) — present it as a working *pipeline* whose model needs GPU fine-tuning, not as a finished classifier.
- **Biggest structural debt:** djongo (freezes Django + Python versions) and synchronous inference (blocks scaling).
- **Biggest scientific gap:** the multimodal combination is presentational, not learned — closing it requires a paired clinical dataset, which is the natural continuation of this PFE.
