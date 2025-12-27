# AI Assistant Setup Instructions

## 1. Install Dependencies
Run the following command to install the required packages:
```bash
pip install -r requirements.txt
```
(Note: You may need to install `pyaudio` manually depending on your system for voice features).

## 2. Database Migrations
Since new models were added (`ChatSession`, `ChatMessage`, `VoiceCommand`, etc.), you must update your database:
```bash
python manage.py makemigrations
python manage.py migrate
```

## 3. Frontend Integration (The Star Icon)
To add the AI Assistant star icon to your website:
1. Open your base template (e.g., `base.html`).
2. Include the widget template at the bottom of the `<body>` tag:
```django
{% include "ai_assistant/widget.html" %}
```
If your templates are configured differently, you might need to copy the content of `templates/ai_assistant/widget.html` into your base template or adjust the path.

## 4. URL Configuration
Ensure your project's main `urls.py` includes the AI Assistant URLs.
Example:
```python
from django.urls import path, include

urlpatterns = [
    # ... other paths ...
    path('', include('SokHub.AI_Assistant.urls')), # If you want /api/chat/...
    # OR
    # path('ai/', include('SokHub.AI_Assistant.urls')), # Then update widget.html to use /ai/api/chat/...
]
```

## 5. Verify API Keys (Optional)
For full functionality (Maps, Voice, Advanced AI), update `settings.py` with:
- `GOOGLE_MAPS_API_KEY`
- `OPENAI_API_KEY` (if utilizing OpenAI integration)

The system is designed to work with basic features (Mock AI / Rule-based) even without these keys.
