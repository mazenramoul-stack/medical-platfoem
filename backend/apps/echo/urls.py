from django.urls import path

from .views import EchoDetailView, EchoExplainView, EchoListView, EchoUploadView

app_name = 'echo'

urlpatterns = [
    path('upload/', EchoUploadView.as_view(), name='upload'),
    path('', EchoListView.as_view(), name='list'),
    path('<int:pk>/', EchoDetailView.as_view(), name='detail'),
    path('<int:pk>/explain/', EchoExplainView.as_view(), name='explain'),
]
