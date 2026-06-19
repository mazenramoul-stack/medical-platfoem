from django.urls import re_path

from .views import ConvertView

app_name = 'conversion'

urlpatterns = [
    # Only the four known modalities route here; anything else 404s before the
    # view (so an unknown modality never reaches the permission/converter logic).
    re_path(r'^(?P<modality>mri|ecg|echo|eeg)/$', ConvertView.as_view(), name='convert'),
]
