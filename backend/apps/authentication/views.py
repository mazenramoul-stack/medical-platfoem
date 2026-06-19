from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from django.contrib.auth import get_user_model

from .permissions import IsTechnician
from .serializers import (
    DoctorSerializer,
    EmailTokenObtainPairSerializer,
    UserRegistrationSerializer,
    UserSerializer,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]
    throttle_scope = 'auth_register'

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                'user': UserSerializer(user).data,
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """POST {email, password} → {access, refresh, user}."""
    serializer_class = EmailTokenObtainPairSerializer
    permission_classes = [AllowAny]
    throttle_scope = 'auth_login'


class RefreshView(TokenRefreshView):
    """POST {refresh} → {access}. Subclassed only to attach a throttle scope."""
    throttle_scope = 'auth_refresh'


class LogoutView(APIView):
    """POST {refresh} → blacklist the refresh token (server-side revocation)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get('refresh')
        if not refresh:
            return Response({'detail': 'refresh token is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            return Response({'detail': 'Token is invalid or already blacklisted.'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class DoctorListView(generics.ListAPIView):
    """GET /api/auth/doctors/ — technician-only list of doctors for assignment.

    Doctors do not get the user directory; only a technician (who must pick which
    doctor(s) a patient goes to) can read this.
    """

    serializer_class = DoctorSerializer
    permission_classes = [IsTechnician]
    pagination_class = None

    def get_queryset(self):
        return User.objects.filter(role=User.Role.DOCTOR).order_by('full_name')
