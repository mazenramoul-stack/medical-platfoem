# Implement the Technician role + multi-modal data-conversion tool

You are working in an existing monorepo: a multimodal medical-AI platform (Master's PFE). Implement the complete feature described below, end to end, following the repo's existing conventions. Work autonomously and verify as you go — do not stop to ask unless you hit a genuine blocker or an ambiguity that materially changes the design.

## Before you write any code

1. Read `CLAUDE.md` (repo root) in full — it documents architecture, hard version constraints, the two backend contracts (doctor isolation + pipeline result envelope), the test-runner behavior, and many "looks like a bug but isn't" notes. Treat it as authoritative.
2. Read `frontend/THEME-I18N-CONVENTIONS.md` — you MUST follow it for every component/locale you touch (CSS-variable theming, light/dark, EN/FR key-tree parity).
3. Skim `maybe read/CONTRIBUTING.md` (the "adding a new modality" recipe) for the house style.
4. If `superpowers` skills are available, use `test-driven-development` and `verification-before-completion`. Always verify with the commands in the "Verification" section before claiming anything works.

## Hard constraints (do not violate)

- **Python 3.10/3.11**, **Django 3.2.25 LTS**, **djongo** over MongoDB. Do not upgrade these. djongo is schemaless, so `AddField`-style migrations are effectively no-ops at the DB layer but must still be created/recorded.
- The test runner auto-swaps `DATABASES['default']` to in-memory SQLite when `'test' in sys.argv` (see `backend/core/settings.py`), so `APITestCase` DB tests run on a fresh checkout.
- Backend apps live under `backend/apps/` and are registered as `apps.<name>` (the dotted prefix — `apps.py` sets `name = 'apps.<name>'`). Project config (settings/urls/wsgi) is in `backend/core/`.
- **Contract 1 — doctor isolation:** every queryset over patient-owned data filters by the requesting user. Don't introduce an endpoint that leaks another user's data.
- **Contract 2 — structured failure:** request-thread handlers return a plain dict envelope `{status, ...fields, error?, error_type?}` and must NEVER raise into the DRF view. Mirror this for the converters.
- Frontend: React 19, functional components only (the single documented class exception is `ErrorBoundary`). `npm run lint` (ESLint 9 flat config) must exit 0. Unit tests run on Vitest (`npm test`). i18n dictionaries live per-namespace under `frontend/src/i18n/locales/`, registered in `locales/index.js`, with **identical EN/FR key trees**.
- The Axios instance in `frontend/src/services/` already attaches the JWT and intercepts 401 → `/login`. Reuse it.

## What to build

Two parts: (A) rename the `admin` role to `Technician`; (B) build a Technician-only, multi-modal data-conversion tool. A Technician is a Doctor with one extra capability: converting the standard clinical file a clinic hands a patient into the exact format each model needs.

---

### Part A — Rename the `admin` role to `Technician`

Current state: `backend/apps/authentication/models.py` defines `User.Role` = `DOCTOR` + `ADMIN` (default `DOCTOR`); the role is embedded in the JWT (`MyTokenObtainPairSerializer`); public registration (`RegisterSerializer`) is hard-wired to create a `DOCTOR` and treats `role` as read-only (anti-self-elevation); `ADMIN` is set only by `create_superuser` and **no app endpoint is gated on it**. Frontend: `frontend/src/utils/constants.js` `ROLES`, `frontend/src/modules/Auth/Register.jsx` role picker, `frontend/src/components/Layout/Navbar.jsx` role badge, and `frontend/src/i18n/locales/auth.js` role labels.

Changes:
1. **Model** — `User.Role` becomes `DOCTOR` + `TECHNICIAN` (`'technician', 'Technician'`); remove `ADMIN`. Keep `DOCTOR` as the default.
2. **`create_superuser`** — default `role=TECHNICIAN`. Django-admin access still comes from `is_staff`/`is_superuser`, which remain **independent** of the app `role` field.
3. **Migration** — a new `authentication` migration that (a) updates the field `choices`, and (b) is a **data migration** rewriting any existing rows with `role='admin'` → `'technician'` (forward), so current admins become technicians. Make it reversible where sensible.
4. **Registration** — `RegisterSerializer` now **honors** a chosen `role`, but only within `{doctor, technician}`: validate the value (reject anything else with a 400) and default to `doctor` if absent. It must **still never** set `is_staff` or `is_superuser` — those stay server-controlled. The JWT keeps carrying `role` unchanged.
5. **Frontend** — `ROLES` = doctor/technician; the Register page sends the chosen role (the backend now honors it); the Navbar shows the role; `auth.js` gains `roles.technician` (EN `Technician` / FR `Technicien`) and drops `admin`. Update the `authSlice` register thunk only if it doesn't already pass `role`. Keep EN/FR parity.
6. **Tests** — update `backend/apps/authentication/tests.py`: registering with `role='technician'` creates a technician; registering with an invalid role is rejected; **self-registration still cannot grant `is_staff`/`is_superuser`** (add/keep a test proving a malicious `is_staff=true`/`is_superuser=true` in the payload is ignored); a superuser created via `create_superuser` has `role=technician`.

---

### Part B — Converter backend (new app `apps/conversion`)

Create a new Django app `backend/apps/conversion` (registered as `apps.conversion` in `INSTALLED_APPS`; `apps.py` sets `name = 'apps.conversion'`). Wire its URLs under the `api/convert/` prefix in `backend/core/urls.py`.

- **Permission** — `IsTechnician` DRF permission: authenticated AND `request.user.role == 'technician'`. Apply it to every conversion endpoint, so a doctor gets **403** (defense in depth; the frontend also hides the page).
- **Endpoint** — `POST /api/convert/<modality>/` where `<modality> ∈ {mri, ecg, echo, eeg}`. Accepts multipart: the raw uploaded file plus modality-specific params (e.g. MRI `slice_index`). On success, returns the **standardized file as a download** (`Content-Disposition: attachment; filename=...`, correct `Content-Type`). On failure, return a JSON error envelope `{status: 'failed', error, error_type}` with an appropriate 4xx/422 — converters must NOT raise into the view (catch and convert to the envelope, mirroring Contract 2). The output is download-only; do **not** auto-create an analysis (the technician re-uploads via the normal pages).
- **Converters** — one pure module per modality under `backend/apps/conversion/converters/{mri,ecg,echo,eeg}.py`, each exposing `convert(input_path, **params) -> (output_path, meta: dict)`; keep the DRF view thin. All required libraries are already dependencies (`pydicom 2.4.4`, `nibabel 5.2.0`, `opencv-python-headless 4.9.0.80`, `mne 1.12.1`, `edfio 0.4.13`, `wfdb 4.1.2`, `scipy`, `pandas`, `numpy`, `Pillow`).

| Modality | Input (standard clinic file) | Conversion | Output |
|---|---|---|---|
| **MRI** | DICOM series (`.zip` of `.dcm`) or single `.dcm`, or NIfTI `.nii`/`.nii.gz` volume | pydicom/nibabel → select a 2D slice (middle by default, or `slice_index` param) → normalize to 8-bit grayscale | `.png` |
| **ECG** | **DICOM ECG** waveform (`.dcm`) — the primary supported input | pydicom `WaveformSequence` → extract 12-lead samples → resample to the model's rate, standard lead order | `.csv` |
| **EEG** | Non-EDF clinical formats: BrainVision (`.vhdr`+`.eeg`), BioSemi `.bdf`, EEGLAB `.set` (multi-file inputs uploaded as a `.zip`) | `mne.io.read_raw_*` → export via `edfio` | `.edf` |
| **Echo** | DICOM ultrasound **cine** (multiframe `.dcm`) — primary; also `.mov`/`.mkv` | pydicom multiframe (or opencv) → frames → opencv `VideoWriter` | `.mp4` |

Converter rules:
- **Multi-file inputs** (DICOM series, BrainVision) arrive as a single uploaded **`.zip`**; unpack to a temp dir server-side, find the relevant files, convert, clean up.
- **ECG** commits to **DICOM ECG** via pydicom now; structure the module so a vendor-XML/SCP parser can be added later, but return a clear, friendly error for any unsupported input (don't half-implement digitization of scanned printouts — that's explicitly out of scope).
- Validate inputs and surface clear errors (unsupported extension, unreadable/corrupt file, no waveform/slices found, etc.). Enforce a sane max upload size.
- Write outputs to a temp/working dir; stream the file back; don't leave stray files.

---

### Part C — Converter frontend (`modules/Convert`)

- A **Technician-only** "Convert data" page under a new module `frontend/src/modules/Convert/`. Layout: four modality tabs/cards (MRI, ECG, Echo, EEG). Each: upload the raw file, set any modality params, click **Convert**, then the standardized file **downloads** to the technician (who then runs the analysis via the existing upload pages).
- **Gating** — add a "Convert data" nav entry and a `/convert` route that are shown/registered only when `user.role === 'technician'` (use the existing `useAuth`/auth slice). The backend `IsTechnician` is the real enforcement; the UI gate is for UX. Routes are registered in `frontend/src/App.jsx`; nav in `frontend/src/components/Layout/Navbar.jsx`.
- **Service** — `frontend/src/services/conversionService.js` wrapping `POST /api/convert/<modality>/` with `responseType: 'blob'` (so the file downloads), using the shared Axios instance. Trigger a client-side download from the blob + the response's filename.
- **i18n** — new `frontend/src/i18n/locales/convert.js` namespace (EN + FR, identical key trees), registered in `locales/index.js`; add a nav label to `nav.js`. Follow `THEME-I18N-CONVENTIONS.md` (tokens, `useI18n`, EN/FR parity).
- Functional components, Tailwind utility classes, drag/drop or file input consistent with the existing modality upload pages (look at `frontend/src/modules/{MRI,ECG,Echo,EEG}/*Upload.jsx` for the established pattern, loading/error states, and toasts).

---

## Verification (run these; everything must pass before you call it done)

Backend (from `backend/`, venv active):
```
python manage.py check
python manage.py makemigrations --check --dry-run        # should report no missing migrations after you add yours
python manage.py migrate                                  # applies cleanly (djongo warnings about schema/columns are expected/no-ops)
python manage.py test tests.test_doctor_isolation tests.test_health   # weight-free DB suites still pass
python manage.py test apps.authentication.tests          # your updated auth/role tests
python manage.py test apps.conversion                     # converter + IsTechnician tests (these need the heavy libs; run locally)
```
Frontend (from `frontend/`):
```
npm run lint     # MUST exit 0
npm test         # Vitest — all suites green; add tests for the Convert page gating + one modality form
npm run build    # production build succeeds
```

Add tests:
- Backend: the auth/role security tests above; `IsTechnician` returns 403 for a doctor and 200/2xx for a technician; a per-modality converter smoke test on a tiny synthetic fixture (e.g. a 1-frame DICOM, a 2-channel BDF, a short multiframe DICOM, a small NIfTI) asserting the output file is produced with the right type.
- Frontend: a render test that the `/convert` page/nav is hidden for a doctor and shown for a technician, plus one modality form rendering + submit wiring (mock the service).

## Suggested order

1. Part A model + `create_superuser` + migration + serializer, then its tests → verify auth suite.
2. Scaffold `apps/conversion` (app, `IsTechnician`, URL wiring, the dispatch view with the error envelope) with a stub converter, prove the 403/200 gating + routing.
3. Implement the four converters one at a time, each with its smoke test (MRI and Echo first — simplest; then EEG via mne/edfio; then ECG via pydicom waveform).
4. Frontend role rename (constants/register/navbar/i18n).
5. Frontend Convert module: service → page + tabs → route + nav gating → i18n → tests.
6. Full verification sweep (all commands above), then a final self-review for the two backend contracts, EN/FR parity, and lint.

## Definition of done

- `admin` is gone everywhere (enum, frontend constants, i18n, register, navbar); `technician` exists and is self-registerable; existing admin rows migrate to technician; superusers are technicians; self-registration still cannot grant staff/superuser.
- `POST /api/convert/{mri,ecg,echo,eeg}/` works for a technician, 403s for a doctor, returns the right standardized file per the table, and never 500s on bad input (clean error envelope instead).
- The Technician-only `/convert` page converts + downloads each modality and is invisible to doctors.
- All verification commands pass; new tests cover the role security, the permission gate, each converter, and the frontend gating.
- No existing contract broken (doctor isolation, result-envelope pattern), lint clean, EN/FR parity intact.

Work through it methodically, keep commits/edits focused, and report what you verified with the actual command output.
