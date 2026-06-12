"""ECG analysis REST endpoints.

Routes (mounted at /api/ecg/):
    POST    /upload/         multipart upload + synchronous inference
    GET     /                list (filtered to requesting doctor's patients)
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

from apps.inference import analyze_ecg, run_inference_with_timeout
from apps.patients.models import Patient

from .models import ECGAnalysis
from .serializers import ECGAnalysisSerializer

logger = logging.getLogger(__name__)


# File validation ----------------------------------------------------------

ALLOWED_ECG_EXTENSIONS = {'.csv', '.edf', '.dat', '.hea'}
MAX_ECG_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


def _detected_extension(filename: str) -> str:
    return os.path.splitext(filename.lower())[1]


def _relative_to_media(absolute_path: str) -> str | None:
    if not absolute_path:
        return None
    try:
        rel = os.path.relpath(absolute_path, settings.MEDIA_ROOT)
    except ValueError:
        return None
    return rel.replace('\\', '/')


# Views --------------------------------------------------------------------

class ECGUploadView(APIView):
    """POST /api/ecg/upload/ — multipart {patient_id, file}."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        patient_id = request.data.get('patient_id')
        uploaded = request.FILES.get('file')

        if not patient_id:
            return Response({'detail': 'patient_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if uploaded is None:
            return Response({'detail': 'file is required.'}, status=status.HTTP_400_BAD_REQUEST)

        ext = _detected_extension(uploaded.name)
        if ext not in ALLOWED_ECG_EXTENSIONS:
            return Response(
                {'detail': f'Unsupported ECG file extension: {ext}. '
                           f'Allowed: {sorted(ALLOWED_ECG_EXTENSIONS)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if uploaded.size > MAX_ECG_SIZE_BYTES:
            return Response(
                {'detail': f'File too large ({uploaded.size} bytes). '
                           f'Max allowed: {MAX_ECG_SIZE_BYTES} bytes (50MB).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        patient = get_object_or_404(Patient, pk=patient_id, doctor=request.user)

        with transaction.atomic():
            analysis = ECGAnalysis.objects.create(
                patient=patient,
                file=uploaded,
                status=ECGAnalysis.Status.PROCESSING,
            )
        logger.info("ECG upload received: analysis_id=%s patient_id=%s file=%s size=%d",
                    analysis.pk, patient.pk, analysis.file.name, uploaded.size)

        file_disk_path = analysis.file.path
        logger.info("ECG inference start: analysis_id=%s", analysis.pk)
        result = run_inference_with_timeout(analyze_ecg, file_disk_path, timeout_seconds=300)
        logger.info("ECG inference done: analysis_id=%s status=%s", analysis.pk, result.get('status'))

        with transaction.atomic():
            if result.get('status') == 'success':
                # Merge HR + classification into hrv_metrics for completeness
                hrv = dict(result.get('hrv_metrics') or {})
                hrv['heart_rate_bpm'] = result.get('heart_rate_bpm')
                hrv['hr_classification'] = result.get('hr_classification')
                hrv['additional_flags'] = result.get('additional_flags') or []

                analysis.status = ECGAnalysis.Status.COMPLETED
                analysis.model_used = ' | '.join(result.get('models_used', []))
                analysis.result_arrhythmia_detected = result.get('arrhythmia_detected')
                analysis.result_arrhythmia_type = result.get('diagnosis')
                analysis.result_confidence = result.get('diagnosis_confidence')
                analysis.result_hrv_metrics = hrv
                analysis.result_pathology_probabilities = result.get('all_pathology_probabilities')
                analysis.result_plot_path = _relative_to_media(result.get('plot_path'))
                analysis.result_report = result.get('report')
            else:
                analysis.status = ECGAnalysis.Status.FAILED
                analysis.result_report = (
                    f"Inference failed.\nType: {result.get('error_type')}\n"
                    f"Detail: {result.get('error')}"
                )
                logger.error("ECG inference failed: analysis_id=%s type=%s err=%s",
                             analysis.pk, result.get('error_type'), result.get('error'))
            analysis.save()

        serializer = ECGAnalysisSerializer(analysis, context={'request': request})
        http_status = status.HTTP_201_CREATED if result.get('status') == 'success' else status.HTTP_202_ACCEPTED
        return Response(serializer.data, status=http_status)


class ECGListView(generics.ListAPIView):
    """GET /api/ecg/?patient_id=<id>"""

    serializer_class = ECGAnalysisSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = ECGAnalysis.objects.filter(patient__doctor=self.request.user)
        patient_id = self.request.query_params.get('patient_id')
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        return qs.order_by('-created_at')


class ECGDetailView(generics.RetrieveDestroyAPIView):
    """GET / DELETE /api/ecg/{id}/"""

    serializer_class = ECGAnalysisSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ECGAnalysis.objects.filter(patient__doctor=self.request.user)

    def perform_destroy(self, instance):
        try:
            if instance.file:
                instance.file.delete(save=False)
        except Exception as e:
            logger.warning("Could not delete uploaded ECG file: %s", e)

        if instance.result_plot_path:
            absolute = os.path.join(settings.MEDIA_ROOT, instance.result_plot_path)
            try:
                if os.path.exists(absolute):
                    os.remove(absolute)
            except OSError as e:
                logger.warning("Could not delete ECG plot %s: %s", absolute, e)

        instance.delete()
