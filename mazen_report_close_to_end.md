# Mazen — Project Review, Close to the End

**A-to-Z audit of the multimodal medical AI platform (PFE, Université Constantine 2)**
Date: 2026-06-12 · Scope: backend, ML pipelines, frontend, validation honesty, docs, tests, devops, and forgotten gaps.

---

## How this report was produced (read this first)

This is the output of a 10-dimension parallel audit. Nine dimensions completed; each high/critical
finding was sent to a separate agent that re-opened the actual files and tried to **refute** it, so the
list below is filtered for reality, not just plausibility. I then **personally re-verified** the three
highest-impact findings whose verifier was interrupted.

**Honest caveats about coverage:**
- The dedicated **thesis-defence** reviewer and **three verifier** agents hit a session/quota limit and did
  not finish. So: the "Thesis-defence readiness" section below is my synthesis from the other dimensions
  (not an independent deep pass), and three findings carry a "verifier interrupted" note — but I confirmed
  all three by hand (registration role flaw, the media-auth leak via a second dimension, and the Echo-EF
  numbers, which I recomputed myself).
- This audits the **code and docs as they exist today**. It does not re-run the full model evaluations.

**Verdict in one paragraph:** This is a strong, unusually honest PFE. The architecture is clean, doctor
isolation is correctly enforced on every JSON endpoint, the deliberate engineering decisions in `CLAUDE.md`
are sound and faithfully implemented, EN/FR i18n parity is perfect, and most accuracy numbers reproduce
exactly from committed artifacts. The problems that matter are **not** in the ML — they are in (1) one real
**patient-data exposure** path, (2) a handful of **"confidently wrong" silent-failure** paths in the
pipelines, (3) **two accuracy claims** a sharp jury could attack, (4) **reproducibility traps** that would
make a fresh clone silently run *weaker* models than your headline numbers, and (5) **missing governance
artifacts** (LICENSE, in-UI medical disclaimer, consent/audit) that a medical-AI jury notices by their
absence. None of these invalidate the work; all are fixable before submission.

---

## Severity dashboard

| Area | Critical | High | Medium | Low |
|---|---|---|---|---|
| Security & auth | 1 | 1 | 3 | 2 |
| Doctor isolation / API contracts | – | 1* | – | 2 |
| ML pipeline correctness | – | 1 | 6 | 3 |
| Frontend quality / UX | – | 3 | 2 | 7 |
| ML validation honesty | – | 1 | 3 | 2 |
| Documentation consistency | – | 3 | 4 | 4 |
| Testing & CI | 1 | 3 | 3 | 4 |
| Reproducibility / config | – | 2 | 2 | 5 |
| Forgotten / missing | – | 3 | 4 | 3 |

\* The doctor-isolation "high" is the **same** unauthenticated-media issue as the security "critical",
found independently by two dimensions — that cross-corroboration is why I rank it #1.

---

## DO THIS BEFORE YOU SUBMIT / DEFEND — priority order

These are the items that change either patient-safety posture, the defensibility of your numbers, or what a
jury will visibly catch. Effort is a rough estimate.

| # | Fix | Why it matters | Effort |
|---|---|---|---|
| 1 | **Stop serving `/media/` without auth** (route PHI through a doctor-scoped view, or nginx `auth_request`/`X-Accel-Redirect`) | Any unauthenticated party who guesses a `/media/...pdf` URL can read another doctor's scans & reports — directly breaks your own #1 contract | M |
| 2 | **Make `role` read-only in registration** | One `curl` self-registers as `role=admin` today (confirmed in code) | XS |
| 3 | **Fix the Echo EF headline** — quote MAE 4.0% / R² 0.83 (400 videos), not 3.19% (40 videos) | The repo's own artifact contradicts the headline; I reproduced both numbers | XS–S |
| 4 | **Add doctor-isolation API tests** (two-doctor cross-access → 404/empty) | Your documented #1 security invariant has **zero** tests | M |
| 5 | **Make headline weights reproducible** (host/download the fine-tuned ViT + ECG; stop calling the BIOT encoder "bundled" when it's git-ignored; log a WARNING on stock-weight fallback) | A fresh clone silently runs the *weaker* stock ViT (80.4%) while your report claims 95.4% | M |
| 6 | **Fix the doc contradictions a jury will read** — "ViT-B/16"→"Swin-T" (config.json proves Swin), "5/7" vs "all 7", the superseded EEG brief, React 18→19, the "open U-Net bug" framing in the report outline | These undercut your own "everything is verified, code wins" claim | S |
| 7 | **Flag "confidently wrong" ML inputs** — wrong ECG lead order, <12-lead broadcast, already-bipolar EEG, non-FLAIR MRI | Today these return a normal-looking `status:success` with a wrong answer | M |
| 8 | **Add a LICENSE file + an in-UI medical disclaimer (EN/FR)** | README claims MIT with a literal "TODO"; the UI has no "not for clinical use" notice anywhere | XS |

---

## 1. Security & patient-data protection

### 🔴 CRITICAL — Patient media (scans + PDF reports) served with no authentication
*`backend/core/urls.py:17-18`, `maybe read/DEPLOYMENT.md:152` — found by two dimensions; verifier confirmed `isReal=true`, rated high.*

Doctor isolation is enforced on every DRF JSON endpoint, but the **binary files those endpoints point to**
are not protected. In DEBUG, `static()` serves all of `MEDIA_ROOT` with no permission check; the documented
production config serves the same tree via a bare `nginx location /media/ { alias …; }`. Filenames are
**predictable** — report PDFs are `{patient_pk}_{YYYYMMDD_HHMMSS}.pdf` (`reports/views.py:116`), uploads keep
their original name. So anyone who learns or guesses a path downloads another doctor's MRI/echo/EEG files and
full reports. The authenticated `ReportDownloadView` is bypassed because the API itself hands back raw
`/media/` URLs (`file_url`, `overlay_url`, `plot_url`).

> **Honest nuance:** on localhost dev this is low *real* risk (only you can reach it). The real exposure is
> the **production nginx recipe you documented**. Either way it contradicts your "doctor isolation is a hard
> contract" claim, so fix it and mention it in Known Limitations until you do.

**Fix:** Serve every modality's files through an authenticated, doctor-scoped Django view (the
`ReportDownloadView` pattern you already have), or use nginx `auth_request` → Django permission check. Use
UUID filenames as defense-in-depth, but that's not a substitute for the access check.

### 🟠 HIGH — Registration mass-assigns `role` → self-elevation to admin
*`backend/apps/authentication/serializers.py:28` — I confirmed this by hand.*

`UserRegistrationSerializer` lists `role` in writable `fields` with only a `default` (not read-only), and
`create()` passes `validated_data` straight to `create_user`. `RegisterView` is `AllowAny`. So
`POST /api/auth/register/ {email, password, full_name, role:"admin"}` creates an admin. Blast radius is small
*today* (no endpoint gates on `role` yet) but the role is baked into the JWT and surfaced to the frontend, so
any future admin gate is instantly exploitable. **Fix:** drop `role` from the writable fields and force
`role=DOCTOR` server-side.

### 🟡 MEDIUM — three production-hardening gaps
- **No `CACHES` backend** → the DRF throttle uses per-process `LocMemCache`; under the documented 2-worker
  gunicorn, your login limit becomes 10/min *per worker* and resets on reload. Add Redis/Memcached as the
  default cache. (`settings.py`, no CACHES block.)
- **No production security settings** — no `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SESSION/CSRF_COOKIE_SECURE`,
  `SECURE_PROXY_SSL_HEADER`, `SECURE_CONTENT_TYPE_NOSNIFF`. `manage.py check --deploy` would flag all of these;
  DEPLOYMENT.md even admits media URLs come back as `http://` behind TLS. Add a `not DEBUG` block.
- **No token revocation / logout** — 7-day refresh, `ROTATE`/`BLACKLIST` off, no `token_blacklist` app, no
  logout endpoint. A stolen refresh token is valid for a full week. Enable blacklisting + a logout endpoint.

### 🟢 LOW
- Inference endpoints are **unthrottled** and run heavy synchronous CPU work on files up to 500 MB → a DoS
  surface; add a modest per-user throttle on uploads.
- The working `backend/.env` contains a recognizable `django-insecure-…` placeholder key — **correctly
  git-ignored** (no leak), but add a startup guard that refuses `DEBUG=False` with an insecure key.

---

## 2. Doctor isolation & API contracts

The core is **correct**: every list/retrieve/destroy queryset filters by `patient__doctor=request.user`, and
uploads resolve `get_object_or_404(Patient, …, doctor=request.user)`. No IDOR in the JSON layer. Two minor
issues:

- 🟢 **`/history/` silently omits echo & eeg** (`patients/views.py:23-37`) — returns only `mri_analyses` and
  `ecg_analyses`, but README documents four modalities and the reverse relations exist. Add them (or iterate a
  modality registry).
- 🟢 **The envelope guarantee isn't enforced at the call site** (`inference/__init__.py:37-49`) —
  `run_inference_with_timeout` catches only `TimeoutError`; any other exception escaping a pipeline would 500.
  It holds today only because each `analyze_*` wraps its whole body in `try/except`. Wrap `future.result()` in
  a catch-all that returns `{status:'failed', error, error_type}` so the contract is enforced centrally.

---

## 3. ML pipeline correctness — the "confidently wrong" risks

The deliberate choices (no second sigmoid, recall-first thresholds, weights-not-bundled, structured envelope)
are sound and correctly implemented. The real risks are **silent wrong answers** — none crash, all return a
normal-looking `status:success`:

| Sev | Issue | Location | What happens |
|---|---|---|---|
| 🟠 HIGH | **Lazy loaders aren't thread-safe** (verifier downgraded to MEDIUM) | `model_loader.py` getters | Only `__new__` is locked; per-model getters do unguarded check-then-set. Two concurrent first requests can each load a model (double memory / torn state). Guard each getter or pre-load in `warmup()`. |
| 🟡 MED | **ECG lead order is positional** | `utils.py:69-129` | Leads are consumed by column/header position, never mapped to canonical I,II,III,aVR…V6. Wrong source order → silently wrong prediction. Parse labels and reorder. |
| 🟡 MED | **<12-lead ECG broadcast** | `utils.py:110-113` | `np.tile(sig[:1],(12,1))` replicates **lead I** into all 12 channels and runs full inference → confident garbage. Refuse or flag "reduced lead set". |
| 🟡 MED | **EEG montage assumption** | `eeg_preprocess.py:65-117` | An already-bipolar EDF (e.g. `FP1-F7`) gets re-referenced into nonsense. Detect montage type or raise a structured error. |
| 🟡 MED | **MRI U-Net fed 3 identical channels** | `mri_pipeline.py:181-192`, `utils.py:32-62` | The U-Net was trained on 3 *different* sequences (T1/FLAIR/T1c); it receives one grayscale image broadcast ×3. Document that validity is tied to FLAIR-like inputs. |
| 🟡 MED | **EEG train/inference window mismatch** | `eeg_preprocess.py:149-174` | Training/eval score ONE central 10s window; deployment scores **all** non-overlapping windows. The endpoint's off-center per-window labels are unvalidated. Evaluate the deployed path or document the gap. |
| 🟡 MED | **700 MB first-call download blocks the request** inside a 300s timeout | `model_loader.py`, `mri/views.py:107` | Cold start can hit the timeout and look like an inference failure. Call `warmup()` at startup; distinguish "downloading" from "timeout". |
| 🟢 LOW | `central_segment` clamp can silently slide to the wrong 10s window | `eeg_preprocess.py:149-158` | Log/skip instead of relocating. |
| 🟢 LOW | MRI inline comment says "Dice ~0.9" but measured is 0.85; `seg_conf` semantics ambiguous | `mri_pipeline.py:204` | Align comment to 0.85. |
| 🟢 LOW | Echo EF clip sampling can degenerate to a single clip; EF clamp masks regressor failure | `echo_pipeline.py:102-120` | Average over clips even for short videos; flag non-physiological EF instead of clamping. |

---

## 4. ML validation — honesty issues a jury can attack

Your validation is, by student-project standards, **unusually honest and reproducible** — I recomputed the
ECG (macro F1 0.727) and MRI (95.4%) headlines from the committed artifacts and they matched exactly. But:

### 🟠 HIGH — The Echo EF headline is a 40-video cherry-pick *(verifier interrupted — I reproduced this myself)*
`VALIDATION.md:334` headlines **MAE 3.19% / R² 0.860**, measured on **40 videos** (`VALIDATION.md:327-328`).
The repo's own committed `tools/echo_ef_pairs.json` contains **400** true/pred pairs. I recomputed:

| Sample | MAE | RMSE | R² |
|---|---|---|---|
| First 40 (headlined) | 3.19% | — | 0.86 |
| **All 400 (in repo)** | **4.01%** | **5.30%** | **0.83** |

The smaller, better-looking number is headlined; the larger, more reliable one is never quoted as *the* EF
result. (To your credit, `VALIDATION.md:518` does note "rerun without `--limit` for the full figure" — but the
headline should be the 400-video number, or the full 1,277-video TEST split.) **Fix:** re-headline with the
400-video numbers and keep 40 only if explicitly labelled "preliminary subset".

### 🟡 MEDIUM
- **No confidence intervals / variance anywhere** — every figure (ECG, MRI, Echo, EEG) is a single-split point
  estimate. Add bootstrap 95% CIs to the headline metrics (cheap — resample saved scores, no re-inference) and
  a permutation test for the EEG "above chance" claim.
- **"macro F1 0.727" vs "0.596" in the metrics JSON** — both are arithmetically correct but use *different
  threshold objectives* (F1-tuned vs balanced-accuracy-tuned). Label each explicitly so it doesn't read as
  "which number is real?".
- **EEG reproduce command is inconsistent** — VALIDATION headlines a 6,814/1,883 split with `--limit 12000`,
  but `eval_eeg.py`/`train_eeg_head.py` default `--limit 4000`. State the exact `--limit`/`--seed` (or commit
  the window index) so the headline split actually reproduces.

### 🟢 LOW
- The 3/7 ECG fine-tune trains on PTB-XL folds 1–8 while PTB-XL is *also* your leakage concern — partial
  circularity. **Run `tools/eval_ecg_external.py` on Chapman-Shaoxing-Ningbo before the defence** to convert
  the leakage caveat from a hand-wave into a measured result. (This is your single best pre-defence experiment.)
- The headline table juxtaposes LGG-segmentation Dice and Kaggle-ViT accuracy as one "MRI result" — two
  different datasets/tasks. Tag each row with its dataset.

---

## 5. Documentation contradictions

Your docs are extensive and cross-referenced, but they contradict each other in places a jury reads. The
"code wins, everything verified" posture makes each contradiction more damaging than it would otherwise be.

| Sev | Contradiction | Fix |
|---|---|---|
| 🟠 HIGH | Docs call the MRI classifier **"ViT-B/16"**, but `config.json` says **`SwinForImageClassification`** (Swin-T) — the code/weights are Swin; the docs were wrong (this audit row had the direction backwards) | RESOLVED June 2026: all docs corrected to **Swin Transformer (Swin-T, Liu et al. 2021)**, ~28 M params, base `microsoft/swin-tiny-patch4-window7-224` |
| 🟠 HIGH | Stale **"ECG degrades to 5/7"** narrative in TESTING/CHANGELOG/METHODOLOGY/HOW-IT-WORKS/PROJECT_FUNCTIONALITY while README/VALIDATION/code say **all 7 load** (one doc even lists the wrong 5-set) | Separate "all 7 load at startup" from "envelope *can report* a runtime partial"; fix the wrong set |
| 🟠 HIGH | `docs/EEG-MODALITY-BRIEF.md` describes a **different model** (TUEV: SPSW/PLED/GPED…, "pretrained, no training") than what you built (IIIC: SZ/LPD/GPD…, fine-tuned head) | Add a "SUPERSEDED — see EEG-IIIC-MODALITY-BRIEF.md" banner or archive it. **You have this file open right now.** |
| 🟡 MED | README stack table says **React 18**; project is React 19 | Fix the table |
| 🟡 MED | `PFE_REPORT_OUTLINE.md` still treats the U-Net saturation as an **open bug** + lists the already-applied fix as Future Work | Reframe as a diagnosed-and-fixed contribution (double-sigmoid) |
| 🟡 MED | `CHANGELOG.md:127-137` & `TESTING.md:199` still list the U-Net preprocessing/saturation as a **known limitation** | Scope as "state at 1.0.0 (since fixed)" or correct |
| 🟢 LOW | `seed_database.py` path differs between docs (`backend/tests/…` vs `tests/…`) → real "file not found" | Make cwd explicit everywhere |
| 🟢 LOW | CONTRIBUTING says test DB auto-creates & ~600 MB; other docs say djongo refuses it & ~700 MB | Align |
| 🟢 LOW | Echo EF clinical thresholds stated with different cut-points across 3 docs | One canonical EF table, referenced everywhere |
| 🟢 LOW | CHANGELOG describes the PDF as MRI+ECG-only; it now does 4 modalities | Soften the historical wording |

---

## 6. Testing & CI — thin and structurally fragile

This is the weakest engineering area, and it's the one most at odds with a "medical platform" framing.

### 🔴 CRITICAL — Doctor isolation has **zero** tests
*verifier confirmed.* Your documented #1 security invariant ("an endpoint returning another doctor's data is a
bug") is enforced in code but **never tested**. Add APITestCase tests with two doctors: B requesting A's
patient/mri/ecg/echo/eeg/report → 404 or empty; B uploading with A's `patient_id` → 404.

### 🟠 HIGH
- **The only HTTP/auth/permission tests can't run on a fresh checkout** — `APITestCase` needs the test DB,
  which djongo "refuses to create" (your own docs). No sqlite test fallback. So on a clean clone the entire
  auth/permission/validation test layer typically doesn't run. **Fix:** detect `'test' in sys.argv` in
  `settings.py` and switch `DATABASES['default']` to in-memory sqlite for tests.
- **CI runs no behavioural tests** — only `manage.py check` + `compileall`, which never *imports* or *executes*
  code. A `NameError` in a view, a wrong serializer shape, or a broken pipeline passes CI green. With the
  sqlite override, add a `manage.py test tests.test_pipelines.APITest` step on `requirements-core.txt`.
- **Frontend has no test runner at all** — the 401 interceptor, JWT attach, Redux slices, and dropzone logic
  are entirely unverified. Add Vitest + Testing Library; start with the auth slice and the 401 interceptor.

### 🟡 MEDIUM / 🟢 LOW
- Upload extension/size **rejection** is implemented but never tested (tests only post valid files).
- **echo & eeg apps have no `tests.py` at all.**
- The reports test checks only 400 paths — never generates an actual PDF (so `_ascii()` is untested).
- Auth throttle (429) untested; serializers & `/history/` untested; inference smoke tests are shape-only and
  `@skipUnless(sample exists)` so a "green" run can mean **zero** inference assertions ran.
- `test_apis.sh` defaults (`doctor@test.local` / `SecurePass123!`) **don't match** the seed user
  (`doctor@test.com` / `TestPass123!`) → the smoke test fails out of the box.

---

## 7. Reproducibility & config — the "fresh clone runs the wrong models" trap

Secrets hygiene is good (no `.env`, no real weights tracked) and docker-compose is honestly flagged untested.
But:

### 🟠 HIGH
- **The BIOT encoder is documented as "bundled" but is git-ignored and untracked** (`.gitignore:220`
  `backend/models_weights/*`). CLAUDE.md, README, and the loader docstring all say "bundled"; it isn't. EEG
  can't run on a fresh clone even after training the head. **Fix:** either commit it via a `.gitignore`
  negation (it's 13.8 MB, MIT) or stop calling it "bundled" and document a download.
- **The fine-tuned ViT (95.4%) and ECG (0.727) weights — which back your headline numbers — are git-ignored
  with no download path, and the loaders silently fall back to the weaker stock models** (ViT 80.4%). A
  reproducer unknowingly measures *different, worse* models than your report claims. **Fix:** host the weights
  + document retrieval, and at minimum log a loud WARNING on stock fallback.

### 🟡 MEDIUM / 🟢 LOW
- **Your CI workflow won't run on GitHub** — the actual git root is `E:/MASTER`, one level above
  `medical-platform/`. `git init` at `medical-platform/` (or move `.github/`) before claiming CI.
- docker-compose bind-mount `./backend:/app` shadows the image's installed deps → documented `docker compose up`
  can't work as-is (already flagged untested — keep it honest).
- A stray **63 MB `drive-download-…zip`** sits under `ecg_finetuned/` (git-ignored, so harmless to git, but
  delete it after extracting).
- README says Node ≥18; Vite 8 / React 19 need Node ≥20.19. Bump it and add `engines` to package.json.
- Python 3.10/3.11 and port-3000 constraints are documented but **not enforced** — add a `sys.version_info`
  guard in `manage.py` (djongo silently breaking on 3.12 is your single most likely "doesn't run" support
  ticket).
- `requirements*.txt` pin **celery + redis** but there's no async layer and no import of either — dead deps;
  remove or move to a clearly-labelled `requirements-future.txt`.

---

## 8. Frontend quality & UX

Genuinely well-built: **EN/FR key-tree parity is perfect across all 11 namespaces** (verified
programmatically), the theme system is coherent, and the upload UX is sensible. Real flaws:

### 🟠 HIGH (all verified; verifiers downgraded the impact to MEDIUM/LOW)
- **The advertised JWT refresh flow is entirely unimplemented** (`services/api.js:17-34`) — refresh tokens are
  stored but never used; every 401 hard-redirects to `/login`. So sessions silently die at the 1-hour access-
  token expiry, mid-work. Implement a refresh-on-401 interceptor (retry once, queue concurrent 401s).
- **No client-side file-size validation** despite prominently advertised limits — no `maxSize` on any
  dropzone. A user can drop a 1 GB file and wait minutes for a server rejection.
- **No timeout-aware UX** — axios hard-caps every request at 5 min; if inference exceeds it (cold cache + CPU +
  big EDF), axios aborts while the backend keeps working, showing only a raw error. Detect `ECONNABORTED` and
  show a translated "still processing — refresh the patient page" message; or move inference off the request
  path.

### 🟡 MEDIUM / 🟢 LOW
- Dropzone **rejections are silently swallowed** (wrong type → nothing happens, no toast).
- **Modals lack accessibility** — no `role="dialog"`, `aria-modal`, Escape-to-close, or focus trap.
- The **notifications slice + Navbar bell are dead UI** (never dispatched, no handler) — wire or remove.
- **Dates never localized to French** (date-fns with no `fr` locale) — acknowledged in your conventions, but
  worth closing.
- **Failed-status MRI/ECG results render empty panels** (0% bars, "—") instead of a failure banner — mirror
  `EEGResult`.
- **Dashboard "Recent activity" only shows MRI & ECG** — echo/eeg/reports are fetched for counts but dropped
  from the feed.
- Untranslated server strings + lowercase `role` surface raw in FR; **login password min (6) ≠ register min
  (8)**; result pages don't re-poll a stuck `processing` record.

---

## 9. Forgotten / missing — what a medical-AI jury notices by absence

Hygiene is better than typical (per-modality size limits, BIOT LICENSE preserved, models cited, AI
disclaimers *in the PDF*, a `cleanup_media` command). The gaps:

### 🟠 HIGH
- **No top-level LICENSE file** — README says MIT with a literal "TODO: add formal LICENSE". Add MIT + a
  `THIRD_PARTY.md` enumerating each model's license (BIOT MIT, EchoNet, ecglib, ViT, datasets).
- **No in-UI medical disclaimer** — disclaimers exist only in the PDF/backend text; a grep of `frontend/src`
  for "disclaimer / clinical use / not a diagnosis" returns nothing. Add a persistent EN/FR banner in the app
  shell + every result page. *This is one sentence of code and directly addresses an obvious jury question.*
- **No patient-consent capture or access audit trail** despite a "GDPR-inspired" README claim — the Patient
  model stores PII (name, age, gender, free-text history) with no consent flag, no retention/expiry, no audit
  log. Either implement a minimal consent flag + AuditLog, **or soften the README to say honestly that no GDPR
  controls are implemented** (the cheaper, defensible option for a prototype).

### 🟡 MEDIUM
- No async queue for synchronous 5–60s+ inference (UX/availability risk — at least document the deployment
  timeout implication).
- No **API docs** (drf-spectacular → `/api/docs/` is near-free and gives the jury an authoritative surface).
- No **health/readiness endpoint** (`/health/` pinging Mongo + reporting weight presence).
- No **structured logging** config and no error monitoring (add a `LOGGING` dict; optional Sentry behind an
  env var).

### 🟢 LOW
- No model cards / dataset-license notes beside the weights (`MODEL_CARD.md` per dir).
- `cleanup_media` exists but is unscheduled & DB-blind; no backup script (document a scheduled run + a
  `mongodump` restore note).
- Thin accessibility (only ~29 aria/role/alt across 20 files) — quick polish pass.

---

## 10. Thesis-defence readiness *(my synthesis — the dedicated reviewer agent was interrupted)*

Treat this as a checklist of what a Constantine 2 jury is most likely to probe, derived from the findings
above rather than an independent deep pass:

1. **"Are your numbers trustworthy?"** — Your strongest and weakest area. Strong: most numbers reproduce from
   committed artifacts and you disclose leakage/ceiling caveats. Weak points they'll find: the Echo-EF 40-video
   cherry-pick (#3), no confidence intervals (everything is one split), and the PTB-XL train/test circularity.
   **Pre-empt all three:** fix the EF headline, add bootstrap CIs, and run the external ECG eval.
2. **"Is it safe with patient data?"** — Have an answer ready for the unauthenticated `/media/` path and the
   absence of consent/audit. Best move: fix the media auth, and frame the data-governance gap honestly as
   "prototype scope" in both the report and `Problems of My Project.md`.
3. **"What did *you* build vs. download?"** — Be crisp: you fine-tuned the ViT (80.4→95.4%) and 3 ECG heads,
   trained the EEG IIIC head (frozen encoder, ~chance ceiling — already honest), and engineered the pipelines/
   fusion. The "Swin vs ViT" doc slip (#6) will make a careful jury doubt you know your own model — fix it.
4. **"Does it run?"** — The reproducibility traps (#5) mean a jury cloning your repo gets weaker models or a
   non-starting EEG path. Make a fresh clone reproduce the headline numbers, or document the weight-download
   path precisely.
5. **Keep `My Project – The End.md` and `Problems of My Project.md` in sync** (your CLAUDE.md already mandates
   this) — and add the items above to the honest-limitations doc *before* the jury finds them. A limitation you
   disclose is a strength; one they discover is a wound.

---

## What you got RIGHT (don't "fix" these)

So you know where the floor is — and what *not* to touch:

- **The deliberate decisions in CLAUDE.md are correct and faithfully implemented** — the no-second-sigmoid U-Net
  fix, recall-first screening thresholds, the structured `{status,…}` envelope, weights-not-bundled `FileNotFoundError`
  paths, and `_ascii()` in the PDF generator. Auditors confirmed these are sound, not bugs.
- **Doctor isolation is correctly enforced on every JSON queryset** — no IDOR in the API layer.
- **EN/FR i18n key-tree parity is perfect** across all 11 namespaces (verified programmatically).
- **Your validation is unusually honest** — leakage, the LGG-vs-Kaggle split, the EEG frozen-encoder ceiling,
  and the rule-based (non-learned) fusion are all disclosed. Most headline numbers reproduce exactly from
  committed artifacts.
- Secrets hygiene, vendored-license preservation, model/dataset citations, and the careful `cleanup_media`
  command are all above the bar for a Master's PFE.

---

## Appendix — coverage & confidence

- **Verified by an independent refutation agent:** media-auth (×2 dimensions), thread-safety, refresh-token,
  client file-size, timeout UX, doctor-isolation-tests gap, APITestCase/CI gaps, frontend-no-tests, Swin/ViT,
  5/7-vs-all-7, superseded EEG brief, BIOT "bundled", fine-tuned-weights-ignored, LICENSE, in-UI disclaimer,
  consent/audit.
- **Verified by me directly (their agent was interrupted):** registration `role` flaw (read the serializer),
  Echo-EF cherry-pick (recomputed: 400 pairs → MAE 4.01% vs first-40 → 3.19%), media-auth (cross-corroborated).
- **Not independently audited:** the dedicated thesis-defence pass (interrupted) — section 10 is my synthesis.
- Severities shown reflect the verifier's *adjusted* rating where it downgraded an initial call (several
  frontend "high"s were judged medium/low on impact — kept in the High section by their reviewer's original
  framing but flagged honestly).

*Total: ~79 findings across 9 dimensions (2 critical, ~17 high, 27 medium, 32 low), de-duplicated where two
dimensions found the same issue.*
