from django.db import models


class EchoAnalysis(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    patient = models.ForeignKey(
        'patients.Patient',
        on_delete=models.CASCADE,
        related_name='echo_analyses',
    )
    file = models.FileField(upload_to='echo/uploads/')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    model_used = models.CharField(max_length=255, blank=True)

    result_ef = models.FloatField(null=True, blank=True)
    result_ef_category = models.CharField(max_length=64, null=True, blank=True)
    result_ed_area = models.IntegerField(null=True, blank=True)
    result_es_area = models.IntegerField(null=True, blank=True)
    result_overlay_path = models.CharField(max_length=500, null=True, blank=True)
    result_report = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Echo analyses'

    def __str__(self):
        return f'Echo #{self.pk} — {self.patient.full_name} ({self.status})'
