from rest_framework import serializers

from apps.authentication.models import User

from .models import Patient, PatientAssignment


class PatientSerializer(serializers.ModelSerializer):
    # Read: the doctors this patient is assigned to.
    doctors = serializers.SerializerMethodField()
    # Write: ids of doctors to assign. Honored ONLY for technicians (a doctor is
    # auto-assigned to themselves and may not assign others — anti-escalation).
    doctor_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False,
    )
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by_name = serializers.CharField(
        source='created_by.full_name', read_only=True, default=None)

    class Meta:
        model = Patient
        fields = (
            'id',
            'full_name',
            'age',
            'gender',
            'medical_history',
            'doctors',
            'doctor_ids',
            'created_by',
            'created_by_name',
            'created_at',
        )
        read_only_fields = ('id', 'doctors', 'created_by', 'created_by_name', 'created_at')

    def get_doctors(self, obj):
        return [
            {'id': a.doctor_id, 'full_name': a.doctor.full_name}
            for a in obj.assignments.select_related('doctor').all()
        ]

    def validate_doctor_ids(self, value):
        # Only a technician may choose which doctors a patient is assigned to.
        request = self.context.get('request')
        actor = getattr(request, 'user', None)
        if getattr(actor, 'role', None) != User.Role.TECHNICIAN:
            raise serializers.ValidationError('Only technicians may assign doctors.')
        ids = list(dict.fromkeys(value))  # de-dupe, keep order
        valid = set(
            User.objects.filter(id__in=ids, role=User.Role.DOCTOR).values_list('id', flat=True)
        )
        missing = [i for i in ids if i not in valid]
        if missing:
            raise serializers.ValidationError(f'Not valid doctor ids: {missing}.')
        return ids

    def create(self, validated_data):
        actor = self.context['request'].user
        doctor_ids = validated_data.pop('doctor_ids', None)
        patient = Patient.objects.create(created_by=actor, **validated_data)
        if getattr(actor, 'role', None) == User.Role.TECHNICIAN:
            target_ids = doctor_ids or []
        else:
            # A doctor self-registering a patient is auto-assigned to themselves.
            target_ids = [actor.id]
        self._assign(patient, target_ids, actor)
        return patient

    def update(self, instance, validated_data):
        actor = self.context['request'].user
        doctor_ids = validated_data.pop('doctor_ids', None)
        patient = super().update(instance, validated_data)
        # Reassignment is technician-only; validate_doctor_ids already rejected a
        # doctor that tried to send doctor_ids, so this is belt-and-suspenders.
        if doctor_ids is not None and getattr(actor, 'role', None) == User.Role.TECHNICIAN:
            self._assign(patient, doctor_ids, actor, replace=True)
        return patient

    @staticmethod
    def _assign(patient, doctor_ids, actor, replace=False):
        target = set(doctor_ids)
        if replace:
            patient.assignments.exclude(doctor_id__in=target).delete()
        existing = set(patient.assignments.values_list('doctor_id', flat=True))
        for doctor_id in target:
            if doctor_id not in existing:
                PatientAssignment.objects.create(
                    patient=patient, doctor_id=doctor_id, assigned_by=actor)
