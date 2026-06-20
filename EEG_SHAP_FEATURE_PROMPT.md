# Implement EEG explainability (SHAP) — mirror the existing MRI + ECG XAI

You are working in an existing monorepo: a multimodal medical-AI platform (Master's PFE —
brain MRI, 12-lead ECG, echocardiogram, EEG, with a combined PDF report). The **MRI**
classifier has post-hoc explainability (Grad-CAM + Captum GradientShap, `POST /api/mri/{id}/explain/`)
and the **ECG** model now has SHAP explainability (Captum GradientShap, `POST /api/ecg/{id}/explain/`).
The **EEG** model (BIOT/IIIC 6-class harmful-brain-activity screening) has none. Your job: add
**SHAP explainability for the EEG model**, mirroring the existing XAI patterns exactly — the
**ECG SHAP code is your closest template** (same "signal modality" shape). Work autonomously and
verify as you go; only stop on a genuine blocker.

## Before you write any code

1. Read `CLAUDE.md` (repo root) in full — architecture, hard version constraints, the two backend
   contracts (doctor isolation + result-envelope), the test-runner behaviour, and the "looks like
   a bug but isn't" notes (especially: **the EEG BIOT/IIIC head is NOT bundled** — `get_eeg_model()`
   raises a clear `FileNotFoundError` if absent, and `warmup()` does not preload EEG). Treat it as
   authoritative.
2. Read the **XAI you are mirroring** (ECG is the primary template; MRI is the original pattern):
   - `backend/apps/inference/explainers/ecg_shap.py` — `ecg_gradient_shap()` + `per_lead_importance()`.
     **This is your template** (adapt "lead" → EEG "channel").
   - `backend/apps/inference/ecg_pipeline.py` — `explain_ecg(file_path, pathology=None)`: how a SHAP
     pass is wrapped into the `{status, ...}` envelope, the target-selection (argmax-or-requested,
     invalid → fall back) logic, the plot rendering, and the stable-named PNG written to media.
   - `backend/apps/ecg/views.py` — `ECGExplainView` (`POST /api/ecg/{id}/explain/`): resolve via
     `scope_by_patient`, `run_inference_with_timeout`, `signed_media_url(...)`, `_relative_to_media(...)`,
     502 on failure.
   - `backend/apps/inference/explainers/shap_attr.py` + `base.py` + `explain_mri()` in `mri_pipeline.py`
     + `MRIExplainView` — the original multi-class pattern (the EEG head is **multi-class softmax**, so
     the `target = predicted-class (argmax)` selection mirrors MRI's Swin, not ECG's single sigmoid).
3. Read the **EEG code you are extending**:
   - `backend/apps/inference/eeg_pipeline.py` — `analyze_eeg`: how the `.edf` is loaded, how
     `eeg_preprocess.py` produces the model input (get the **exact input tensor shape**, channel set,
     and sampling rate), the **6 IIIC class labels** (canonical order), the per-class probability /
     softmax, and how it builds its multi-channel matplotlib plot (Agg backend).
   - `backend/apps/inference/model_loader.py` — `get_eeg_model()` (builds `BIOTClassifier`, loads the
     bundled encoder + the fine-tuned `biot_iiic.pt` head). Note `get_device()`.
   - `backend/apps/inference/biot/` — the vendored `BIOTClassifier` (read its `forward` signature /
     output shape) and `backend/apps/inference/eeg_preprocess.py` (the shared train/inference-parity
     preprocessing + the channel/montage list).
   - `backend/apps/eeg/{views.py,urls.py,serializers.py,models.py}`.
   - `backend/apps/inference/__init__.py` (exports: `run_inference_with_timeout`, `ModelLoader`,
     `analyze_*`, `explain_mri`, `explain_ecg`).
4. Read the **frontend** you'll touch: `frontend/src/modules/EEG/EEGResult.jsx`,
   `frontend/src/services/eegService.js`, `frontend/src/services/api.js`,
   `frontend/src/i18n/locales/eeg.js`, and the **`frontend/src/modules/ECG/ECGExplain.jsx`** panel
   (+ its `ECGExplain.test.jsx`) as the component template — note its chooser stays visible so you
   can re-run / pick another target (no dead-end once a result shows). Follow the theme + i18n
   conventions in `frontend/THEME-I18N-CONVENTIONS.md` (CSS-variable tokens, strings via `useI18n`,
   **identical EN/FR key trees**).
5. Use the `superpowers` **test-driven-development** and **verification-before-completion** skills.
   Always verify with the Verification commands before claiming anything works.

## Hard constraints (do not violate)

- **Python 3.10/3.11**, **Django 3.2.25 LTS**, **djongo** over MongoDB. Do not upgrade.
- The test runner auto-swaps `DATABASES['default']` to in-memory SQLite when `'test' in sys.argv`
  (`backend/core/settings.py`), so `APITestCase` DB tests run on a fresh checkout.
- Backend apps live under `backend/apps/`, registered as `apps.<name>`.
- **Contract 1 — doctor isolation.** The new `/explain/` endpoint MUST resolve the analysis through
  `scope_by_patient` — a cross-user id returns **404**, never a leak.
- **Contract 2 — structured failure.** `explain_eeg(...)` returns a plain dict
  `{status, ...fields, error?, error_type?}` and must **never raise into the DRF view** (catch and
  convert to the envelope, exactly like `analyze_eeg` / `explain_ecg`).
- `captum>=0.7,<0.8` is already a dependency. torch / pyedflib / matplotlib / scipy are installed —
  **no new dependencies.**
- **GradientShap must run OUTSIDE `torch.no_grad()`** (it backpropagates). The normal `analyze_eeg`
  forward runs under `no_grad`; the explainer must not.
- EEG inference is **synchronous and single-threaded**; the SHAP pass calls model gradients on the
  shared model singleton — safe today only because requests are synchronous. Mirror the MRI/ECG
  thread-safety caveat in a comment; don't parallelize.
- **The BIOT/IIIC head is NOT bundled.** Backend explain tests MUST **skip gracefully** when the EEG
  model can't load (try `get_eeg_model()`; on `FileNotFoundError`/load error → `skipTest`), so a fresh
  checkout without the head doesn't hard-fail. Locally (head present) they run for real. CI only runs
  the weight-free suites.

## What to build

Locked design decisions:

- **SHAP via Captum `GradientShap`** on the BIOT classifier — the fast, faithful gradient-based SHAP
  variant (a multi-channel × thousands-of-samples EEG makes coalition methods like KernelSHAP/LIME
  infeasible in the request thread). Identical in spirit to `ecg_gradient_shap` / `swin_gradient_shap`.
  **Known risk to verify early:** confirm GradientShap actually backprops through BIOT's front-end
  (it uses an STFT-based patch embedding; `torch.stft` is differentiable, so it should). If a
  non-differentiable op blocks it, fall back to Captum `IntegratedGradients` (still a gradient /
  Shapley-style attribution), **document the swap**, and keep the public framing "SHAP-style saliency."
- **Target = the predicted class** (argmax of the 6 IIIC softmax) by default; accept an optional
  `target_class` param to attribute any one of the 6 classes (by canonical name or index). An invalid
  value **falls back to the predicted class** (kept explicit via the returned field) — mirror
  `explain_ecg`'s invalid-pathology handling; never raise.
- **On-demand endpoint only** — do NOT add it to normal `analyze_eeg`. **No new model field, no
  migration** (mirror the MRI/ECG on-demand SHAP, which persist nothing).
- **Output:** a multi-channel EEG plot with the SHAP saliency shaded over each channel trace, plus a
  **per-channel importance** vector (Σ|attribution| per channel → which electrodes drove the call) and
  the **top-3 channels**.

### Backend

1. **`backend/apps/inference/explainers/eeg_shap.py`** (new) —
   `eeg_gradient_shap(model, signal, n_samples=32) -> np.ndarray (C, T)`: abs, min-max normalised to
   [0,1]. Mirror `ecg_shap.py`: build the input tensor in the **exact shape BIOT expects** (read it
   from `analyze_eeg`/`eeg_preprocess`) on the model's device; two-point baseline (`zeros` + signal
   mean); run outside `no_grad`; a robust `forward` wrapper handling tuple output and ensuring 2-D
   `(N, 6)` so `target` indexes a class. Also expose `per_channel_importance(attr_map, channel_names)`
   (abs sum over time, normalised). Include the thread-safety caveat comment.

2. **`explain_eeg(file_path, target_class=None)`** in `eeg_pipeline.py` (next to `analyze_eeg`; export
   it from `backend/apps/inference/__init__.py`). Returns the envelope and **never raises**. Steps:
   load + preprocess the `.edf` exactly as `analyze_eeg` (so the attribution matches what the model
   sees); `model = ModelLoader().get_eeg_model()`; compute the 6-class softmax; choose the target
   (the `target_class` arg if valid, else the argmax = predicted); run `eeg_gradient_shap` on the model
   for that target; render the multi-channel SHAP plot (matplotlib Agg, same style as `analyze_eeg`'s
   plot) and write the PNG to `MEDIA_ROOT/eeg/explanations/<input-stem>_<class>.png` (stable name →
   overwrite). Return `{status:'success', shap_path, predicted_class, target_class, class_probabilities,
   probability, per_channel_importance:{channel: score}, top_channels:[...]}`. On any failure return
   `{status:'failed', error, error_type}`.

3. **`EEGExplainView`** in `backend/apps/eeg/views.py` + route
   `path('<int:pk>/explain/', EEGExplainView.as_view(), name='explain')` in `backend/apps/eeg/urls.py`.
   Mirror `ECGExplainView` exactly: `permission_classes=[IsAuthenticated]`; resolve via
   `get_object_or_404(scope_by_patient(request.user, EEGAnalysis.objects.all()), pk=pk)`; read an
   optional `target_class` from `request.data`;
   `result = run_inference_with_timeout(lambda p: explain_eeg(p, target_class), analysis.file.path, 300)`;
   on success replace `result['shap_path']` with `signed_media_url(request, _relative_to_media(result['shap_path']))`
   and return 200; on failure return the envelope with 502. Reuse/add `_relative_to_media` as in
   `ecg/views.py`; import `signed_media_url` from `core.media`.

### Frontend

4. **`eegService.js`** — add
   `explain: (id, targetClass) => api.post(\`/eeg/${id}/explain/\`, targetClass ? { target_class: targetClass } : {}).then(r => r.data)`.

5. **`EEGExplain.jsx`** (new, mirror `ECGExplain.jsx`) — an **"Explain (SHAP)"** button + a dropdown to
   pick which of the 6 IIIC classes to explain (default = predicted), with loading + error (toast)
   states. Keep the chooser **always visible** so the user can pick another class and re-run (button
   relabels to "Re-run"); render the returned SHAP image (`<img src={shap_path}>` — signed URL), the
   per-channel importance bars, and the top-3 channels. Match the EEGResult layout + theme tokens.
   Render it from `EEGResult.jsx` when the analysis is completed.

6. **i18n** — add an `explain` block to `frontend/src/i18n/locales/eeg.js` (EN **and** FR, identical
   key trees): button label, panel title, running, error, rerun, per-channel-importance label,
   top-channels label, pick-class label, primary/predicted option, and a short **honesty caveat**
   ("signal-level saliency — which channels/segments drove the prediction — not clinical reasoning").
   Do not translate channel names or the IIIC class abbreviations.

### 3D / topographic presentation (SHAP-driven) — genuine upgrade

Today `frontend/src/modules/EEG/eegAnatomy.js` only maps the IIIC class to generalized (whole
cerebrum) vs lateralized (one hemisphere, **side NOT localized** by the model). SHAP **per-channel
importance is electrode-localized**, so it drives a genuinely more accurate visualization — add it:

- **2D scalp topomap (rigorous core, recommended):** in `EEGExplain.jsx`, render a small head/scalp
  diagram with the 16 electrode positions colored by `per_channel_importance` (the standard EEG
  presentation). Use the montage positions from `eeg_preprocess.py` (10–20 coordinates); if none are
  defined there, add a small fixed 10–20 lookup for the BIOT 16-channel montage.
- **3D brain marker (nice-to-have, reuse the existing mechanism):** `Anatomy3DPanel` already supports a
  `gradcamFocus` marker `{x, y, severity}` (a distinct-hue "where the model looked" dot, used by the MRI
  XAI). Extend `mapEegToHighlight` to **optionally accept the SHAP result** and, from the top channel(s),
  project an approximate scalp coordinate into the brain panel as a `gradcamFocus`-style marker (and/or
  choose the hemisphere from whether the top channels are left vs right). This makes the 3D reflect the
  electrodes the model actually used — **including the side for lateralized patterns, which the bare
  class label cannot give**.

Back-compat: keep `mapEegToHighlight`'s current behavior when no SHAP result is present; only enrich it
when the explanation is available — exactly as `mapMriToHighlight` does with the Grad-CAM peak. Honesty
(state in the caption + doc): resolution is the **16-channel montage** (coarse), the marker is an
approximate scalp projection, and per-channel SHAP shows *which electrodes drove this prediction*, not a
validated EEG source localization. Add the topomap/marker i18n labels + caveat (EN + FR identical).

## Verification (run these; everything must pass before you call it done)

Backend (from `backend/`, venv active):
```
python manage.py check
python manage.py makemigrations --check --dry-run      # MUST be "No changes detected" (no model change)
python manage.py test apps.eeg                          # your new explain tests (skip if BIOT head absent)
python manage.py test tests.test_doctor_isolation tests.test_health   # still green
```
Frontend (from `frontend/`):
```
npm run lint     # MUST exit 0 (no NEW warnings from your files)
npm test         # Vitest — all green; add the EEGExplain test
npm run build
```

Add tests:
- **Backend** (`apps/eeg/tests.py`, guard with `skipUnless` the EEG model loads) — `eeg_gradient_shap`
  on a real BIOT model + a synthetic EEG tensor returns shape `(C, T)`, values in `[0,1]`; `explain_eeg`
  on a tiny synthetic `.edf` (build one with `pyedflib` matching the channels/fs `eeg_preprocess`
  expects, or reuse `tools/generate_sample_eeg.py`) returns `status=='success'`, writes a `.png`, and
  `per_channel_importance` has the expected channel count; a garbage/unreadable `.edf` returns
  `{status:'failed', ...}` and **does not raise**. `EEGExplainView`: a doctor NOT assigned the patient
  gets **404**; the owner (or a technician) gets **200** with a signed `shap_path`; an invalid
  `target_class` falls back to the predicted class and still returns 200. (Mirror `apps/ecg/tests.py`.)
- **Frontend** — `EEGExplain` renders the Explain button; clicking it calls `eegService.explain` (mock
  the service) and shows the returned image. (Mirror `ECGExplain.test.jsx`.)

## Definition of done

- `POST /api/eeg/{id}/explain/` returns a SHAP saliency PNG (signed URL) + per-channel importance for
  the predicted class (or a chosen one), is doctor-isolated (cross-user id → 404), and **never 500s**
  on bad input (clean `{status:'failed'}` envelope with 502 instead).
- The EEG result page has a working **Explain (SHAP)** button showing the attribution + per-channel
  importance + top channels, with the honest "signal-level saliency" caveat, and lets you re-run for a
  different class.
- A **SHAP-driven scalp topomap** of per-channel importance is shown, and (if feasible) the 3D brain
  panel gets an electrode-localized `gradcamFocus` marker via an enriched `mapEegToHighlight` — with the
  16-channel-resolution honesty caveat, and back-compatible when no explanation is present.
- **No migration** was needed; no existing contract (doctor isolation, result envelope) is broken;
  lint is clean; EN/FR key trees stay identical; every verification command passes (EEG-head-dependent
  backend tests skip cleanly when the head is absent, run for real when present).
- Report what you verified with the **actual command output**.

## Suggested order

1. `eeg_gradient_shap` + per-channel helper + a direct unit test on a synthetic EEG tensor (assert
   shape `(C, T)`, values in [0,1]); **verify GradientShap backprops through BIOT** here (fall back to
   IntegratedGradients + document if it doesn't) → verify.
2. `explain_eeg` + envelope tests (success on synthetic `.edf`, clean failure on garbage) → verify.
3. `EEGExplainView` + URL + isolation test (cross-user 404, owner 200) → verify.
4. Frontend service + `EEGExplain.jsx` + i18n + Vitest test; wire into `EEGResult.jsx`.
5. Full verification sweep, then a final self-review against the two backend contracts and EN/FR parity.

Keep edits focused, follow the existing ECG/MRI XAI patterns precisely, and don't oversell — SHAP here
is signal-level saliency (which channels/segments drove the prediction), not a clinical diagnosis rationale.
