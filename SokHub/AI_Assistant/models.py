# models.py - Add AI-related models
from django.db import models
from django.contrib.auth.models import User

class AIRequestLog(models.Model):
    """Log all AI assistant requests"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    query = models.TextField()
    query_type = models.CharField(max_length=50)  # 'client_search', 'vendor_report', etc.
    response = models.JSONField()
    timestamp = models.DateTimeField(auto_now_add=True)
    response_time = models.FloatField()  # in seconds
    
    class Meta:
        ordering = ['-timestamp']