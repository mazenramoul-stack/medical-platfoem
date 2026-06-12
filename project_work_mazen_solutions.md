# Solutions Guide — Remaining Problems

**Companion to** [project_work_mazen_architecture_v2.md](project_work_mazen_architecture_v2.md) §7.
**Compiled:** 2026-06-12.

> **Scope.** The **MRI two-model frontend routing** you asked for is already **implemented** (see [§0 below](#0-done-mri-two-model-routing-implemented)). This file proposes concrete solutions for **every other** problem — ordered *must-do → optional* — with the exact change, a code/command sketch where it helps, the effort, and an acceptance check ("done when…"). Treat it as an implementation backlog; nothing here is applied yet.

---

## 0. DONE — MRI two-model routing (implemented)

The MRI now runs **one model chosen by image type**, decided in the frontend and enforced in the backend:

- **Black/white (grayscale) scan → Classification** (Swin 4-class) — `mode='classify'`.
- **Colored / masked image → Segmentation** (U-Net) — `mode='segment'`.
- Auto-detected in the browser (pixel color-spread), with a manual override toggle; `mode='full'` (both) is still supported for API callers.

Files changed: `backend/apps/inference/mri_pipeline.py` (mode branching), `backend/apps/mri/views.py` (validate + forward `mode`), `frontend/src/services/mriService.js`, `frontend/src/modules/MRI/MRIUpload.jsx` (detection + toggle), `frontend/src/modules/MRI/MRIResult.jsx` (single-model tab default), `frontend/src/i18n/locales/mri.js` (EN/FR keys). Verified: backend compiles, all three modes run on the sample image, ESLint clean, EN/FR parity holds.

---

## 🔴 MUST-DO

### 1. Re-root the git repository at `medical-platform/`
**Problem.** The repo root is `E:\MASTER` (one level above the project), with zero commits and no remote; the `C:` working copy isn't a repo at all. GitHub would ignore `.github/workflows/ci.yml` (it must sit at the repo root), so CI never runs.
**Fix.**
```bash
cd "c:/Users/MAZEN/Desktop/pfe/medical-platform"
git init
# ensure .gitignore covers: backend/venv, node_modules, __pycache__, *.pyc,
#   backend/media/, backend/.env, *.pt/*.ckpt/*.safetensors (large weights)
git add -A && git commit -m "Initial commit: medical-platform at repo root"
gh repo create medical-platform --private --source=. --push
```
**Done when** `git rev-parse --show-toplevel` ends in `medical-platform`, and the Actions tab shows the CI workflow running on push.

### 2. Block registration role self-elevation
**Problem.** `UserRegistrationSerializer` exposes `role` as writable with `AllowAny`, so `POST /api/auth/register {role:"admin"}` creates an admin (`apps/authentication/serializers.py:28`).
**Fix.** Make `role` read-only and force the default in `create()`:
```python
class UserRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('email', 'password', 'first_name', 'last_name', 'role')
        read_only_fields = ('role',)          # <-- role can never be set by the client
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        validated_data.pop('role', None)       # belt-and-suspenders
        return User.objects.create_user(role=User.Role.DOCTOR, **validated_data)
```
**Done when** a registration request including `"role":"admin"` produces a user whose role is `doctor`. Add a test asserting exactly that (see #3).

### 3. Add doctor-isolation tests (your #1 invariant has zero tests)
**Problem.** Every queryset filters by doctor, but nothing tests it.
**Fix.** `backend/apps/patients/tests.py` (or a new `tests/test_isolation.py`):
```python
class DoctorIsolationTest(APITestCase):
    def setUp(self):
        self.a = User.objects.create_user(email='a@t.com', password='x', role='doctor')
        self.b = User.objects.create_user(email='b@t.com', password='x', role='doctor')
        self.pa = Patient.objects.create(doctor=self.a, full_name='PA', age=40, gender='M')

    def _auth(self, u):
        self.client.force_authenticate(u)

    def test_b_cannot_read_a_patient(self):
        self._auth(self.b)
        self.assertEqual(self.client.get(f'/api/patients/{self.pa.id}/').status_code, 404)

    def test_b_cannot_upload_to_a_patient(self):
        self._auth(self.b)
        r = self.client.post('/api/mri/upload/', {'patient_id': self.pa.id, 'file': png_fixture()})
        self.assertIn(r.status_code, (403, 404))
    # repeat for ecg/echo/eeg/report
```
**Done when** doctor B gets 403/404 on every one of doctor A's resources, and the suite runs in CI (needs #10).

### 4. Stop the silent stock-weight fallback (host the fine-tuned weights)
**Problem.** The fine-tuned Swin (95.4 %), the 3 ECG `.pt`, EchoNet, and the BIOT encoder/head are git-ignored with no download path. A fresh clone silently runs the stock Swin (80.4 %) while the report claims 95.4 %.
**Fix (two layers).**
1. **Loud warning now** — make the stock fallback impossible to miss. In `model_loader.get_mri_classifier`, the fallback branch should `logger.warning("MRI: fine-tuned ViT NOT found — running STOCK (~80.4%%). Reproduce with the real numbers requires the fine-tuned weights.")` (already partly there; ensure it fires and is visible). Do the same for ECG (`ft_loaded == 0`) and add a per-pathology info log so AFIB/STACH/SBRAD/LBBB report "stock weights".
2. **Hosted download** — upload the weights (HF Hub or a release asset) and add their URLs to `tools/download_weights.py` so `python tools/download_weights.py` fetches them. Document the command in the README.
**Done when** a fresh clone either downloads the real weights or prints a prominent warning that the numbers won't match the report.

### 5. Fix the "ViT-B/16" → Swin naming everywhere
**Problem.** The deployed classifier is a **Swin Transformer** (`config.json` → `SwinForImageClassification`, `model_type: swin`), but README/VALIDATION/METHODOLOGY/defence notes call it "ViT-B/16". A jury that sees the wrong architecture name doubts you know your own model.
**Fix.** Search-and-correct: `grep -rn "ViT-B/16\|Vision Transformer" maybe\ read/ docs/ Mazen_PFE/ README.md` and replace with "Swin Transformer (Liu et al., ICCV 2021)" where it refers to the brain-tumour classifier. Optionally rename the `vit_brain_tumor/` weights dir (and the `VIT_BRAIN_TUMOR_WEIGHTS` env var) or add a one-line note that the directory name is historical. *(The code already says "Swin/ViT" in the report text after this pass.)*
**Done when** no doc calls the brain-tumour classifier a ViT-B/16 without qualification.

### 6. Reconcile stale "open bug" claims with the fixed code
**Problem.** Several docs still describe already-fixed things as open: the `/media/` PHI hole (fixed via HMAC signing in `core/media.py`), the U-Net double-sigmoid (fixed), the "ECG degrades to 5/7" wording (it's 7/7).
**Fix.** Edit `docs/HOW-IT-WORKS.md`, `docs/PROJECT_FUNCTIONALITY_A_TO_Z.md`, `maybe read/PFE_REPORT_OUTLINE.md`, `maybe read/CHANGELOG.md`, `maybe read/TESTING.md` so these read as **resolved**, not as open bugs / future work. Add a "Resolved" subsection to CHANGELOG referencing the fix commit.
**Done when** no doc lists media-auth, double-sigmoid, or 5/7-ECG as an open problem.

### 7. Pin the EEG headline split and quote 0.278 only
**Problem.** `eval_eeg.py`/`train_eeg_head.py` default `--limit 4000` (→ 485-window/0.434), but the headline is `--limit 12000` (→ 1,883-window/0.278). A fresh run silently reproduces the weaker-looking 0.434.
**Fix.** Either change the script default to `--limit 12000` or print a banner when the default is used: `"NOTE: --limit 12000 --seed 0 reproduces the reported 1,883-window headline (bal-acc 0.278)."` In all docs, quote **0.278 (n=1,883)** as the EEG headline and footnote the 485-window run as small-sample.
**Done when** the reproduce command in VALIDATION.md and the script default agree, and 0.434 never appears as a headline.

### 8. Make the Echo EF headline the 400-video number
**Problem.** Some docs headline MAE 3.19 % / R² 0.860 (40 videos); the honest number is **4.01 % / 0.831 (400 videos)**.
**Fix.** Replace every Echo EF headline with **MAE 4.01 %, R² 0.831 (400 videos)**; demote 3.19 %/40-video to a transparency footnote; state the full TEST split is 1,277 videos (so even 400 is a subset).
**Done when** no doc headlines the 40-video figure.

### 9. Add an in-UI medical disclaimer
**Problem.** "Not for clinical use" appears only in PDF/backend text, never in the React app.
**Fix.** Add a persistent banner in the app shell (`App.jsx`/`DashboardLayout`) and a one-liner on each result view:
```jsx
<div className="text-xs text-amber-800 bg-amber-50 border-t border-amber-200 px-4 py-1.5 text-center">
  {t('common.disclaimer')} {/* "Decision-support only — not a diagnosis. Verify with a qualified physician." */}
</div>
```
Add `common.disclaimer` to the EN + FR `common` namespace (keep key-tree parity).
**Done when** the disclaimer is visible on every authenticated page and both languages.

### 10. Make CI run real tests on a clean clone
**Problem.** CI is only `check` + `compileall`; a NameError in a view or a broken pipeline passes green. `APITestCase` can't run because djongo refuses the test DB.
**Fix.** The settings already swap to in-memory SQLite when `'test' in sys.argv` — leverage it. In `.github/workflows/ci.yml`, add a backend job step:
```yaml
- run: |
    cd backend
    pip install -r requirements-core.txt
    python manage.py test apps tests.test_pipelines --noinput
```
(Run the API/isolation tests under SQLite; keep the heavy inference tests local, or gate them behind a label since they pull ~700 MB.)
**Done when** the doctor-isolation test (#3) and the auth/permission tests execute in CI on a fresh runner.

---

## 🟠 SHOULD-DO

### 11. Run the external ECG leakage check (single best experiment)
**Problem.** ecglib may have trained on PTB-XL, so the ~0.98 AUC could be optimistic — and the check is documented but never run.
**Fix.** `python tools/eval_ecg_external.py` on Chapman-Shaoxing-Ningbo (procedure in `tools/EXTERNAL_ECG_EVAL.md`); paste the macro-AUC into VALIDATION.md. Decision rule already stated: AUC ≈ 0.95+ ⇒ vindicated; a drop ⇒ optimism honestly quantified.
**Done when** VALIDATION.md shows a real external macro-AUC instead of the `X.XXX` placeholder.

### 12. Add confidence intervals + a significance test
**Problem.** Every metric is a single-split point estimate; no variance. The EEG "above chance" claim has no test.
**Fix.** Bootstrap (1,000 resamples) 95 % CIs for the headline metrics (MRI acc, ECG macro-F1/recall, Echo MAE, EEG balanced-acc) from the cached prediction files (`mri_preds.json`, `ecg_scores_finetuned.json`, `echo_ef_pairs.json`). For EEG, a permutation test of balanced-acc vs the 0.167 chance line. Report as `0.278 [0.25, 0.31]`.
**Done when** every headline number carries a 95 % CI and the EEG above-chance claim has a p-value.

### 13. Run the EEG GPU full fine-tune (lift the 0.278 ceiling)
**Problem.** The IIIC head is frozen-encoder-limited at balanced-acc 0.278.
**Fix.** Run `Colab PFE/colab_eeg_full_finetune.ipynb` (unfreeze the encoder, GPU). Honest target 0.45–0.55. Re-verify locally with `tools/eval_eeg.py --limit 12000`. If no GPU is available, state explicitly that this is the one experiment the hardware blocked — that's a defensible position, not a gap.
**Done when** either a GPU-fine-tuned `biot_iiic.pt` lifts balanced-acc toward ~0.5, or the limitation is explicitly hardware-scoped.

### 14. Add frontend tests (Vitest)
**Problem.** No test runner; the auth slice, 401 interceptor, and dropzone validation are unverified.
**Fix.** Add Vitest + React Testing Library:
```bash
npm i -D vitest @testing-library/react @testing-library/jest-dom jsdom
```
Test: `authSlice` reducers; the Axios 401 → `/login` interceptor; `MRIUpload` mode auto-detection (grayscale → `classify`, color → `segment`); dropzone rejection of a `.txt` file.
**Done when** `npm test` runs a green suite covering auth, the interceptor, and MRI mode detection.

### 15. Close the ML silent-failure paths
**Problem.** Several pipelines return `status:success` with a wrong answer (positional ECG leads, <12-lead broadcast, already-bipolar EEG, non-FLAIR MRI).
**Fix (smallest, highest-value first).**
- ECG: map leads by **header label**; if labels are missing/ambiguous, set `quality.warnings += ["positional lead order — unverified"]` (already partly there) and surface it in the result view.
- ECG: reject `< 12` leads instead of broadcasting lead I (return a `failed` envelope with a clear message).
- EEG: the preprocessor already refuses already-bipolar EDFs — make sure that ValueError becomes a clean `failed` envelope, not a 500.
- MRI: surface the existing `segmentation_note` (FLAIR caveat) in the result UI.
**Done when** each unsupported input yields a clear warning or a structured `failed`, never a confident wrong success.

### 16. Implement token refresh + revocation
**Problem.** 7-day refresh, no blacklist, no logout; the frontend refresh flow is unimplemented (every 401 hard-redirects).
**Fix.** Add `rest_framework_simplejwt.token_blacklist` to `INSTALLED_APPS`, enable `ROTATE_REFRESH_TOKENS` + `BLACKLIST_AFTER_ROTATION`, add a `/api/auth/logout/` that blacklists the refresh token. Frontend: on 401, attempt a silent `/refresh` once before redirecting to `/login`.
**Done when** an expired access token is transparently refreshed, and logout invalidates the refresh token server-side.

### 17. Shared cache + production security settings
**Problem.** Per-process `LocMemCache` makes the throttle per-worker; no SSL/HSTS/secure-cookie settings.
**Fix.** Add a shared `CACHES` backend (Redis or the DB) so throttle state is global. Add `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_PROXY_SSL_HEADER`, `SECURE_CONTENT_TYPE_NOSNIFF` behind a `DEBUG=False` guard.
**Done when** `python manage.py check --deploy` reports no critical warnings and the throttle holds across workers.

### 18. Validate MRI end-to-end on one common dataset
**Problem.** U-Net (LGG) and the classifier (Kaggle) are validated on different datasets; no single image is validated through both.
**Fix.** Pick a small set with both masks and type labels (or accept the limitation explicitly). Report the deployed crop-then-classify accuracy, which is currently unmeasured.
**Done when** there's a number for the deployed two-stage path, or the limitation is explicitly scoped in the thesis.

### 19. Add LICENSE, THIRD_PARTY, and model cards
**Problem.** README claims MIT with a literal "TODO"; no per-model licence notes.
**Fix.** Add a real `LICENSE` (MIT), a `THIRD_PARTY.md` listing each model + dataset + licence (ViT/Swin, U-Net, ecglib, EchoNet, BIOT, PTB-XL, LGG, EchoNet-Dynamic, HMS), and a one-line `MODEL_CARD.md` in each `models_weights/*` dir.
**Done when** every bundled model and dataset has an attributed licence.

---

## 🟢 NICE-TO-HAVE (optional)

| # | Problem | Fix |
|---|---|---|
| 20 | No API docs | Add `drf-spectacular`; expose `/api/schema/` + `/api/docs/`. |
| 21 | No health endpoint | Add `/health/` that pings Mongo and reports which model weights are present. |
| 22 | No structured logging | Add a `LOGGING` dict (JSON formatter); optional Sentry DSN from env. |
| 23 | `/history/` omits echo & eeg | Add the echo/eeg reverse relations to the aggregate endpoint and serializer. |
| 24 | Dead UI / UX gaps | Wire or remove the notifications bell; toast dropzone rejections; show a failure banner on failed MRI/ECG (mirror `EEGResult`); add echo/eeg to the dashboard feed; load the `fr` date-fns locale. |
| 25 | Stray files / dead deps | Delete `ecg_finetuned/drive-download-*.zip`; remove unused `celery`/`redis` pins or move to `requirements-future.txt`. |
| 26 | Patient consent / audit trail | Add a consent flag + minimal `AuditLog`, or soften the "GDPR-inspired" README claim. |
| 27 | Accessibility | Add `role="dialog"`, `aria-modal`, Escape-to-close, and focus-trap to modals. |
| 28 | Node version doc | README says Node ≥18; Vite 8/React 19 need ≥20.19 — fix the doc and add `engines` to `package.json`. |
| 29 | djongo / Django 3.2 lock-in (large) | Plan a migration off djongo (Postgres or MongoEngine) to unlock Django 4.x + Python 3.12. |
| 30 | Synchronous inference (large) | Add Celery/RQ + a job-status endpoint + a progress UI if scaling past a demo. |

---

*Priority rationale: 🔴 items cost marks or break the demo / contradict your own contracts; 🟠 items raise the work to a clear master's level (real external validation, variance, tests); 🟢 items are polish. The MRI two-model routing requested is already done (§0).*
