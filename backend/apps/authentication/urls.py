from django.urls import path

from .views import (
    DoctorListView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    RegisterView,
)

app_name = 'authentication'

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('refresh/', RefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', MeView.as_view(), name='me'),
    path('doctors/', DoctorListView.as_view(), name='doctors'),
]
