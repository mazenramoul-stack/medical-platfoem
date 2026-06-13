from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.ecg.serializers import ECGAnalysisSerializer
from apps.echo.serializers import EchoAnalysisSerializer
from apps.eeg.serializers import EEGAnalysisSerializer
from apps.mri.serializers import MRIAnalysisSerializer

from .models import Patient
from .serializers import PatientSerializer


class PatientViewSet(viewsets.ModelViewSet):
    serializer_class = PatientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Patient.objects.filter(doctor=self.request.user)

    def perform_create(self, serializer):
        serializer.save(doctor=self.request.user)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        # get_object() runs through get_queryset(), so the patient is already
        # doctor-scoped; every reverse relation below inherits that scoping.
        patient = self.get_object()
        ctx = {'request': request}
        return Response({
            'patient_id': patient.pk,
            'patient_name': patient.full_name,
            'mri_analyses': MRIAnalysisSerializer(
                patient.mri_analyses.all(), many=True, context=ctx
            ).data,
            'ecg_analyses': ECGAnalysisSerializer(
                patient.ecg_analyses.all(), many=True, context=ctx
            ).data,
            'echo_analyses': EchoAnalysisSerializer(
                patient.echo_analyses.all(), many=True, context=ctx
            ).data,
            'eeg_analyses': EEGAnalysisSerializer(
                patient.eeg_analyses.all(), many=True, context=ctx
            ).data,
        })
