# security.py - Add AI-specific permissions
from django.contrib.auth.models import User

class AIAssistantPermissions:
    @staticmethod
    def can_access_client_features(user):
        return user.groups.filter(name='Client').exists()
    
    @staticmethod
    def can_access_vendor_features(user):
        return user.groups.filter(name='Vendor').exists()
    
    @staticmethod
    def can_access_ai_assistant(user):
        return user.is_authenticated and (user.groups.filter(name__in=['Client', 'Vendor']).exists())