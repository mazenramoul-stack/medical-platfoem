"""Rename the `admin` role to `technician`.

(a) Updates the User.role field choices to {doctor, technician}, and
(b) data-migrates any existing rows with role='admin' to 'technician', so a
clinic's current admins become technicians.

djongo is schemaless, so the AlterField is a no-op at the MongoDB layer; the
RunPython data step is the one that actually matters in production. Both are
recorded so `makemigrations --check` stays clean.
"""

from django.db import migrations, models


def admins_to_technicians(apps, schema_editor):
    User = apps.get_model('authentication', 'User')
    User.objects.filter(role='admin').update(role='technician')


def technicians_to_admins(apps, schema_editor):
    # Best-effort reverse so the data stays consistent with the reverted field
    # choices. It cannot distinguish an original admin from a self-registered
    # technician, so it maps ALL technicians back to admin.
    User = apps.get_model('authentication', 'User')
    User.objects.filter(role='technician').update(role='admin')


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[('doctor', 'Doctor'), ('technician', 'Technician')],
                default='doctor',
                max_length=20,
            ),
        ),
        migrations.RunPython(admins_to_technicians, technicians_to_admins),
    ]
