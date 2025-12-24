# security.py - Add AI-specific permissions
from django.contrib.auth import get_user_model

def get_user():
    return get_user_model()

class AIAssistantPermissions:
    @staticmethod
    def can_access_client_features(user):
        # Use user_type field from customer.User model
        return user.is_authenticated and getattr(user, 'user_type', '') == 'customer'
    
    @staticmethod
    def can_access_vendor_features(user):
        return user.is_authenticated and getattr(user, 'user_type', '') == 'vendor'
    
    @staticmethod
    def can_access_ai_assistant(user):
        return user.is_authenticated

def validate_request(request):
    """Simple request validation"""
    return True