from django.urls import path

from .views import LoginView, MeView, RefreshView, RegisterView

app_name = 'authentication'

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('refresh/', RefreshView.as_view(), name='token_refresh'),
    path('me/', MeView.as_view(), name='me'),
]
