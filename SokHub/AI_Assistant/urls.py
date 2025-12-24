from django.urls import path

from SokHub.SokHub import settings
from . import views

urlpatterns = [
    
    path('api/ai/assistant/', views.ai_assistant, name='ai_assistant'),
    path('api/ai/client/search/', views.client_product_search, name='client_search'),
    path('api/ai/vendor/report/', views.vendor_business_report, name='vendor_report'),

    path('api/chat/start/', views.chat_start, name='chat_start'),
    path('api/chat/send/', views.chat_send, name='chat_send'),
    path('api/chat/history/', views.chat_history, name='chat_history'),
    path('api/chat/stream/', views.chat_stream, name='chat_stream'),
    
    # Voice endpoints
    path('api/voice/input/', views.voice_input, name='voice_input'),
    path('api/voice/tts/', views.text_to_speech, name='text_to_speech'),
    path('api/voice/train/', views.train_voice_profile, name='train_voice_profile'),
    
    # Mapping endpoints
    path('api/map/distance/', views.calculate_distance, name='calculate_distance'),
    path('api/map/nearby/', views.find_nearby_places, name='find_nearby_places'),
    
    # Recommendations
    path('api/recommend/personal/', views.personal_recommendations, name='personal_recommendations'),
    path('api/recommend/train/', views.train_recommendation_model, name='train_recommendation_model'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
