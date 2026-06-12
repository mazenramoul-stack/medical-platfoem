from rest_framework import serializers

from core.media import signed_media_url

from .models import EchoAnalysis


class EchoAnalysisSerializer(serializers.ModelSerializer):
    """Read serializer for echo analyses, with computed absolute media URLs."""

    file_url = serializers.SerializerMethodField()
    overlay_url = serializers.SerializerMethodField()

    class Meta:
        model = EchoAnalysis
        fields = (
            'id', 'patient', 'file', 'file_url', 'status', 'model_used',
            'result_ef', 'result_ef_category', 'result_ed_area', 'result_es_area',
            'result_overlay_path', 'overlay_url', 'result_report', 'created_at',
        )
        read_only_fields = (
            'id', 'status', 'model_used', 'result_ef', 'result_ef_category',
            'result_ed_area', 'result_es_area', 'result_overlay_path',
            'result_report', 'created_at', 'file_url', 'overlay_url',
        )

    def get_file_url(self, obj):
        return signed_media_url(self.context.get('request'), obj.file.url) if obj.file else None

    def get_overlay_url(self, obj):
        return signed_media_url(self.context.get('request'), obj.result_overlay_path)
