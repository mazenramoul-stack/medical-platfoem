from django.conf import settings
from django.db import models


class Patient(models.Model):
    class Gender(models.TextChoices):
        MALE = 'M', 'Male'
        FEMALE = 'F', 'Female'
        OTHER = 'O', 'Other'

    full_name = models.CharField(max_length=255)
    age = models.PositiveIntegerField()
    gender = models.CharField(max_length=1, choices=Gender.choices)
    medical_history = models.TextField(blank=True)
    # Who created the record (a doctor self-registering a patient, or a
    # technician doing intake). Kept for lineage only — ACCESS is governed by
    # PatientAssignment, not this field. SET_NULL so removing a user never
    # deletes patient data.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_patients',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.full_name} ({self.age})'


class PatientAssignment(models.Model):
    """A doctor's access to a patient.

    Replaces the old single ``Patient.doctor`` owner FK: a patient may now be
    assigned to many doctors (e.g. by a technician), and a doctor sees a patient
    iff an assignment row exists. It is a plain join model — NOT a Django
    ManyToManyField — so access can be scoped with shallow ``id__in`` queries
    that djongo handles reliably (see apps.patients.access); djongo's implicit
    M2M tables and 2-level joins are unreliable on MongoDB.
    """

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name='assignments')
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='patient_assignments')
    # Who created the assignment (a technician, or the doctor self-assigning).
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+')
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('patient', 'doctor')
        ordering = ['assigned_at']

    def __str__(self):
        return f'patient {self.patient_id} -> doctor {self.doctor_id}'
