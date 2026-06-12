from django.db import models


class Report(models.Model):
    patient = models.ForeignKey(
        'patients.Patient',
        on_delete=models.CASCADE,
        related_name='reports',
    )
    mri_analysis = models.ForeignKey(
        'mri.MRIAnalysis',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports',
    )
    ecg_analysis = models.ForeignKey(
        'ecg.ECGAnalysis',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports',
    )
    echo_analysis = models.ForeignKey(
        'echo.EchoAnalysis',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports',
    )
    eeg_analysis = models.ForeignKey(
        'eeg.EEGAnalysis',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports',
    )
    pdf_file = models.FileField(upload_to='reports/')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Report #{self.pk} — {self.patient.full_name}'
