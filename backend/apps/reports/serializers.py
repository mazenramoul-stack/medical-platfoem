from rest_framework import serializers

from core.media import signed_media_url

from .models import Report


class ReportSerializer(serializers.ModelSerializer):
    """Read serializer for combined MRI+ECG PDF reports."""

    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = (
            'id',
            'patient',
            'mri_analysis',
            'ecg_analysis',
            'echo_analysis',
            'eeg_analysis',
            'pdf_file',
            'pdf_url',
            'created_at',
        )
        read_only_fields = ('id', 'pdf_file', 'pdf_url', 'created_at')

    def get_pdf_url(self, obj):
        if not obj.pdf_file:
            return None
        return signed_media_url(self.context.get('request'), obj.pdf_file.url)
