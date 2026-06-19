"""Replace Patient.doctor (single owner FK) with PatientAssignment (many doctors).

Schema: add PatientAssignment + Patient.created_by, then drop Patient.doctor.
Data: migrate each existing patient's `doctor` into an assignment (and into
`created_by`) so no doctor loses access.

djongo is schemaless, so the schema ops are no-ops at the MongoDB layer; the
RunPython data step is the meaningful one. Applies normally on the SQLite test DB.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def doctor_to_assignment(apps, schema_editor):
    Patient = apps.get_model('patients', 'Patient')
    PatientAssignment = apps.get_model('patients', 'PatientAssignment')
    for patient in Patient.objects.all():
        doctor_id = getattr(patient, 'doctor_id', None)
        if not doctor_id:
            continue
        patient.created_by_id = doctor_id
        patient.save(update_fields=['created_by'])
        PatientAssignment.objects.get_or_create(
            patient=patient, doctor_id=doctor_id,
            defaults={'assigned_by_id': doctor_id},
        )


def assignment_to_doctor(apps, schema_editor):
    # Best-effort reverse: put the first assigned doctor back on patient.doctor.
    Patient = apps.get_model('patients', 'Patient')
    PatientAssignment = apps.get_model('patients', 'PatientAssignment')
    for patient in Patient.objects.all():
        first = PatientAssignment.objects.filter(patient=patient).order_by('assigned_at').first()
        if first:
            patient.doctor_id = first.doctor_id
            patient.save(update_fields=['doctor'])


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PatientAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('assigned_at', models.DateTimeField(auto_now_add=True)),
                ('assigned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('doctor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='patient_assignments', to=settings.AUTH_USER_MODEL)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignments', to='patients.patient')),
            ],
            options={
                'ordering': ['assigned_at'],
                'unique_together': {('patient', 'doctor')},
            },
        ),
        migrations.AddField(
            model_name='patient',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_patients', to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(doctor_to_assignment, assignment_to_doctor),
        migrations.RemoveField(
            model_name='patient',
            name='doctor',
        ),
    ]
