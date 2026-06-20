# Implement ECG explainability (SHAP) — mirror the existing MRI XAI

You are working in an existing monorepo: a multimodal medical-AI platform (Master's
PFE — brain MRI, 12-lead ECG, echocardiogram, EEG, with a combined PDF report).
The **MRI** classifier already has post-hoc explainability (Grad-CAM + Captum
GradientShap, exposed at `POST /api/mri/{id}/explain/`). The **ECG** model has
none. Your job: add **SHAP explainability for the ECG model**, mirroring the MRI
XAI patterns exactly. Work autonomously and verify as you go; only stop on a
genuine blocker.

## Before you write any code

1. Read `CLAUDE.md` (repo root) in full — architecture, hard version constraints,
   the two backend contracts (doctor isolation + result-envelope), the
   test-runner behaviour, and the "looks like a bug but isn't" notes. Treat it as
   authoritative.
2. Read the **MRI XAI you are mirroring**:
   - `backend/apps/inference/explainers/shap_attr.py` — `swin_gradient_shap()`,
     Captum **GradientShap** on the Swin classifier. **This is your template.**
   - `backend/apps/inference/explainers/base.py` (shared helpers).
   - the `explain_mri()` function in `backend/apps/inference/mri_pipeline.py` (how
     a SHAP pass is wrapped into the `{status, ...}` envelope + writes a PNG to media).
   - `MRIExplainView` in `backend/apps/mri/views.py` (`POST /api/mri/{id}/explain/`)
     — the endpoint pattern: resolve via `scope_by_patient`, run under
     `run_inference_with_timeout`, return `signed_media_url(...)`, `_relative_to_media(...)`.
3. Read the **ECG code you are extending**:
   - `backend/apps/inference/ecg_pipeline.py` — `analyze_ecg`, `_scalar_probability`,
     how `load_ecg_signal` is used (returns a `(12, 5000)` signal @ 500 Hz + a
     quality dict), the 7 pathologies, `DETECTION_THRESHOLDS`, and the per-pathology
     probability loop. Note how it builds its 12-lead matplotlib plot (Agg backend).
   - `backend/apps/ecg/{views.py,urls.py,serializers.py,models.py}`. (`ecg/views.py`
     already imports `scope_by_patient` from `apps.patients.access`.)
   - `backend/apps/inference/__init__.py` (what's exported: `run_inference_with_timeout`,
     `ModelLoader`, `analyze_*`).
4. Read the **frontend** you'll touch: `frontend/src/modules/ECG/ECGResult.jsx`,
   `frontend/src/services/ecgService.js`, `frontend/src/services/api.js`,
   `frontend/src/i18n/locales/ecg.js`, and how `MRIResult.jsx` renders its
   Grad-CAM/SHAP for reference. Follow the theme + i18n conventions in
   `Dont Need Files/frontend/THEME-I18N-CONVENTIONS.md` (CSS-variable tokens via
   `useTokens`, strings via `useI18n`, **identical EN/FR key trees**).
5. Use the `superpowers` **test-driven-development** and **verification-before-completion**
   skills. Always verify with the commands in the Verification section before
   claiming anything works.

## Hard constraints (do not violate)

- **Python 3.10/3.11**, **Django 3.2.25 LTS**, **djongo** over MongoDB. Do not upgrade.
- The test runner auto-swaps `DATABASES['default']` to in-memory SQLite when
  `'test' in sys.argv` (see `backend/core/settings.py`), so `APITestCase` DB tests
  run on a fresh checkout.
- Backend apps live under `backend/apps/`, registered as `apps.<name>`.
- **Contract 1 — doctor isolation.** Every queryset over patient-owned data filters
  by the requesting user through `apps/patients/access.py`
  (`scope_by_patient` / `get_patient_or_404`): a **doctor** sees only patients
  assigned to them, a **technician** sees all. The new `/explain/` endpoint MUST
  resolve the analysis through `scope_by_patient` — a cross-user id returns **404**,
  never a leak.
- **Contract 2 — structured failure.** `explain_ecg(...)` returns a plain dict
  `{status, ...fields, error?, error_type?}` and must **never raise into the DRF
  view** (catch and convert to the envelope, exactly like `analyze_ecg`).
- `captum>=0.7,<0.8` is already a dependency (from the MRI XAI). torch / ecglib /
  matplotlib / scipy are all installed — no new dependencies.
- **GradientShap must run OUTSIDE `torch.no_grad()`** (it backpropagates). The
  normal `analyze_ecg` forward runs under `no_grad`; the explainer must not.
- ECG inference is **synchronous and single-threaded**; the SHAP pass calls model
  gradients on the shared model singleton — safe today only because requests are
  synchronous. Mirror the MRI thread-safety caveat in a comment; don't parallelize.

## What to build

Locked design decisions:

- **SHAP via Captum `GradientShap`** on the 1-D DenseNet — NOT KernelSHAP/LIME
  (a 12×5000 = 60,000-feature signal makes coalition methods infeasible in the
  request thread). GradientShap is the fast, faithful, gradient-based variant,
  identical in spirit to `swin_gradient_shap`.
- **Target = the primary diagnosis** (the pathology with the highest probability)
  by default; accept an optional `pathology` param to attribute any one of the 7
  (`AFIB, 1AVB, STACH, SBRAD, RBBB, LBBB, PVC`).
- **On-demand endpoint only** — do NOT add it to normal `analyze_ecg` (keep
  inference fast). **No new model field, no migration** (mirror the MRI *on-demand*
  SHAP, which persists nothing).
- **Output:** a 12-lead plot with the SHAP saliency shaded over each lead trace,
  plus a **per-lead importance** vector (Σ|attribution| per lead → which of I…V6
  drove the call) and the **top-3 leads**.

### Backend

1. **`backend/apps/inference/explainers/ecg_shap.py`** (new) —
   `ecg_gradient_shap(model, signal_12x5000, n_samples=32) -> np.ndarray (12, 5000)`:
   abs-summed, min-max normalised to [0,1] attribution. Mirror `shap_attr.py`:
   build an input tensor shaped `(1, 12, 5000)` on the model's device; two-point
   baseline (`zeros` + signal-mean); `target=0` (the single-output sigmoid head);
   run outside `no_grad`. Also expose a helper to reduce the map to per-lead
   importance (`abs sum over time`, normalised).

2. **`explain_ecg(file_path, pathology=None)`** in `ecg_pipeline.py` (next to
   `analyze_ecg`; export it from `backend/apps/inference/__init__.py`). Returns the
   envelope and **never raises**. Steps: load the signal via the same
   `load_ecg_signal` `analyze_ecg` uses → `(12, 5000)`; get the models via
   `ModelLoader().get_ecg_models()`; choose the target pathology (the `pathology`
   arg if valid, else compute the 7 probabilities and take the argmax = primary);
   run `ecg_gradient_shap` on the chosen model; render the 12-lead SHAP plot
   (matplotlib Agg, same style as `analyze_ecg`'s plot) and write the PNG to
   `MEDIA_ROOT/ecg/explanations/<input-stem>_<pathology>.png` (stable name so
   re-runs overwrite — no accumulation). Return
   `{status:'success', shap_path, pathology, probability, per_lead_importance:
   {lead: score for the 12 canonical leads}, top_leads:[...]}`. On any failure
   return `{status:'failed', error, error_type}`.

3. **`ECGExplainView`** in `backend/apps/ecg/views.py` + route
   `path('<int:pk>/explain/', ECGExplainView.as_view(), name='explain')` in
   `backend/apps/ecg/urls.py`. Mirror `MRIExplainView` exactly:
   - `permission_classes = [IsAuthenticated]`.
   - `analysis = get_object_or_404(scope_by_patient(request.user, ECGAnalysis.objects.all()), pk=pk)`.
   - read an optional `pathology` from `request.data`.
   - `result = run_inference_with_timeout(lambda p: explain_ecg(p, pathology), analysis.file.path, 300)`
     (or adapt the timeout helper's signature — see how `MRIExplainView` calls it).
   - on success, replace `result['shap_path']` with
     `signed_media_url(request, _relative_to_media(result['shap_path']))` and return
     `200`; on failure return the envelope with `502`.
   - reuse `_relative_to_media` if `ecg/views.py` already has it, else add the same
     helper used in `echo/views.py`; import `signed_media_url` from `core.media`.

### Frontend

4. **`ecgService.js`** — add
   `explain: (id, pathology) => api.post(\`/ecg/${id}/explain/\`, pathology ? { pathology } : {}).then(r => r.data)`.

5. **`ECGResult.jsx`** — add an **"Explain (SHAP)"** button that calls
   `ecgService.explain(id, pathology?)`, with loading + error (toast) states, then
   renders the returned SHAP image (`<img src={shap_path}>` — it's a signed URL),
   the per-lead importance, and the top-3 leads. Optionally a small dropdown to
   pick which of the 7 pathologies to explain (default = primary). Match the
   existing ECGResult layout and theme tokens.

6. **i18n** — add keys to `frontend/src/i18n/locales/ecg.js` (EN **and** FR,
   identical key trees): the button label, panel title, loading, error,
   per-lead-importance label, top-leads label, pick-pathology label, and a short
   **honesty caveat** line ("signal-level saliency — which leads/segments drove the
   prediction — not clinical reasoning"). Do not translate lead names (I, II, …V6)
   or pathology abbreviations.

## Verification (run these; everything must pass before you call it done)

Backend (from `backend/`, venv active):
```
python manage.py check
python manage.py makemigrations --check --dry-run      # MUST be "No changes detected" (no model change)
python manage.py test apps.ecg                          # your new explain tests (need ecglib weights; run locally)
python manage.py test tests.test_doctor_isolation tests.test_health   # still green
```
Frontend (from `frontend/`):
```
npm run lint     # MUST exit 0
npm test         # Vitest — all green; add the ECGResult explain test
npm run build
```

Add tests:
- **Backend** — `explain_ecg` on a tiny synthetic 12-lead CSV (columns
  `I,II,III,aVR,aVL,aVF,V1,V2,V3,V4,V5,V6`, ~5000 rows @ 500 Hz) returns
  `status == 'success'`, writes a `.png`, and `per_lead_importance` has 12 leads;
  an unreadable/garbage CSV returns `{status:'failed', ...}` and **does not raise**.
  `ECGExplainView`: a doctor NOT assigned the patient gets **404** (isolation); the
  owner (or a technician) gets **200** with a signed `shap_path`; an invalid
  `pathology` value is handled (decide 400 vs fall-back-to-primary and make it
  explicit + tested). These need the heavy ECG libs — run locally (CI only runs the
  weight-free suites).
- **Frontend** — `ECGResult` renders the Explain button; clicking it calls
  `ecgService.explain` (mock the service) and shows the returned image.

## Definition of done

- `POST /api/ecg/{id}/explain/` returns a SHAP saliency PNG (signed URL) + per-lead
  importance for the primary pathology (or a chosen one), is doctor-isolated
  (cross-user id → 404), and **never 500s** on bad input (clean `{status:'failed'}`
  envelope instead).
- The ECG result page has a working **Explain (SHAP)** button showing the
  attribution + per-lead importance, with the honest "signal-level saliency" caveat.
- **No migration** was needed; no existing contract (doctor isolation, result
  envelope) is broken; lint is clean; EN/FR key trees stay identical; every
  verification command passes.
- Report what you verified with the actual command output.

## Suggested order

1. `ecg_gradient_shap` + a direct unit test on a synthetic signal (assert shape
   `(12,5000)`, values in [0,1]) → verify.
2. `explain_ecg` + envelope tests (success on synthetic CSV, clean failure on
   garbage) → verify.
3. `ECGExplainView` + URL + isolation test (cross-user 404, owner 200) → verify.
4. Frontend service + button + i18n + Vitest test.
5. Full verification sweep, then a final self-review against the two backend
   contracts and EN/FR parity.

Keep edits focused, follow the existing MRI XAI patterns precisely, and don't
oversell the result in the UI — SHAP here is signal-level saliency, not a clinical
diagnosis rationale.
