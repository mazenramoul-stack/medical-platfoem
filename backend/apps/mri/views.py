"""MRI analysis REST endpoints.

Routes (mounted at /api/mri/):
    POST    /upload/         multipart upload + synchronous inference
    GET     /                list (filtered to requesting doctor's patients)
    GET     /{id}/           retrieve one
    DELETE  /{id}/           delete record + on-disk artifacts
"""

import functools
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

from apps.inference import analyze_mri, run_inference_with_timeout
from apps.patients.models import Patient

from .models import MRIAnalysis
from .serializers import MRIAnalysisSerializer

logger = logging.getLogger(__name__)


# File validation ----------------------------------------------------------

ALLOWED_MRI_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp',
    '.dcm', '.nii', '.nii.gz',
}
MAX_MRI_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB

# Which MRI model(s) to run. The frontend picks this from the uploaded image
# type: a plain grayscale scan -> 'classify' (Swin 4-class), a colored/masked
# image -> 'segment' (U-Net). 'full' runs both (default / backward-compatible).
VALID_MRI_MODES = {'full', 'classify', 'segment'}


def _detected_extension(filename: str) -> str:
    """Return a lowercase extension, treating '.nii.gz' as one extension."""
    lower = filename.lower()
    if lower.endswith('.nii.gz'):
        return '.nii.gz'
    return os.path.splitext(lower)[1]


def _relative_to_media(absolute_path: str) -> str | None:
    """Convert an absolute path under MEDIA_ROOT to a forward-slash relative path."""
    if not absolute_path:
        return None
    try:
        rel = os.path.relpath(absolute_path, settings.MEDIA_ROOT)
    except ValueError:
        return None
    return rel.replace('\\', '/')


# Views --------------------------------------------------------------------

class MRIUploadView(APIView):
    """POST /api/mri/upload/ — multipart {patient_id, file}."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        patient_id = request.data.get('patient_id')
        uploaded = request.FILES.get('file')
        mode = (request.data.get('mode') or 'full').strip().lower()

        # ---- 1. validate inputs ----
        if not patient_id:
            return Response({'detail': 'patient_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if uploaded is None:
            return Response({'detail': 'file is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if mode not in VALID_MRI_MODES:
            return Response(
                {'detail': f'Invalid mode: {mode}. Allowed: {sorted(VALID_MRI_MODES)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ext = _detected_extension(uploaded.name)
        if ext not in ALLOWED_MRI_EXTENSIONS:
            return Response(
                {'detail': f'Unsupported MRI file extension: {ext}. '
                           f'Allowed: {sorted(ALLOWED_MRI_EXTENSIONS)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if uploaded.size > MAX_MRI_SIZE_BYTES:
            return Response(
                {'detail': f'File too large ({uploaded.size} bytes). '
                           f'Max allowed: {MAX_MRI_SIZE_BYTES} bytes (100MB).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---- 2. resolve patient (must belong to requesting doctor) ----
        patient = get_object_or_404(Patient, pk=patient_id, doctor=request.user)

        # ---- 3. create record (processing) + persist upload ----
        with transaction.atomic():
            analysis = MRIAnalysis.objects.create(
                patient=patient,
                file=uploaded,
                status=MRIAnalysis.Status.PROCESSING,
            )
        logger.info("MRI upload received: analysis_id=%s patient_id=%s file=%s size=%d",
                    analysis.pk, patient.pk, analysis.file.name, uploaded.size)

        # ---- 4. run inference (synchronous, with 5-min timeout) ----
        # The chosen model(s) are selected by `mode`; bind it via partial since
        # run_inference_with_timeout only forwards the file path positionally.
        file_disk_path = analysis.file.path
        logger.info("MRI inference start: analysis_id=%s mode=%s", analysis.pk, mode)
        result = run_inference_with_timeout(
            functools.partial(analyze_mri, mode=mode), file_disk_path, timeout_seconds=300,
        )
        logger.info("MRI inference done: analysis_id=%s status=%s", analysis.pk, result.get('status'))

        # ---- 5. update record with results ----
        with transaction.atomic():
            if result.get('status') == 'success':
                analysis.status = MRIAnalysis.Status.COMPLETED
                analysis.model_used = ' | '.join(result.get('models_used', []))
                analysis.result_tumor_detected = result.get('tumor_detected')
                analysis.result_tumor_type = result.get('tumor_type')
                analysis.result_confidence = result.get('tumor_type_confidence')
                analysis.result_mask_path = _relative_to_media(result.get('mask_path'))
                analysis.result_overlay_path = _relative_to_media(result.get('overlay_path'))
                analysis.result_analysis_path = _relative_to_media(result.get('analysis_path'))
                analysis.result_report = result.get('report')
            else:
                analysis.status = MRIAnalysis.Status.FAILED
                analysis.result_report = (
                    f"Inference failed.\nType: {result.get('error_type')}\n"
                    f"Detail: {result.get('error')}"
                )
                logger.error("MRI inference failed: analysis_id=%s type=%s err=%s",
                             analysis.pk, result.get('error_type'), result.get('error'))
            analysis.save()

        serializer = MRIAnalysisSerializer(analysis, context={'request': request})
        http_status = status.HTTP_201_CREATED if result.get('status') == 'success' else status.HTTP_202_ACCEPTED
        return Response(serializer.data, status=http_status)


class MRIListView(generics.ListAPIView):
    """GET /api/mri/?patient_id=<id>  — list MRI analyses owned by the doctor."""

    serializer_class = MRIAnalysisSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = MRIAnalysis.objects.filter(patient__doctor=self.request.user)
        patient_id = self.request.query_params.get('patient_id')
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        return qs.order_by('-created_at')


class MRIDetailView(generics.RetrieveDestroyAPIView):
    """GET / DELETE /api/mri/{id}/"""

    serializer_class = MRIAnalysisSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return MRIAnalysis.objects.filter(patient__doctor=self.request.user)

    def perform_destroy(self, instance):
        # 1. delete uploaded file via FileField (also handles the storage backend)
        try:
            if instance.file:
                instance.file.delete(save=False)
        except Exception as e:
            logger.warning("Could not delete uploaded MRI file: %s", e)

        # 2. delete result artifacts (raw paths relative to MEDIA_ROOT)
        for rel in (instance.result_mask_path, instance.result_overlay_path, instance.result_analysis_path):
            if not rel:
                continue
            absolute = os.path.join(settings.MEDIA_ROOT, rel)
            try:
                if os.path.exists(absolute):
                    os.remove(absolute)
            except OSError as e:
                logger.warning("Could not delete MRI artifact %s: %s", absolute, e)

        instance.delete()
