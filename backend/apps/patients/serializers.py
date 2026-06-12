from rest_framework import serializers

from .models import Patient


class PatientSerializer(serializers.ModelSerializer):
    doctor = serializers.PrimaryKeyRelatedField(read_only=True)
    doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)

    class Meta:
        model = Patient
        fields = (
            'id',
            'full_name',
            'age',
            'gender',
            'medical_history',
            'doctor',
            'doctor_name',
            'created_at',
        )
        read_only_fields = ('id', 'doctor', 'doctor_name', 'created_at')
