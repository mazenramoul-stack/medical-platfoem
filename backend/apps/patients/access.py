"""Single source of truth for who may see which patients (and their analyses).

Replaces the old ``doctor=request.user`` ownership check. A technician
(back-office) sees everything; a doctor sees only patients assigned to them via
PatientAssignment. Scoping uses shallow ``id__in`` / ``patient_id__in`` queries
(materialised id lists, no 2-level joins) so it stays djongo-safe.

Every queryset over patient-owned data in patients / mri / ecg / echo / eeg /
reports routes through these helpers — that is the doctor-isolation contract,
redefined from "owns" to "is assigned".
"""

from django.shortcuts import get_object_or_404

from apps.authentication.models import User

from .models import Patient, PatientAssignment


def visible_patient_ids(user):
    """Patient ids the user may access, or None meaning 'all' (technician)."""
    if getattr(user, 'role', None) == User.Role.TECHNICIAN:
        return None
    return list(
        PatientAssignment.objects.filter(doctor=user).values_list('patient_id', flat=True)
    )


def scope_patients(user, qs=None):
    """Restrict a Patient queryset to what `user` may see."""
    qs = Patient.objects.all() if qs is None else qs
    ids = visible_patient_ids(user)
    return qs if ids is None else qs.filter(id__in=ids)


def scope_by_patient(user, qs):
    """Restrict a queryset of patient-owned rows (analyses, reports) to `user`."""
    ids = visible_patient_ids(user)
    return qs if ids is None else qs.filter(patient_id__in=ids)


def get_patient_or_404(user, pk):
    """Fetch a patient `user` may access, else 404 (never an authorization leak)."""
    return get_object_or_404(scope_patients(user), pk=pk)
