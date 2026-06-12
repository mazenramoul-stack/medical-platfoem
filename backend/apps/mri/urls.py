from django.urls import path

from .views import MRIDetailView, MRIListView, MRIUploadView

app_name = 'mri'

urlpatterns = [
    path('upload/', MRIUploadView.as_view(), name='upload'),
    path('', MRIListView.as_view(), name='list'),
    path('<int:pk>/', MRIDetailView.as_view(), name='detail'),
]
