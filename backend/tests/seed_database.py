"""Populate the dev database with a default doctor and a few sample patients.

Idempotent — safe to re-run; existing records are not duplicated.

Usage (from anywhere — the script bootstraps Django itself):
    python backend/tests/seed_database.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = THIS_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django
django.setup()

from django.contrib.auth import get_user_model
from apps.patients.models import Patient, PatientAssignment


DOCTOR = {
    "email": "doctor@test.com",
    "password": "TestPass123!",
    "full_name": "Dr. Test",
    "role": "doctor",
}

PATIENTS = [
    {"full_name": "John Doe",        "age": 45, "gender": "M",
     "medical_history": "Hypertension, type-2 diabetes."},
    {"full_name": "Jane Smith",      "age": 62, "gender": "F",
     "medical_history": "Atrial fibrillation, anticoagulated on warfarin."},
    {"full_name": "Karim Mansouri",  "age": 38, "gender": "M",
     "medical_history": "Recurrent migraine, family history of glioma."},
    {"full_name": "Aïcha Ben Salah", "age": 71, "gender": "F",
     "medical_history": "Post-MI, ejection fraction 35%, on beta-blocker."},
    {"full_name": "Tom Williams",    "age": 29, "gender": "M",
     "medical_history": "Athlete, resting bradycardia on routine ECG."},
]


def seed_doctor() -> 'User':  # type: ignore[name-defined]
    User = get_user_model()
    existing = User.objects.filter(email=DOCTOR["email"]).first()
    if existing:
        print(f"  [skip] doctor {DOCTOR['email']!r} already exists (id={existing.pk})")
        return existing
    user = User.objects.create_user(
        email=DOCTOR["email"],
        password=DOCTOR["password"],
        full_name=DOCTOR["full_name"],
        role=DOCTOR["role"],
    )
    print(f"  [new]  doctor {DOCTOR['email']!r} created (id={user.pk})")
    return user


def seed_patients(doctor) -> None:
    for spec in PATIENTS:
        # Idempotency by created_by + name (a plain FK field — djongo-safe).
        existing = Patient.objects.filter(
            created_by=doctor, full_name=spec["full_name"],
        ).first()
        if existing:
            print(f"  [skip] patient {spec['full_name']!r} already exists (id={existing.pk})")
            continue
        p = Patient.objects.create(created_by=doctor, **spec)
        PatientAssignment.objects.get_or_create(
            patient=p, doctor=doctor, defaults={"assigned_by": doctor})
        print(f"  [new]  patient {spec['full_name']!r} created (id={p.pk})")


def main() -> int:
    print("Seeding dev database…")
    doctor = seed_doctor()
    seed_patients(doctor)

    from apps.patients.models import Patient as P
    n_patients = P.objects.filter(created_by=doctor).count()
    print(f"\nDone. doctor={doctor.email}  patients={n_patients}")
    print(f"Login: {DOCTOR['email']} / {DOCTOR['password']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
