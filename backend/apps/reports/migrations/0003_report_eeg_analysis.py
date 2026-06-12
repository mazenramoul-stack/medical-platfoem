from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('eeg', '0001_initial'),
        ('reports', '0002_report_echo_analysis'),
    ]

    operations = [
        migrations.AddField(
            model_name='report',
            name='eeg_analysis',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='reports', to='eeg.eeganalysis',
            ),
        ),
    ]
