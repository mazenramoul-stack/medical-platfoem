from django.db import models


class MRIAnalysis(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    patient = models.ForeignKey(
        'patients.Patient',
        on_delete=models.CASCADE,
        related_name='mri_analyses',
    )
    file = models.FileField(upload_to='mri/uploads/')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    model_used = models.CharField(max_length=255, blank=True)

    result_tumor_detected = models.BooleanField(null=True, blank=True)
    result_tumor_type = models.CharField(max_length=255, null=True, blank=True)
    result_confidence = models.FloatField(null=True, blank=True)
    result_mask_path = models.CharField(max_length=500, null=True, blank=True)
    result_overlay_path = models.CharField(max_length=500, null=True, blank=True)
    result_analysis_path = models.CharField(max_length=500, null=True, blank=True)
    result_gradcam_path = models.CharField(max_length=500, null=True, blank=True)
    result_report = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'MRI analyses'

    def __str__(self):
        return f'MRI #{self.pk} — {self.patient.full_name} ({self.status})'
