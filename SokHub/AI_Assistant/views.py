from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
import json

from SokHub.AI_Assistant import chat_service

from .service import AIClientService, AIVendorService, AIAssistantPermissions
from .security import validate_request

@csrf_exempt
@login_required
def ai_assistant(request):
    """Main AI assistant endpoint"""
    if not AIAssistantPermissions.can_access_ai_assistant(request.user):
        return JsonResponse({'error': 'Unauthorized access'}, status=403)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_query = data.get('query', '')
            user_type = data.get('user_type', 'client')  # 'client' or 'vendor'
            
            # Route query based on user type
            if user_type == 'client':
                response = handle_client_query(request.user, user_query, data)
            elif user_type == 'vendor':
                response = handle_vendor_query(request.user, user_query, data)
            else:
                response = {'error': 'Invalid user type'}
            
            return JsonResponse(response)
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

def handle_client_query(user, query, data):
    """Handle client queries"""
    if not AIAssistantPermissions.can_access_client_features(user):
        return {'error': 'Client features not accessible'}
    
    # Simple intent detection (can be enhanced with ML/NLP)
    query_lower = query.lower()
    
    if any(word in query_lower for word in ['find', 'search', 'look', 'product']):
        location = data.get('location')  # Should be {'lat': x, 'lng': y}
        user_loc = (location['lat'], location['lng']) if location else None
        
        products = AIClientService.find_products_by_wish(query, user_loc)
        
        return {
            'intent': 'product_search',
            'query': query,
            'results': [
                {
                    'id': p.id,
                    'name': p.name,
                    'store': p.store.name if p.store else None,
                    'price': str(p.price),
                    'distance_km': getattr(p, 'distance', None)
                }
                for p in products[:10]  # Limit to top 10
            ]
        }
    
    elif any(word in query_lower for word in ['near', 'nearby', 'store', 'shop']):
        location = data.get('location')
        if location:
            user_loc = (location['lat'], location['lng'])
            stores = AIClientService.find_nearby_stores(user_loc)
            
            return {
                'intent': 'store_search',
                'query': query,
                'nearby_stores': [
                    {
                        'id': s.id,
                        'name': s.name,
                        'address': s.address,
                        'distance_km': s.distance,
                        'open_hours': s.open_hours
                    }
                    for s in stores
                ]
            }
    
    return {
        'intent': 'general',
        'response': f"I understand you're asking: '{query}'. For better assistance, please specify if you're looking for products or stores."
    }

def handle_vendor_query(user, query, data):
    """Handle vendor queries"""
    if not AIAssistantPermissions.can_access_vendor_features(user):
        return {'error': 'Vendor features not accessible'}
    
    query_lower = query.lower()
    
    # Get vendor ID from user
    vendor = vendor.objects.filter(user=user).first()
    if not vendor:
        return {'error': 'Vendor profile not found'}
    
    if any(word in query_lower for word in ['report', 'analysis', 'performance', 'sales']):
        period = 'monthly'
        if 'daily' in query_lower:
            period = 'daily'
        elif 'weekly' in query_lower:
            period = 'weekly'
        
        report = AIVendorService.generate_business_report(vendor.id, period)
        
        return {
            'intent': 'business_report',
            'period': period,
            'report': report
        }
    
    elif any(word in query_lower for word in ['distance', 'delivery', 'route', 'how far']):
        location = data.get('client_location')
        if location:
            client_loc = (location['lat'], location['lng'])
            distance_info = AIVendorService.calculate_delivery_distance(vendor.id, client_loc)
            
            return {
                'intent': 'delivery_distance',
                'distance_info': distance_info
            }
    
    return {
        'intent': 'general',
        'response': f"As a vendor, I can help you with business reports and delivery information. Please ask about your sales performance or delivery distances."
    }
# views.py - Add chat endpoints
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
@csrf_exempt
def chat_start(request):
    """Start a new chat session"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    # Get context from request
    context = json.loads(request.body).get('context', {})
    
    # Create session
    session = chat_service.create_chat_session(request.user, context)
    
    # Get initial messages
    messages = chat_service.get_conversation_history(session)
    
    return JsonResponse({
        'session_id': session.session_id,
        'messages': messages,
        'context': session.context
    })

@csrf_exempt
def chat_send(request):
    """Send a message in chat"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    data = json.loads(request.body)
    message = data.get('message', '')
    session_id = data.get('session_id')
    
    # Get or create session
    session = chat_service.get_or_create_session(request.user, session_id)
    
    # Add user message
    user_message = chat_service.add_message(
        session=session,
        role='user',
        content=message,
        metadata={'timestamp': datetime.now().isoformat()}
    )
    
    # Process with AI
    ai_response = EnhancedAIService.process_chat_message(
        message=message,
        user=request.user,
        session_context=session.context,
        conversation_history=chat_service.get_conversation_history(session)
    )
    
    # Add AI response
    assistant_message = chat_service.add_message(
        session=session,
        role='assistant',
        content=ai_response['response'],
        metadata=ai_response.get('metadata', {})
    )
    
    # Update context if needed
    if ai_response.get('context_updates'):
        chat_service.update_conversation_context(
            session=session,
            updates=ai_response['context_updates']
        )
    
    # Store memories if any
    if ai_response.get('memories'):
        for key, value in ai_response['memories'].items():
            chat_service.store_conversation_memory(
                user=request.user,
                key=key,
                value=value,
                confidence=0.9
            )
    
    return JsonResponse({
        'session_id': session.session_id,
        'response': ai_response['response'],
        'message_id': assistant_message.id,
        'context': session.context
    })

@csrf_exempt
def chat_history(request):
    """Get chat history"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    session_id = request.GET.get('session_id')
    limit = int(request.GET.get('limit', 50))
    
    if session_id:
        try:
            session = ChatSession.objects.get(
                session_id=session_id,
                user=request.user
            )
            messages = chat_service.get_conversation_history(session, limit)
        except ChatSession.DoesNotExist:
            return JsonResponse({'error': 'Session not found'}, status=404)
    else:
        # Get all sessions
        sessions = ChatSession.objects.filter(
            user=request.user
        ).order_by('-updated_at')[:10]
        
        sessions_data = []
        for session in sessions:
            sessions_data.append({
                'session_id': session.session_id,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'is_active': session.is_active,
                'summary': chat_service.generate_conversation_summary(session)
            })
        
        return JsonResponse({
            'sessions': sessions_data
        })
    
    return JsonResponse({
        'session_id': session_id,
        'messages': messages,
        'context': session.context if session else {}
    })

@csrf_exempt
def chat_stream(request):
    """Stream chat responses (for real-time updates)"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    def event_stream():
        """Generator for Server-Sent Events"""
        data = json.loads(request.body)
        message = data.get('message', '')
        session_id = data.get('session_id')
        
        # Get session
        session = chat_service.get_or_create_session(request.user, session_id)
        
        # Add user message
        chat_service.add_message(
            session=session,
            role='user',
            content=message
        )
        
        # Stream AI response
        response_generator = EnhancedAIService.stream_chat_response(
            message=message,
            user=request.user,
            session=session
        )
        
        for chunk in response_generator:
            yield f"data: {json.dumps(chunk)}\n\n"
        
        yield "data: [DONE]\n\n"
    
    return StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )

# views.py - Add voice endpoints
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
import base64
import json
from .voice_service import voice_service

@csrf_exempt
def voice_input(request):
    """Handle voice input"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    if request.method == 'POST':
        # Get audio file
        audio_file = request.FILES.get('audio')
        
        if not audio_file:
            return JsonResponse({'error': 'No audio file provided'}, status=400)
        
        # Process voice command
        result = voice_service.process_voice_command(
            audio_file, 
            request.user.id
        )
        
        # Save to database
        VoiceCommand.objects.create(
            user=request.user,
            session_id=request.GET.get('session_id', ''),
            audio_file=audio_file,
            transcribed_text=result.get('text', ''),
            confidence=result.get('confidence', 0),
            intent=result.get('intent', 'general'),
            response_text=result.get('response_text', ''),
            response_audio=ContentFile(
                base64.b64decode(result.get('response_audio', '')),
                name='response.mp3'
            ) if result.get('response_audio') else None
        )
        
        return JsonResponse(result)

@csrf_exempt
def text_to_speech(request):
    """Convert text to speech"""
    data = json.loads(request.body)
    text = data.get('text', '')
    voice_type = data.get('voice', 'default')
    speed = float(data.get('speed', 1.0))
    
    # Generate speech
    audio_bytes, content_type = voice_service.text_to_speech(
        text, voice_type, speed
    )
    
    if not audio_bytes:
        return JsonResponse({'error': 'Failed to generate speech'}, status=500)
    
    # Return audio
    response = HttpResponse(audio_bytes, content_type=content_type)
    response['Content-Disposition'] = 'inline; filename="speech.mp3"'
    return response

@csrf_exempt
def train_voice_profile(request):
    """Train voice profile for user"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    audio_files = request.FILES.getlist('audio_samples')
    
    if len(audio_files) < 3:
        return JsonResponse({
            'error': 'At least 3 audio samples required for training'
        }, status=400)
    
    # Convert files to AudioData
    audio_samples = []
    for audio_file in audio_files:
        import speech_recognition as sr
        with sr.AudioFile(audio_file) as source:
            audio = sr.Recognizer().record(source)
            audio_samples.append(audio)
    
    # Create voice profile
    voice_service.create_voice_profile(request.user.id, audio_samples)
    
    return JsonResponse({
        'success': True,
        'message': 'Voice profile trained successfully',
        'samples_used': len(audio_samples)
    })