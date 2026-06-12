from django.contrib import admin

from .models import EEGAnalysis


@admin.register(EEGAnalysis)
class EEGAnalysisAdmin(admin.ModelAdmin):
    list_display = ('id', 'patient', 'status', 'result_dominant_pattern', 'result_harmful', 'created_at')
    list_filter = ('status', 'result_harmful')
    search_fields = ('patient__full_name',)
