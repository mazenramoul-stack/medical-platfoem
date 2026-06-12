"""Echocardiography analysis REST endpoints (mounted at /api/echo/).

    POST    /upload/         multipart upload + synchronous EchoNet inference
    GET     /                list (doctor-scoped)
    GET     /{id}/           retrieve one
    DELETE  /{id}/           delete record + on-disk artifacts
"""

import logging
import os

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.inference import analyze_echo, run_inference_with_timeout
from apps.patients.models import Patient

from .models import EchoAnalysis
from .serializers import EchoAnalysisSerializer

logger = logging.getLogger(__name__)

ALLOWED_ECHO_EXTENSIONS = {'.avi', '.mp4', '.mov', '.webm', '.mkv'}
MAX_ECHO_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB (echo clips are large)
ECHO_TIMEOUT_SECONDS = 600               # video inference on CPU is slow


def _relative_to_media(absolute_path):
    if not absolute_path:
        return None
    try:
        rel = os.path.relpath(absolute_path, settings.MEDIA_ROOT)
    except ValueError:
        return None
    return rel.replace('\\', '/')


class EchoUploadView(APIView):
    """POST /api/echo/upload/ — multipart {patient_id, file}."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        patient_id = request.data.get('patient_id')
        uploaded = request.FILES.get('file')

        if not patient_id:
            return Response({'detail': 'patient_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if uploaded is None:
            return Response({'detail': 'file is required.'}, status=status.HTTP_400_BAD_REQUEST)

        ext = os.path.splitext(uploaded.name.lower())[1]
        if ext not in ALLOWED_ECHO_EXTENSIONS:
            return Response(
                {'detail': f'Unsupported echo video extension: {ext}. '
                           f'Allowed: {sorted(ALLOWED_ECHO_EXTENSIONS)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if uploaded.size > MAX_ECHO_SIZE_BYTES:
            return Response(
                {'detail': f'File too large ({uploaded.size} bytes). '
                           f'Max: {MAX_ECHO_SIZE_BYTES} bytes (500MB).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        patient = get_object_or_404(Patient, pk=patient_id, doctor=request.user)

        with transaction.atomic():
            analysis = EchoAnalysis.objects.create(
                patient=patient, file=uploaded, status=EchoAnalysis.Status.PROCESSING,
            )
        logger.info('Echo upload: analysis_id=%s patient_id=%s size=%d',
                    analysis.pk, patient.pk, uploaded.size)

        file_disk_path = analysis.file.path
        result = run_inference_with_timeout(analyze_echo, file_disk_path, ECHO_TIMEOUT_SECONDS)
        logger.info('Echo inference done: analysis_id=%s status=%s', analysis.pk, result.get('status'))

        with transaction.atomic():
            if result.get('status') == 'success':
                analysis.status = EchoAnalysis.Status.COMPLETED
                analysis.model_used = ' | '.join(result.get('models_used', []))
                analysis.result_ef = result.get('ejection_fraction')
                analysis.result_ef_category = result.get('ef_category')
                analysis.result_ed_area = result.get('ed_area_px')
                analysis.result_es_area = result.get('es_area_px')
                analysis.result_overlay_path = _relative_to_media(result.get('overlay_path'))
                analysis.result_report = result.get('report')
            else:
                analysis.status = EchoAnalysis.Status.FAILED
                analysis.result_report = (
                    f"Inference failed.\nType: {result.get('error_type')}\n"
                    f"Detail: {result.get('error')}"
                )
                logger.error('Echo inference failed: analysis_id=%s type=%s err=%s',
                             analysis.pk, result.get('error_type'), result.get('error'))
            analysis.save()

        serializer = EchoAnalysisSerializer(analysis, context={'request': request})
        http_status = status.HTTP_201_CREATED if result.get('status') == 'success' else status.HTTP_202_ACCEPTED
        return Response(serializer.data, status=http_status)


class EchoListView(generics.ListAPIView):
    """GET /api/echo/?patient_id=<id> — doctor-scoped list."""

    serializer_class = EchoAnalysisSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = EchoAnalysis.objects.filter(patient__doctor=self.request.user)
        patient_id = self.request.query_params.get('patient_id')
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        return qs.order_by('-created_at')


class EchoDetailView(generics.RetrieveDestroyAPIView):
    """GET / DELETE /api/echo/{id}/"""

    serializer_class = EchoAnalysisSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return EchoAnalysis.objects.filter(patient__doctor=self.request.user)

    def perform_destroy(self, instance):
        try:
            if instance.file:
                instance.file.delete(save=False)
        except Exception as e:
            logger.warning('Could not delete echo upload: %s', e)
        if instance.result_overlay_path:
            absolute = os.path.join(settings.MEDIA_ROOT, instance.result_overlay_path)
            try:
                if os.path.exists(absolute):
                    os.remove(absolute)
            except OSError as e:
                logger.warning('Could not delete echo artifact %s: %s', absolute, e)
        instance.delete()
