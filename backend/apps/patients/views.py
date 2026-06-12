from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.ecg.serializers import ECGAnalysisSerializer
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
        patient = self.get_object()
        mri_qs = patient.mri_analyses.all()
        ecg_qs = patient.ecg_analyses.all()
        return Response({
            'patient_id': patient.pk,
            'patient_name': patient.full_name,
            'mri_analyses': MRIAnalysisSerializer(
                mri_qs, many=True, context={'request': request}
            ).data,
            'ecg_analyses': ECGAnalysisSerializer(
                ecg_qs, many=True, context={'request': request}
            ).data,
        })
