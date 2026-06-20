from django.urls import path

from .views import ECGDetailView, ECGExplainView, ECGListView, ECGUploadView

app_name = 'ecg'

urlpatterns = [
    path('upload/', ECGUploadView.as_view(), name='upload'),
    path('', ECGListView.as_view(), name='list'),
    path('<int:pk>/', ECGDetailView.as_view(), name='detail'),
    path('<int:pk>/explain/', ECGExplainView.as_view(), name='explain'),
]
