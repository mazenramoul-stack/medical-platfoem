from django.contrib import admin

from .models import EchoAnalysis


@admin.register(EchoAnalysis)
class EchoAnalysisAdmin(admin.ModelAdmin):
    list_display = ('id', 'patient', 'status', 'result_ef', 'result_ef_category', 'created_at')
    list_filter = ('status',)
    search_fields = ('patient__full_name',)
