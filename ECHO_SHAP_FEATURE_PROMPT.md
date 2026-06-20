# Implement Echo explainability (SHAP) — mirror the existing MRI + ECG + EEG XAI

You are working in an existing monorepo: a multimodal medical-AI platform (Master's PFE —
brain MRI, 12-lead ECG, echocardiogram, EEG, with a combined PDF report). **MRI** has
explainability (Grad-CAM + Captum GradientShap, `POST /api/mri/{id}/explain/`) and **ECG**
has SHAP (Captum GradientShap, `POST /api/ecg/{id}/explain/`). The **Echo** model
(EchoNet-Dynamic: an R(2+1)D-18 video model that regresses left-ventricle ejection fraction
+ a DeepLabV3 LV segmenter) has none. Your job: add **SHAP explainability for the Echo EF
model**, mirroring the existing XAI patterns. Work autonomously and verify as you go; only
stop on a genuine blocker.

## Read this first — what's different about Echo (and the honesty rules)

1. **Echo is a *video* and the primary output is a *regression* (EF %), not a classification.**
   So the SHAP `target` is the **single EF output** (target index 0), like a one-output head —
   *not* an argmax over classes. The attribution is **spatiotemporal**: `(T, H, W)` over the
   sampled clip → "which frames and which regions of the 2D view drove the EF estimate."
2. **EchoNet gives a GLOBAL EF from a SINGLE 2D apical plane** — it does NOT measure regional
   wall motion. The existing `frontend/src/modules/Echo/echoAnatomy.js` *deliberately* refuses
   to implicate any wall (anterior/inferior/septal) and only highlights the LV globally. **Honor
   this.** The SHAP win for Echo is a **2D saliency overlay on the frames + a temporal
   frame-importance curve**, NOT a fabricated 3D regional highlight. Do **not** invent regional
   wall localization on the 3D heart (see the 3D section below).
3. **Honest framing everywhere:** this is **signal/pixel-level saliency** — which frames and
   image regions the model attended to when estimating EF — **not** a clinical rationale and
   **not** regional wall-motion analysis.

## Before you write any code

1. Read `CLAUDE.md` (repo root) in full — architecture, hard version constraints, the two
   backend contracts (doctor isolation + result-envelope), the test-runner behaviour, and the
   "looks like a bug but isn't" notes (especially: **EchoNet weights are NOT bundled and NOT
   auto-downloaded** — `get_echo_models()` raises a clear `FileNotFoundError` if absent, and
   `warmup()` does not preload echo). Authoritative.
2. Read the **XAI you are mirroring** (ECG/EEG are the closest signal templates; MRI is the
   original):
   - `backend/apps/inference/explainers/ecg_shap.py` — `ecg_gradient_shap()` + per-axis
     importance helper. Your template for the GradientShap call + abs/min-max normalisation.
   - `backend/apps/inference/ecg_pipeline.py` — `explain_ecg(...)`: envelope wrapping, target
     selection, plot rendering, stable-named PNG to media; mirror this structure for `explain_echo`.
   - `backend/apps/ecg/views.py` — `ECGExplainView`: `scope_by_patient`, `run_inference_with_timeout`,
     `signed_media_url`, `_relative_to_media`, 502 on failure.
   - `backend/apps/inference/explainers/shap_attr.py` + `explain_mri()` — the single-target
     GradientShap pattern.
3. Read the **Echo code you are extending**:
   - `backend/apps/inference/echo_pipeline.py` — `analyze_echo`; `load_echo_video` →
     `(F, 112, 112, 3)`; `_normalize` → `(F, 3, 112, 112)`; `_predict_ef` builds a clip
     `(1, 3, CLIP_LEN=32, 112, 112)` (stride `CLIP_PERIOD`) and calls `ef_model(clip).item()`;
     `_predict_segmentation`; the constants (`FRAME_SIZE`, `CLIP_LEN`, `CLIP_PERIOD`, `MAX_CLIPS`,
     `ECHONET_MEAN/STD`); the ED-frame red-mask overlay it already renders; the result envelope.
   - `backend/apps/inference/model_loader.py` — `get_echo_models()` → `(seg_model, ef_model)`
     (DeepLabV3-ResNet50 + R(2+1)D-18). Note `get_device()`.
   - `backend/apps/echo/{views.py,urls.py,serializers.py,models.py}`.
   - `backend/apps/inference/__init__.py` (exports: `run_inference_with_timeout`, `ModelLoader`,
     `analyze_*`, `explain_mri`, `explain_ecg`).
4. Read the **frontend** you'll touch: `frontend/src/modules/Echo/EchoResult.jsx`,
   `frontend/src/services/echoService.js`, `frontend/src/services/api.js`,
   `frontend/src/i18n/locales/echo.js`, `frontend/src/modules/Echo/echoAnatomy.js`,
   `frontend/src/components/three/Anatomy3DPanel.jsx`, and the
   **`frontend/src/modules/ECG/ECGExplain.jsx`** panel (+ `ECGExplain.test.jsx`) as the
   component template (chooser/result stays visible; re-run; signed image). Follow
   `frontend/THEME-I18N-CONVENTIONS.md` (tokens via `useTokens`, strings via `useI18n`,
   **identical EN/FR key trees**).
5. Use the `superpowers` **test-driven-development** and **verification-before-completion** skills.
   Verify with the Verification commands before claiming anything works.

## Hard constraints (do not violate)

- **Python 3.10/3.11**, **Django 3.2.25 LTS**, **djongo**. Do not upgrade.
- Test runner auto-swaps to in-memory SQLite when `'test' in sys.argv`.
- Backend apps under `backend/apps/`, registered as `apps.<name>`.
- **Contract 1 — doctor isolation.** Resolve the analysis through `scope_by_patient` — cross-user
  id → **404**, never a leak.
- **Contract 2 — structured failure.** `explain_echo(...)` returns `{status, ...fields, error?,
  error_type?}` and must **never raise into the DRF view**.
- `captum>=0.7,<0.8`, torch, torchvision, opencv (video decode), matplotlib, numpy are installed —
  **no new dependencies.**
- **GradientShap must run OUTSIDE `torch.no_grad()`** (it backpropagates). `analyze_echo`'s forwards
  run under `no_grad`; the explainer must not.
- Echo inference is **synchronous and single-threaded**; the SHAP pass calls gradients on the shared
  model singleton — mirror the MRI/ECG thread-safety caveat comment; don't parallelize.
- **EchoNet weights are NOT bundled.** Backend explain tests MUST **skip gracefully** when the echo
  models can't load (try `get_echo_models()`; on `FileNotFoundError` → `skipTest`). Locally (weights
  present) they run for real; CI only runs weight-free suites.
- **CPU cost:** R(2+1)D-18 over a 32-frame clip is heavy. Attribute **one representative clip** (the
  same clip construction `_predict_ef` uses, e.g. the first/median clip), use a **smaller default
  `n_samples` (e.g. 8)** for the video model, and stay within the 300 s timeout. (Mention an optional
  GPU path; keep CPU the default.)

## What to build

Locked design decisions:

- **SHAP via Captum `GradientShap`** on the **EF R(2+1)D-18 model**, `target=0` (the single EF
  regression output). Spatiotemporal attribution `(1, 3, T, H, W)` → abs, **sum over the channel
  axis** → `(T, H, W)`, min-max normalised to `[0,1]`. (Attributing the segmentation model is out of
  scope for v1 — EF is the clinically primary output; you may leave a documented hook for it.)
- **On-demand endpoint only** — do NOT add it to `analyze_echo`. **No new model field, no migration.**
- **Output:**
  - a **2D saliency overlay montage** — the SHAP saliency over a few representative frames (reuse the
    ED frame `analyze_echo` already computes; add the ES frame and 1–2 mid-clip frames), saved as a PNG;
  - a **temporal frame-importance curve** (Σ saliency per frame over the clip → which frames, ≈
    systole/diastole, drove EF) + the **top-3 frames** (their clip indices / approximate times);
  - the predicted **EF** value echoed back for context.

### Backend

1. **`backend/apps/inference/explainers/echo_shap.py`** (new) —
   `echo_gradient_shap(ef_model, clip_3thw, n_samples=8) -> np.ndarray (T, H, W)`: build the input
   tensor `(1, 3, T, H, W)` on the model's device (the same normalised clip `_predict_ef` feeds);
   two-point baseline (`zeros` + clip mean); `target=0`; run outside `no_grad`; a robust `forward`
   wrapper (handle tuple, ensure 2-D `(N,1)`). abs → sum over channel → min-max `[0,1]`. Also expose
   `frame_importance(attr_thw) -> np.ndarray (T,)` (Σ over H,W per frame, normalised). Thread-safety
   caveat comment.

2. **`explain_echo(file_path, n_samples=8)`** in `echo_pipeline.py` (next to `analyze_echo`; export
   from `apps/inference/__init__.py`). Returns the envelope, **never raises**. Steps: load + normalise
   the video exactly as `analyze_echo`; `seg_model, ef_model = ModelLoader().get_echo_models()`; build
   ONE representative clip (reuse `_predict_ef`'s clip construction); `ef = float(ef_model(clip))` for
   context; `saliency = echo_gradient_shap(ef_model, clip)`; `tImp = frame_importance(saliency)`; pick
   top-3 frames; render the overlay montage + temporal curve (matplotlib Agg) and write the PNG to
   `MEDIA_ROOT/echo/explanations/<input-stem>_ef.png` (stable name → overwrite). Return
   `{status:'success', shap_path, ef, target:'ef', frame_importance:[...], top_frames:[...],
   n_frames}`. On any failure → `{status:'failed', error, error_type}`.

3. **`EchoExplainView`** in `backend/apps/echo/views.py` + route
   `path('<int:pk>/explain/', EchoExplainView.as_view(), name='explain')`. Mirror `ECGExplainView`
   exactly: `IsAuthenticated`; `get_object_or_404(scope_by_patient(request.user, EchoAnalysis.objects.all()), pk=pk)`;
   `result = run_inference_with_timeout(explain_echo, analysis.file.path, 300)`; on success replace
   `result['shap_path']` with `signed_media_url(request, _relative_to_media(result['shap_path']))` →
   200; on failure → envelope with 502. Reuse/add `_relative_to_media`; import `signed_media_url` from
   `core.media`.

### Frontend

4. **`echoService.js`** — add `explain: (id) => api.post(\`/echo/${id}/explain/\`, {}).then(r => r.data)`.

5. **`EchoExplain.jsx`** (new, mirror `ECGExplain.jsx`) — an **"Explain (SHAP)"** button (no class
   chooser; EF is a single output) with loading + error (toast) states; keep the control visible so
   the user can re-run (button relabels to "Re-run"). Render the returned saliency montage image
   (`<img src={shap_path}>` — signed URL), the **temporal frame-importance** as a small bar/line, and
   the **top frames**. Render it from `EchoResult.jsx` when the analysis is completed.

6. **i18n** — add an `explain` block to `frontend/src/i18n/locales/echo.js` (EN **and** FR, identical
   key trees): button, title, running, error, rerun, frame-importance label, top-frames label, and the
   honesty caveat ("pixel/temporal saliency over the 2D view — which frames and regions drove the EF
   estimate — not regional wall-motion analysis or a clinical rationale"). Do not translate "EF".

### 3D presentation (honest — read carefully)

Per `echoAnatomy.js`, EchoNet's global EF from a single 2D plane does **not** justify a regional 3D
wall highlight. **Keep the existing 3D heart highlight as-is (global LV by EF category) — do NOT add a
fabricated regional/`gradcamFocus` 3D marker for Echo.** The SHAP enhancement lives in the **2D frame
overlay + temporal curve** only. (If you want a faithful spatial cue, overlay the saliency on the 2D
echo frames — which you already do — not on the 3D mesh.) State this limitation in the panel/doc.

## Verification (run these; everything must pass before you call it done)

Backend (from `backend/`, venv active):
```
python manage.py check
python manage.py makemigrations --check --dry-run      # MUST be "No changes detected" (no model change)
python manage.py test apps.echo                         # your new explain tests (skip if EchoNet weights absent)
python manage.py test tests.test_doctor_isolation tests.test_health   # still green
```
Frontend (from `frontend/`):
```
npm run lint     # MUST exit 0 (no NEW warnings from your files)
npm test         # Vitest — all green; add the EchoExplain test
npm run build
```

Add tests:
- **Backend** (`apps/echo/tests.py`, guard with `skipUnless` the echo models load) — `echo_gradient_shap`
  on the real EF model + a synthetic clip returns shape `(T, H, W)`, values in `[0,1]`; `explain_echo`
  on a tiny synthetic video (build a few-frame `.avi` with OpenCV `VideoWriter`, or reuse
  `tools/` sample helpers) returns `status=='success'`, writes a `.png`, and `frame_importance` has the
  expected length; an unreadable/garbage video returns `{status:'failed', ...}` and **does not raise**.
  `EchoExplainView`: a doctor NOT assigned the patient gets **404**; the owner (or technician) gets
  **200** with a signed `shap_path`. (Mirror `apps/ecg/tests.py`.)
- **Frontend** — `EchoExplain` renders the Explain button; clicking it calls `echoService.explain` (mock
  the service) and shows the returned image. (Mirror `ECGExplain.test.jsx`.)

## Definition of done

- `POST /api/echo/{id}/explain/` returns a SHAP saliency PNG (signed URL) + temporal frame importance +
  top frames for the EF estimate, is doctor-isolated (cross-user id → 404), and **never 500s** on bad
  input (clean `{status:'failed'}` envelope with 502 instead).
- The Echo result page has a working **Explain (SHAP)** button showing the 2D saliency overlay +
  temporal frame importance, with the honest caveat, and a re-run control. The 3D heart panel is
  **unchanged** (global LV only — no fabricated regional 3D).
- **No migration** was needed; no existing contract broken; lint clean; EN/FR key trees identical;
  every verification command passes (echo-weight-dependent tests skip cleanly when weights are absent).
- Report what you verified with the **actual command output**.

## Suggested order

1. `echo_gradient_shap` + `frame_importance` + a direct unit test on a synthetic clip (assert shape
   `(T,H,W)`, values in [0,1]); verify GradientShap backprops through R(2+1)D and time it on CPU (tune
   `n_samples` down if slow) → verify.
2. `explain_echo` + envelope tests (success on a synthetic `.avi`, clean failure on garbage) → verify.
3. `EchoExplainView` + URL + isolation test (cross-user 404, owner 200) → verify.
4. Frontend service + `EchoExplain.jsx` + i18n + Vitest test; wire into `EchoResult.jsx`; leave the 3D
   panel untouched.
5. Full verification sweep, then a final self-review against the two backend contracts, the honest-3D
   rule, and EN/FR parity.

Keep edits focused, follow the existing ECG/MRI XAI patterns precisely, and don't oversell — Echo SHAP
is 2D pixel/temporal saliency over a single ultrasound plane, not regional wall-motion analysis.
