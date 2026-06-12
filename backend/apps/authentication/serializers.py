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


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'},
    )

    class Meta:
        model = User
        fields = ('id', 'email', 'password', 'full_name', 'role')
        # `role` is read-only: it is returned in the response but can NEVER be
        # set by the client. Public self-registration always creates a DOCTOR
        # (the model default). Without this, an anonymous POST with
        # {"role": "admin"} would self-elevate to admin — a mass-assignment
        # privilege-escalation flaw, since the role is embedded in the JWT.
        # Admin accounts must be created out-of-band (createsuperuser / admin).
        read_only_fields = ('role',)

    def create(self, validated_data):
        # Defence in depth: even if a future edit makes `role` writable, force
        # the safe default here so this endpoint can never mint a non-doctor.
        validated_data.pop('role', None)
        return User.objects.create_user(role=User.Role.DOCTOR, **validated_data)


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
