from django.urls import path

from .views import EEGDetailView, EEGExplainView, EEGListView, EEGUploadView

app_name = 'eeg'

urlpatterns = [
    path('upload/', EEGUploadView.as_view(), name='upload'),
    path('', EEGListView.as_view(), name='list'),
    path('<int:pk>/', EEGDetailView.as_view(), name='detail'),
    path('<int:pk>/explain/', EEGExplainView.as_view(), name='explain'),
]
