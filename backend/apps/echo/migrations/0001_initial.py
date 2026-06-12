from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('patients', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='EchoAnalysis',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='echo/uploads/')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('model_used', models.CharField(blank=True, max_length=255)),
                ('result_ef', models.FloatField(blank=True, null=True)),
                ('result_ef_category', models.CharField(blank=True, max_length=64, null=True)),
                ('result_ed_area', models.IntegerField(blank=True, null=True)),
                ('result_es_area', models.IntegerField(blank=True, null=True)),
                ('result_overlay_path', models.CharField(blank=True, max_length=500, null=True)),
                ('result_report', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='echo_analyses', to='patients.patient')),
            ],
            options={
                'verbose_name_plural': 'Echo analyses',
                'ordering': ['-created_at'],
            },
        ),
    ]
