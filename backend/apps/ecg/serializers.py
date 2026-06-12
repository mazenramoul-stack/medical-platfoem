from rest_framework import serializers

from core.media import signed_media_url

from .models import ECGAnalysis


class ECGAnalysisSerializer(serializers.ModelSerializer):
    """Read serializer for ECG analyses.

    Exposes computed url fields for the uploaded signal and the generated
    12-lead plot. JSONFields are forwarded as-is by DRF.
    """

    file_url = serializers.SerializerMethodField()
    plot_url = serializers.SerializerMethodField()

    class Meta:
        model = ECGAnalysis
        fields = (
            'id',
            'patient',
            'file',
            'file_url',
            'status',
            'model_used',
            'result_arrhythmia_detected',
            'result_arrhythmia_type',
            'result_confidence',
            'result_hrv_metrics',
            'result_pathology_probabilities',
            'result_plot_path',
            'plot_url',
            'result_report',
            'created_at',
        )
        read_only_fields = (
            'id', 'status', 'model_used',
            'result_arrhythmia_detected', 'result_arrhythmia_type', 'result_confidence',
            'result_hrv_metrics', 'result_pathology_probabilities',
            'result_plot_path', 'result_report', 'created_at',
            'file_url', 'plot_url',
        )

    def get_file_url(self, obj):
        if not obj.file:
            return None
        return signed_media_url(self.context.get('request'), obj.file.url)

    def get_plot_url(self, obj):
        return signed_media_url(self.context.get('request'), obj.result_plot_path)
