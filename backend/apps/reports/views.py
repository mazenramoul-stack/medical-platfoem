"""REST endpoints for combined MRI+ECG PDF reports.

Routes (mounted at /api/reports/):
    POST    /generate/         build + persist a new report from existing analyses
    GET     /                  list (optionally filtered by ?patient_id=X)
    GET     /{id}/             retrieve one
    GET     /{id}/download/    stream the PDF as an attachment
    DELETE  /{id}/             delete record + PDF on disk
"""

import io
import logging
import os

from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ecg.models import ECGAnalysis
from apps.echo.models import EchoAnalysis
from apps.eeg.models import EEGAnalysis
from apps.mri.models import MRIAnalysis
from apps.patients.models import Patient

from .models import Report
from .pdf_generator import MedicalReportGenerator
from .serializers import ReportSerializer

logger = logging.getLogger(__name__)


class ReportGenerateView(APIView):
    """POST /api/reports/generate/  body: {patient_id, mri_analysis_id?, ecg_analysis_id?}"""

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        patient_id = request.data.get('patient_id')
        mri_id = request.data.get('mri_analysis_id')
        ecg_id = request.data.get('ecg_analysis_id')
        echo_id = request.data.get('echo_analysis_id')
        eeg_id = request.data.get('eeg_analysis_id')

        if not patient_id:
            return Response({'detail': 'patient_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not mri_id and not ecg_id and not echo_id and not eeg_id:
            return Response(
                {'detail': 'At least one of mri_analysis_id, ecg_analysis_id, echo_analysis_id or eeg_analysis_id is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        patient = get_object_or_404(Patient, pk=patient_id, doctor=request.user)

        mri = None
        if mri_id:
            mri = get_object_or_404(MRIAnalysis, pk=mri_id, patient=patient)
            if mri.status != MRIAnalysis.Status.COMPLETED:
                return Response(
                    {'detail': f'MRI analysis #{mri.pk} is not completed (status={mri.status}).'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        ecg = None
        if ecg_id:
            ecg = get_object_or_404(ECGAnalysis, pk=ecg_id, patient=patient)
            if ecg.status != ECGAnalysis.Status.COMPLETED:
                return Response(
                    {'detail': f'ECG analysis #{ecg.pk} is not completed (status={ecg.status}).'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        echo = None
        if echo_id:
            echo = get_object_or_404(EchoAnalysis, pk=echo_id, patient=patient)
            if echo.status != EchoAnalysis.Status.COMPLETED:
                return Response(
                    {'detail': f'Echo analysis #{echo.pk} is not completed (status={echo.status}).'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        eeg = None
        if eeg_id:
            eeg = get_object_or_404(EEGAnalysis, pk=eeg_id, patient=patient)
            if eeg.status != EEGAnalysis.Status.COMPLETED:
                return Response(
                    {'detail': f'EEG analysis #{eeg.pk} is not completed (status={eeg.status}).'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ---- build the PDF in memory -----------------------------------
        logger.info("Report.generate: patient_id=%s mri=%s ecg=%s echo=%s eeg=%s", patient.pk,
                    mri.pk if mri else None, ecg.pk if ecg else None,
                    echo.pk if echo else None, eeg.pk if eeg else None)
        try:
            generator = MedicalReportGenerator(patient=patient, mri_analysis=mri,
                                               ecg_analysis=ecg, echo_analysis=echo,
                                               eeg_analysis=eeg, doctor=request.user)
            buf = io.BytesIO()
            generator.build(buf)
            pdf_bytes = buf.getvalue()
        except Exception as e:
            logger.exception("Report generation failed")
            return Response(
                {'detail': 'Report generation failed.', 'error': str(e), 'error_type': type(e).__name__},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # ---- persist record + file -------------------------------------
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        filename = f'{patient.pk}_{timestamp}.pdf'

        with transaction.atomic():
            report = Report.objects.create(patient=patient, mri_analysis=mri, ecg_analysis=ecg,
                                           echo_analysis=echo, eeg_analysis=eeg)
            report.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)

        logger.info("Report saved: id=%s file=%s size=%d", report.pk, report.pdf_file.name, len(pdf_bytes))
        serializer = ReportSerializer(report, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ReportListView(generics.ListAPIView):
    """GET /api/reports/?patient_id=<id>"""

    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Report.objects.filter(patient__doctor=self.request.user)
        patient_id = self.request.query_params.get('patient_id')
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        return qs.order_by('-created_at')


class ReportDetailView(generics.RetrieveDestroyAPIView):
    """GET / DELETE /api/reports/{id}/"""

    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Report.objects.filter(patient__doctor=self.request.user)

    def perform_destroy(self, instance):
        try:
            if instance.pdf_file:
                instance.pdf_file.delete(save=False)
        except Exception as e:
            logger.warning("Could not delete PDF: %s", e)
        instance.delete()


class ReportDownloadView(APIView):
    """GET /api/reports/{id}/download/ → stream the PDF as an attachment."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        report = get_object_or_404(Report, pk=pk, patient__doctor=request.user)
        if not report.pdf_file or not os.path.exists(report.pdf_file.path):
            raise Http404('PDF file is not available on disk.')

        download_name = (
            f'medical_report_patient{report.patient_id}_'
            f'{report.created_at.strftime("%Y%m%d_%H%M%S")}.pdf'
        )
        response = FileResponse(
            open(report.pdf_file.path, 'rb'),
            as_attachment=True,
            filename=download_name,
            content_type='application/pdf',
        )
        return response
