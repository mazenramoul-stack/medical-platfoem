from django.urls import path

from .views import (
    ReportDetailView,
    ReportDownloadView,
    ReportGenerateView,
    ReportListView,
)

app_name = 'reports'

urlpatterns = [
    path('generate/', ReportGenerateView.as_view(), name='generate'),
    path('', ReportListView.as_view(), name='list'),
    path('<int:pk>/', ReportDetailView.as_view(), name='detail'),
    path('<int:pk>/download/', ReportDownloadView.as_view(), name='download'),
]
