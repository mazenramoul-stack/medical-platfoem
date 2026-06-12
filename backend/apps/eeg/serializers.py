from rest_framework import serializers

from core.media import signed_media_url

from .models import EEGAnalysis


class EEGAnalysisSerializer(serializers.ModelSerializer):
    """Read serializer for EEG analyses, with computed absolute media URLs."""

    file_url = serializers.SerializerMethodField()
    plot_url = serializers.SerializerMethodField()

    class Meta:
        model = EEGAnalysis
        fields = (
            'id', 'patient', 'file', 'file_url', 'status', 'model_used',
            'result_dominant_pattern', 'result_harmful', 'result_class_distribution',
            'result_plot_path', 'plot_url', 'result_report', 'created_at',
        )
        read_only_fields = (
            'id', 'status', 'model_used', 'result_dominant_pattern', 'result_harmful',
            'result_class_distribution', 'result_plot_path', 'result_report',
            'created_at', 'file_url', 'plot_url',
        )

    def get_file_url(self, obj):
        return signed_media_url(self.context.get('request'), obj.file.url) if obj.file else None

    def get_plot_url(self, obj):
        return signed_media_url(self.context.get('request'), obj.result_plot_path)
