from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Read-only representation returned by /me/ and embedded in auth responses."""

    class Meta:
        model = User
        fields = ('id', 'email', 'full_name', 'role', 'is_active', 'created_at')
        read_only_fields = ('id', 'email', 'is_active', 'created_at')


class DoctorSerializer(serializers.ModelSerializer):
    """Minimal doctor identity for the technician's assignment picker."""

    class Meta:
        model = User
        fields = ('id', 'full_name', 'email')


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'},
    )
    # Self-registration may pick one of the two self-service roles. The
    # ChoiceField rejects anything outside {doctor, technician} with a 400, so a
    # client can no longer invent a privileged value. It defaults to DOCTOR when
    # omitted. Note this is ONLY the app role embedded in the JWT — it can never
    # set Django's is_staff / is_superuser (those are not serializer fields and
    # are stripped in create(); they stay server-controlled via create_superuser).
    role = serializers.ChoiceField(
        choices=[User.Role.DOCTOR, User.Role.TECHNICIAN],
        required=False,
        default=User.Role.DOCTOR,
    )

    class Meta:
        model = User
        fields = ('id', 'email', 'password', 'full_name', 'role')

    def create(self, validated_data):
        role = validated_data.pop('role', User.Role.DOCTOR)
        # Defence in depth: even though they are not declared fields, make sure a
        # malicious payload can never carry staff/superuser into create_user.
        validated_data.pop('is_staff', None)
        validated_data.pop('is_superuser', None)
        return User.objects.create_user(role=role, **validated_data)


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """SimpleJWT token serializer that embeds user identity in the access token
    and returns the serialized user alongside the access/refresh pair."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email'] = user.email
        token['role'] = user.role
        token['full_name'] = user.full_name
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        return data
