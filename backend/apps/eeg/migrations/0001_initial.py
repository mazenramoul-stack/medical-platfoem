from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('patients', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='EEGAnalysis',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='eeg/uploads/')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('model_used', models.CharField(blank=True, max_length=255)),
                ('result_dominant_pattern', models.CharField(blank=True, max_length=16, null=True)),
                ('result_harmful', models.BooleanField(blank=True, null=True)),
                ('result_class_distribution', models.JSONField(blank=True, null=True)),
                ('result_plot_path', models.CharField(blank=True, max_length=500, null=True)),
                ('result_report', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='eeg_analyses', to='patients.patient')),
            ],
            options={
                'verbose_name_plural': 'EEG analyses',
                'ordering': ['-created_at'],
            },
        ),
    ]
