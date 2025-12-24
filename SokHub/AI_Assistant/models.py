# models.py - Add AI-related models
from django.db import models
from django.conf import settings

# --- Placeholders removed. We will use models from product, order, and customer apps. ---

# --- AI Assistant Models ---

class AIRequestLog(models.Model):
    """Log all AI assistant requests"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    query = models.TextField()
    query_type = models.CharField(max_length=50)  # 'client_search', 'vendor_report', etc.
    response = models.JSONField()
    timestamp = models.DateTimeField(auto_now_add=True)
    response_time = models.FloatField()  # in seconds
    
    class Meta:
        ordering = ['-timestamp']

class ChatSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    session_id = models.CharField(max_length=255, unique=True)
    context = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

class ChatMessage(models.Model):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE)
    role = models.CharField(max_length=50) # 'user', 'assistant'
    content = models.TextField()
    metadata = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['timestamp']

class ConversationMemory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key = models.CharField(max_length=255)
    value = models.TextField()
    confidence = models.FloatField(default=1.0)
    updated_at = models.DateTimeField(auto_now=True)

class VoiceCommand(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    session_id = models.CharField(max_length=255, blank=True, null=True)
    audio_file = models.FileField(upload_to='voice_commands/')
    transcribed_text = models.TextField()
    confidence = models.FloatField(default=0.0)
    intent = models.CharField(max_length=100, default='general')
    response_text = models.TextField()
    response_audio = models.FileField(upload_to='voice_responses/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class VoiceProfile(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, unique=True)
    features = models.JSONField()