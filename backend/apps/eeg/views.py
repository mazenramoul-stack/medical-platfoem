"""EEG analysis REST endpoints (mounted at /api/eeg/).

    POST    /upload/         multipart upload + synchronous BIOT/IIIC inference
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

from apps.inference import analyze_eeg, explain_eeg, run_inference_with_timeout
from apps.patients.access import get_patient_or_404, scope_by_patient
from core.media import signed_media_url

from .models import EEGAnalysis
from .serializers import EEGAnalysisSerializer

logger = logging.getLogger(__name__)

ALLOWED_EEG_EXTENSIONS = {'.edf'}
MAX_EEG_SIZE_BYTES = 200 * 1024 * 1024  # 200 MB
EEG_TIMEOUT_SECONDS = 600               # BIOT over many 10s segments on CPU is slow


def _relative_to_media(absolute_path):
    if not absolute_path:
        return None
    try:
        rel = os.path.relpath(absolute_path, settings.MEDIA_ROOT)
    except ValueError:
        return None
    return rel.replace('\\', '/')


class EEGUploadView(APIView):
    """POST /api/eeg/upload/ — multipart {patient_id, file}."""

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
        if ext not in ALLOWED_EEG_EXTENSIONS:
            return Response(
                {'detail': f'Unsupported EEG extension: {ext}. '
                           f'Allowed: {sorted(ALLOWED_EEG_EXTENSIONS)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if uploaded.size > MAX_EEG_SIZE_BYTES:
            return Response(
                {'detail': f'File too large ({uploaded.size} bytes). '
                           f'Max: {MAX_EEG_SIZE_BYTES} bytes (200MB).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        patient = get_patient_or_404(request.user, patient_id)

        with transaction.atomic():
            analysis = EEGAnalysis.objects.create(
                patient=patient, file=uploaded, status=EEGAnalysis.Status.PROCESSING,
            )
        logger.info('EEG upload: analysis_id=%s patient_id=%s size=%d',
                    analysis.pk, patient.pk, uploaded.size)

        file_disk_path = analysis.file.path
        result = run_inference_with_timeout(analyze_eeg, file_disk_path, EEG_TIMEOUT_SECONDS)
        logger.info('EEG inference done: analysis_id=%s status=%s', analysis.pk, result.get('status'))

        with transaction.atomic():
            if result.get('status') == 'success':
                analysis.status = EEGAnalysis.Status.COMPLETED
                analysis.model_used = ' | '.join(result.get('models_used', []))
                analysis.result_dominant_pattern = result.get('dominant_pattern')
                analysis.result_harmful = result.get('harmful')
                analysis.result_class_distribution = result.get('class_distribution')
                analysis.result_plot_path = _relative_to_media(result.get('plot_path'))
                analysis.result_report = result.get('report')
            else:
                analysis.status = EEGAnalysis.Status.FAILED
                analysis.result_report = (
                    f"Inference failed.\nType: {result.get('error_type')}\n"
                    f"Detail: {result.get('error')}"
                )
                logger.error('EEG inference failed: analysis_id=%s type=%s err=%s',
                             analysis.pk, result.get('error_type'), result.get('error'))
            analysis.save()

        serializer = EEGAnalysisSerializer(analysis, context={'request': request})
        http_status = status.HTTP_201_CREATED if result.get('status') == 'success' else status.HTTP_202_ACCEPTED
        return Response(serializer.data, status=http_status)


class EEGListView(generics.ListAPIView):
    """GET /api/eeg/?patient_id=<id> — doctor-scoped list."""

    serializer_class = EEGAnalysisSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = scope_by_patient(self.request.user, EEGAnalysis.objects.all())
        patient_id = self.request.query_params.get('patient_id')
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        return qs.order_by('-created_at')


class EEGDetailView(generics.RetrieveDestroyAPIView):
    """GET / DELETE /api/eeg/{id}/"""

    serializer_class = EEGAnalysisSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return scope_by_patient(self.request.user, EEGAnalysis.objects.all())

    def perform_destroy(self, instance):
        try:
            if instance.file:
                instance.file.delete(save=False)
        except Exception as e:
            logger.warning('Could not delete EEG upload: %s', e)
        if instance.result_plot_path:
            absolute = os.path.join(settings.MEDIA_ROOT, instance.result_plot_path)
            try:
                if os.path.exists(absolute):
                    os.remove(absolute)
            except OSError as e:
                logger.warning('Could not delete EEG artifact %s: %s', absolute, e)
        instance.delete()


class EEGExplainView(APIView):
    """POST /api/eeg/{id}/explain/ — on-demand SHAP saliency for one EEG analysis.

    Mirrors ECGExplainView / MRIExplainView. Doctor-isolated: the record is resolved
    from the requesting user's scoped queryset, so another doctor's id returns 404
    (never an authorization leak). Optional body ``{target_class}`` attributes one of
    the 6 IIIC classes (canonical name or index); an unknown value falls back to the
    predicted class. Runs synchronously (a few seconds for GradientShap) and returns a
    signed, time-limited URL for the generated SHAP plot. Never 500s on bad input —
    failures come back as the structured ``{status:'failed'}`` envelope with 502.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        analysis = get_object_or_404(
            scope_by_patient(request.user, EEGAnalysis.objects.all()), pk=pk)
        if not analysis.file:
            return Response({'detail': 'No signal on this analysis.'},
                            status=status.HTTP_400_BAD_REQUEST)
        target_class = request.data.get('target_class')
        result = run_inference_with_timeout(
            lambda p: explain_eeg(p, target_class), analysis.file.path,
            timeout_seconds=300)
        if result.get('status') != 'success':
            return Response(result, status=status.HTTP_502_BAD_GATEWAY)
        # Return a signed, time-limited URL for the generated overlay (never raw /media/).
        result['shap_path'] = signed_media_url(request, _relative_to_media(result.get('shap_path')))
        return Response(result, status=status.HTTP_200_OK)
