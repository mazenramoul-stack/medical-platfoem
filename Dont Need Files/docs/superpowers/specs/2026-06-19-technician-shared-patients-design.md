# Design: Technician-assigned shared patients

**Date:** 2026-06-19
**Status:** Proposed (awaiting review)
**Branch:** feat/mri-xai-pilot

## Summary

Let a **Technician** enter a patient's information, run the real AI analyses for
that patient, and assign the patient to **one or more doctors**. Each assigned
doctor sees the patient and its analyses/reports; a Technician (back-office role)
sees everything.

This replaces the platform's "one patient → one owning doctor" model with a
"patient → set of assigned doctors" model, which redefines (but preserves) the
doctor-isolation contract.

## Decisions (locked with the user)

1. **"Enter an analysis" = run the real AI.** The Technician uploads the file and
   the existing MRI/ECG/Echo/EEG pipeline runs — same code path as a doctor. No
   new inference code, no manual result entry.
2. **Patient↔doctor is many-to-many, existing data migrated.** The single
   `Patient.doctor` FK is replaced; each current patient's doctor is migrated into
   the new assignment so nobody loses access.
3. **Technician is back-office.** A Technician can see and manage *every* patient,
   analysis and report in the system. A doctor still sees only patients assigned
   to them.
4. **Reuse existing pages (no dedicated intake page).** `PatientForm` gains a
   doctor multi-select for technicians; technicians reuse the normal patient and
   MRI/ECG/Echo/EEG upload pages.

## Non-goals (YAGNI)

- No change to the inference pipelines or the conversion tool.
- Assignment is at the **patient** level, not per-analysis.
- No notifications/audit-trail UI (a `created_by` / `assigned_by` field is stored
  for data lineage, but there's no UI around it).
- A Technician is never assignable *as a doctor* on a patient.
- Doctors cannot reassign patients or self-assign (anti-privilege-escalation).

## Data model

`apps/patients/models.py`:

- **New `PatientAssignment` join model** (plain FKs, not a Django M2M):
  - `patient`  → FK(Patient, `related_name='assignments'`, CASCADE)
  - `doctor`   → FK(User, `related_name='patient_assignments'`, CASCADE)
  - `assigned_by` → FK(User, null=True, SET_NULL, `related_name='+'`)
  - `assigned_at` → DateTimeField(auto_now_add=True)
  - `Meta.unique_together = ('patient', 'doctor')`
- **`Patient`**:
  - **Remove** the `doctor` FK.
  - **Add** `created_by` → FK(User, null=True, blank=True, SET_NULL,
    `related_name='created_patients'`) for lineage.
  - A patient's assigned doctors are read via the reverse relation
    `patient.assignments` (a 1-level reverse FK, exactly like the existing
    `patient.mri_analyses`).

### Why a join model instead of Django's `ManyToManyField`

djongo 1.3.6's implicit M2M tables are unreliable on MongoDB, and the
analysis-isolation filter would otherwise become a 2-level join
(`MRIAnalysis.objects.filter(patient__doctors__id=...)`) that djongo handles
poorly. A plain join model lets us scope with **shallow `id__in` queries** (below)
that mirror the FK filters already proven to work in this codebase, and the
reverse relation gives ergonomic reads without an M2M descriptor.

## Access control (the doctor-isolation contract, redefined)

New single-source-of-truth module `apps/patients/access.py`:

```python
def visible_patient_ids(user):
    """Patient ids the user may access, or None meaning 'all' (technician)."""
    if user.role == User.Role.TECHNICIAN:
        return None
    # materialised to a list — djongo dislikes queryset subqueries in __in
    return list(PatientAssignment.objects.filter(doctor=user)
                .values_list('patient_id', flat=True))

def scope_patients(user, qs=None):
    qs = qs if qs is not None else Patient.objects.all()
    ids = visible_patient_ids(user)
    return qs if ids is None else qs.filter(id__in=ids)

def scope_by_patient(user, qs):       # analyses / reports (have a patient FK)
    ids = visible_patient_ids(user)
    return qs if ids is None else qs.filter(patient_id__in=ids)

def get_patient_or_404(user, pk):
    return get_object_or_404(scope_patients(user), pk=pk)
```

- **Technician** → `None` ⇒ unfiltered (full access).
- **Doctor** → only patients assigned to them, and those patients' analyses/reports.
- The invariant is unchanged in spirit ("a doctor never sees another's data") — only
  the definition of "their data" changes from *owns* to *is assigned*.

Every current enforcement point switches to these helpers:

| File | Current | New |
|---|---|---|
| `patients/views.py` | `filter(doctor=user)`, `save(doctor=user)` | `scope_patients(user)`, assignment logic in serializer |
| `mri/views.py` | `get_object_or_404(Patient, …, doctor=user)`, `filter(patient__doctor=user)` ×2, explain | `get_patient_or_404`, `scope_by_patient` |
| `ecg/views.py` | same pattern | same |
| `echo/views.py` | same pattern | same |
| `eeg/views.py` | same pattern | same |
| `reports/views.py` | `patient__doctor=user` ×4 (generate, list, detail, download) | `get_patient_or_404` / `scope_by_patient` |

## API changes

- **`GET /api/auth/doctors/`** — *technician-only* (`IsTechnician`). Returns
  `[{id, full_name, email}]` for the assignment picker. (Doctors don't get the user
  directory.)
- **Shared `IsTechnician`** — move the existing `apps/conversion/permissions.py`
  `IsTechnician` to `apps/authentication/permissions.py`; conversion re-imports it.
- **Patient serializer/views**:
  - Read: drop `doctor`/`doctor_name`; add `doctors` (`[{id, full_name}]` from
    `assignments`), `created_by`, `created_by_name`.
  - Write: `doctor_ids` (write-only list) honored **only when the requester is a
    technician**, and each id is validated to be a `role=doctor` user (else 400).
    A doctor creating a patient is auto-assigned to themselves and **cannot** set
    `doctor_ids`. Reassignment = `PATCH` by a technician.
  - `perform_create` sets `created_by=request.user`.
- **Analysis upload endpoints** resolve the patient through `get_patient_or_404`,
  so a technician can upload + run the pipeline for any patient and the result is
  immediately visible to the assigned doctor(s). No inference changes.

## Migration & backward compatibility

`apps/patients/migrations/0002_*`:
1. `CreateModel(PatientAssignment)`
2. `AddField(Patient.created_by)`
3. `RunPython`: for each patient, create a `PatientAssignment(patient, doctor=old
   doctor, assigned_by=old doctor)` and set `created_by = old doctor`. (Reverse:
   copy the first assignment's doctor back into a re-added `doctor` field —
   best-effort.)
4. `RemoveField(Patient.doctor)`

Applies cleanly on the in-memory SQLite test DB (where the suite runs). On
djongo/Mongo the schema ops are no-ops and the `RunPython` data step is the
meaningful one. The unrelated `token_blacklist` djongo quirk (documented in
CLAUDE.md, handled by `start-space.sh`) is independent of this.

Also update `backend/tests/seed_database.py` (and any tool that creates patients)
to attach an assignment instead of setting `doctor=`.

## Frontend

- **`services/doctorService.js`** (new) — `getDoctors()` → `GET /auth/doctors/`.
- **`PatientForm.jsx`** — when `user.role === 'technician'`, render a doctor
  multi-select (loaded via `doctorService`) and submit `doctor_ids`. Hidden for
  doctors (who are auto-assigned).
- **`PatientList.jsx` / `PatientDetail.jsx`** — show assigned-doctor chips instead
  of a single `doctor_name`.
- **`patientService` / `patientsSlice`** — pass `doctor_ids` through create/update;
  consume the new `doctors[]` in responses.
- **i18n** — new keys in `patients.js` (e.g. `assignDoctors`, `assignedDoctors`,
  `noDoctorsAssigned`), EN/FR parity.

## Testing (TDD)

Rewrite `backend/tests/test_doctor_isolation.py` and add cases:
- A doctor sees only patients assigned to them; cannot retrieve/list/delete an
  unassigned patient (still 404).
- A patient assigned to **two** doctors is visible to **both**.
- A doctor cannot self-assign or set `doctor_ids` (escalation blocked).
- A **technician** sees all patients/analyses; can create a patient with
  `doctor_ids`; can upload an analysis for any patient and it becomes visible to the
  assigned doctor(s).
- `GET /api/auth/doctors/` is technician-only (doctor → 403).
- Update `PatientHistoryAggregateTest` and any other `Patient.objects.create(doctor=…)`
  call sites.

Frontend Vitest: `PatientForm` shows the doctor multi-select for a technician and
hides it for a doctor; submitting includes `doctor_ids`.

## Risks

- **djongo query behavior** — mitigated by the shallow `id__in` / `patient_id__in`
  pattern (materialised id lists), avoiding M2M tables and 2-level joins. Validate
  against a real Mongo early in implementation.
- **Migration on a populated DB** — the data migration is idempotent-ish and
  reversible best-effort; verify the existing single-doctor patients still resolve
  for their doctor after migrating.

## File-change checklist (for the plan)

Backend: `patients/models.py`, `patients/access.py` (new), `patients/serializers.py`,
`patients/views.py`, `patients/migrations/0002_*` (new), `mri/views.py`,
`ecg/views.py`, `echo/views.py`, `eeg/views.py`, `reports/views.py`,
`authentication/permissions.py` (new, move `IsTechnician`), `authentication/serializers.py`
(doctor list serializer), `authentication/views.py` + `urls.py` (doctors endpoint),
`conversion/permissions.py` (re-import), `tests/test_doctor_isolation.py`,
`tests/seed_database.py`.

Frontend: `services/doctorService.js` (new), `modules/Patients/PatientForm.jsx`,
`modules/Patients/PatientList.jsx`, `modules/Patients/PatientDetail.jsx`,
`services/patientService.js`, `store/slices/patientsSlice.js`,
`i18n/locales/patients.js`, `modules/Patients/PatientForm.test.jsx` (new/updated).
