# admin.py - Add AI monitoring
from django.contrib import admin
from .models import AIRequestLog

@admin.register(AIRequestLog)
class AIRequestLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'query_type', 'timestamp', 'response_time']
    list_filter = ['query_type', 'timestamp']
    search_fields = ['user__username', 'query']