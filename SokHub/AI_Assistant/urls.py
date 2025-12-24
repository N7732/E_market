# urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Main AI endpoints
    path('api/ai/chat/', views.ai_simple_chat, name='ai_simple_chat'),  # USE THIS FIRST
    path('api/ai/assistant/', views.chat_send, name='ai_assistant'),
    
    # Chat session management
    path('api/ai/chat/start/', views.chat_start, name='chat_start'),
    path('api/ai/chat/history/', views.chat_history, name='chat_history'),
    path('api/ai/chat/stream/', views.chat_stream, name='chat_stream'),
    
    # Voice features (optional)
    path('api/ai/voice/', views.voice_input, name='voice_input'),
    path('api/ai/tts/', views.text_to_speech, name='text_to_speech'),
    path('api/ai/voice/train/', views.train_voice_profile, name='train_voice_profile'),
    
    # Debug/test endpoints
    path('api/ai/test/', views.test_endpoint, name='ai_test'),
    path('api/ai/health/', views.health_check, name='ai_health'),
    
    # UI
    path('ai-assistant/', views.ai_assistant, name='ai_assistant_ui'),
]