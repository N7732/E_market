# views.py - FIXED VERSION
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.conf import settings
import json
from datetime import datetime
import traceback

# Try to import services with fallbacks
try:
    from . import service
    HAS_SERVICE = True
except ImportError as e:
    print(f"Service import error: {e}")
    HAS_SERVICE = False

try:
    from .service import EnhancedAIService, enhanced_ai_service
    HAS_ENHANCED_AI = True
except ImportError as e:
    print(f"EnhancedAIService import error: {e}")
    HAS_ENHANCED_AI = False

try:
    from . import chat_service
    HAS_CHAT_SERVICE = True
except ImportError as e:
    print(f"Chat service import error: {e}")
    HAS_CHAT_SERVICE = False

try:
    from .models import ChatSession
    HAS_CHAT_MODELS = True
except ImportError as e:
    print(f"Chat models import error: {e}")
    HAS_CHAT_MODELS = False

def ai_assistant(request):
    """Main view for AI Assistant UI"""
    return render(request, 'ai_assistant/index.html')

@csrf_exempt
def ai_simple_chat(request):
    """Simple chat endpoint that redirects to dynamic service"""
    # This just wraps chat_send logic or calls service directly for consistency
    return chat_send(request)

@csrf_exempt
def chat_start(request):
    """Start a new chat session - FIXED VERSION"""
    try:
        if request.method != 'POST':
            return JsonResponse({
                'success': False,
                'error': 'Method not allowed',
                'response': 'Please use POST method'
            }, status=405)
        
        # Get context from request
        try:
            data = json.loads(request.body.decode('utf-8'))
            context = data.get('context', {})
        except:
            context = {}
        
        user = request.user if request.user.is_authenticated else None
        
        # If chat service is not available, return a simple session
        if not HAS_CHAT_SERVICE or not HAS_CHAT_MODELS:
            session_id = f"simple_{datetime.now().timestamp()}"
            return JsonResponse({
                'success': True,
                'session_id': session_id,
                'messages': [{
                    'role': 'assistant',
                    'content': "👋 Hello! I'm SokHub AI Assistant. How can I help you today?",
                    'timestamp': datetime.now().isoformat()
                }],
                'context': context
            })
        
        # Create session using chat service
        try:
            session = chat_service.chat_service.create_chat_session(user, context)
            messages = chat_service.chat_service.get_conversation_history(session)
            
            return JsonResponse({
                'success': True,
                'session_id': session.session_id,
                'messages': messages,
                'context': session.context
            })
        except Exception as e:
            print(f"Chat service error: {e}")
            # Fallback
            session_id = f"fallback_{datetime.now().timestamp()}"
            return JsonResponse({
                'success': True,
                'session_id': session_id,
                'messages': [{
                    'role': 'assistant',
                    'content': "Hello! Welcome to SokHub AI Assistant!",
                    'timestamp': datetime.now().isoformat()
                }],
                'context': context
            })
        
    except Exception as e:
        print(f"Error in chat_start: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e),
            'response': 'Failed to start chat session'
        }, status=500)

@csrf_exempt
def chat_history(request):
    """Get chat history - FIXED VERSION"""
    try:
        session_id = request.GET.get('session_id')
        limit = int(request.GET.get('limit', 50))
        user = request.user if request.user.is_authenticated else None
        
        if not session_id:
            return JsonResponse({
                'success': False,
                'error': 'Session ID required',
                'response': 'Please provide a session ID'
            }, status=400)
        
        # If chat models are not available, return empty
        if not HAS_CHAT_MODELS:
            return JsonResponse({
                'success': True,
                'messages': [{
                    'role': 'assistant',
                    'content': "Welcome to SokHub AI Assistant! How can I help you?",
                    'timestamp': datetime.now().isoformat()
                }]
            })
        
        try:
            # Build query
            query = ChatSession.objects.filter(session_id=session_id)
            if user:
                query = query.filter(user=user)
            
            session = query.first()
            
            if not session:
                return JsonResponse({
                    'success': False,
                    'error': 'Session not found',
                    'response': 'Chat session not found'
                }, status=404)
            
            # Get messages
            if HAS_CHAT_SERVICE:
                messages = chat_service.chat_service.get_conversation_history(session, limit)
            else:
                # Fallback: get messages directly
                from .models import ChatMessage
                messages_query = ChatMessage.objects.filter(session=session).order_by('timestamp')[:limit]
                messages = []
                for msg in messages_query:
                    messages.append({
                        'role': msg.role,
                        'content': msg.content,
                        'timestamp': msg.timestamp.isoformat() if msg.timestamp else None
                    })
            
            return JsonResponse({
                'success': True,
                'messages': messages
            })
            
        except ChatSession.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Session not found',
                'response': 'Chat session not found'
            }, status=404)
        except Exception as e:
            print(f"Error getting chat history: {e}")
            return JsonResponse({
                'success': False,
                'error': str(e),
                'response': 'Failed to get chat history'
            }, status=500)
        
    except Exception as e:
        print(f"Error in chat_history: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'response': 'Failed to get chat history'
        }, status=500)

@csrf_exempt
def chat_stream(request):
    """Stream chat responses - SIMPLIFIED"""
    return JsonResponse({
        'success': False,
        'response': 'Streaming not yet implemented',
        'intent': 'info'
    })

@csrf_exempt
def voice_input(request):
    """Voice input endpoint - SIMPLIFIED"""
    return JsonResponse({
        'success': False,
        'response': 'Voice input not yet implemented',
        'intent': 'info'
    })

@csrf_exempt
def text_to_speech(request):
    """Text to speech endpoint - SIMPLIFIED"""
    return JsonResponse({
        'success': False,
        'response': 'Text to speech not yet implemented',
        'intent': 'info'
    })

@csrf_exempt
@login_required
def train_voice_profile(request):
    """Train voice profile - REQUIRES AUTH"""
    return JsonResponse({
        'success': False,
        'response': 'Voice profile training not yet implemented',
        'intent': 'info'
    })

# TEST ENDPOINTS FOR DEBUGGING

@csrf_exempt
def test_endpoint(request):
    """Test endpoint to check if server is working"""
    return JsonResponse({
        'success': True,
        'message': 'AI Assistant server is running',
        'timestamp': datetime.now().isoformat(),
        'user': request.user.username if request.user.is_authenticated else 'anonymous',
        'method': request.method
    })

@csrf_exempt
def health_check(request):
    """Health check endpoint"""
    services = {
        'enhanced_ai_service': HAS_ENHANCED_AI,
        'chat_service': HAS_CHAT_SERVICE,
        'chat_models': HAS_CHAT_MODELS,
        'main_service': HAS_SERVICE
    }
    
    return JsonResponse({
        'status': 'healthy',
        'service': 'AI Assistant',
        'timestamp': datetime.now().isoformat(),
        'services': services
    })

# Main Chat Endpoint using Enhanced AI Service
@csrf_exempt
def chat_send(request):
    """Enhanced chat endpoint using database-aware AI service"""
    try:
        if request.method != 'POST':
            return JsonResponse({
                'success': False,
                'error': 'Method not allowed'
            }, status=405)

        # Parse request
        try:
            data = json.loads(request.body.decode('utf-8'))
        except:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON'
            }, status=400)

        message = data.get('message', '').strip()
        session_id = data.get('session_id', '')
        language = data.get('language', 'en')

        if not message:
            return JsonResponse({
                'success': False,
                'error': 'Empty message'
            }, status=400)

        user = request.user if request.user.is_authenticated else None
        msg_lower = message.lower()
        
        # --- QUICK PRODUCT SEARCH (Inline handler) ---
        # Check for product search intent
        search_keywords = ['want', 'find', 'search', 'show', 'need', 'buy', 'get', 'looking for']
        is_product_search = any(kw in msg_lower for kw in search_keywords)
        
        if is_product_search:
            # Extract product name (remove common words)
            clean_query = msg_lower
            remove_words = ['i', 'want', 'find', 'search', 'show', 'me', 'need', 'buy', 'get', 'looking', 'for', 'to', 'the', 'a']
            for word in remove_words:
                clean_query = clean_query.replace(f' {word} ', ' ').replace(f'{word} ', ' ').replace(f' {word}', ' ').strip()
            
            if clean_query and len(clean_query) > 1:
                # Search database
                from product.models import Product
                try:
                    from django.db.models import Q
                    products = Product.objects.filter(
                        Q(name__icontains=clean_query) | 
                        Q(description__icontains=clean_query) |
                        Q(category__name__icontains=clean_query)
                    )[:5]
                    
                    if products.exists():
                        # Format results
                        msg_lines = ["🔎 **Here is what I found:**"]
                        for p in products:
                            try:
                                vendor_name = p.vendor.vendorprofile.business_name if p.vendor and hasattr(p.vendor, 'vendorprofile') else "Unknown Vendor"
                            except:
                                vendor_name = "Unknown Vendor"
                            msg_lines.append(f"• **{p.name}** - RWF {p.price:,.0f} ({vendor_name})")
                        
                        return JsonResponse({
                            'success': True,
                            'response': '\n'.join(msg_lines),
                            'intent': 'product_search',
                            'language': language,
                            'session_id': session_id
                        })
                except Exception as e:
                    print(f"Product search error: {e}")
        
        # --- Default: Use Enhanced AI Service ---
        # Get user type
        user_type = 'client'
        if user and hasattr(user, 'user_type'):
            user_type = user.user_type or 'client'

        # Process with enhanced service
        try:
            result = enhanced_ai_service.process_message(
                message=message,
                user=user,
                user_type=user_type,
                language=language,
                session_id=session_id 
            )
            
            # Prefer the normalized 'response' key produced by the service,
            # fall back to 'message' for older placeholders.
            resp_text = ''
            if isinstance(result, dict):
                resp_text = result.get('response') or result.get('message') or ''
            else:
                resp_text = str(result)

            response = {
                'success': True,
                'response': resp_text,
                'intent': result.get('type', 'general') if isinstance(result, dict) else 'general',
                'language': result.get('language', 'en') if isinstance(result, dict) else 'en',
                'data': result.get('data', {}) if isinstance(result, dict) else {},
                'session_id': session_id
            }
            
            return JsonResponse(response)
            
        except Exception as e:
            print(f"AI Service error: {e}")
            traceback.print_exc()
            # Fallback
            return JsonResponse({
                'success': True,
                'response': f"Hello! I'm SokHub AI Assistant. I understand you said: '{message}'. How can I help you today?",
                'intent': 'fallback',
                'language': 'en'
            })

    except Exception as e:
        print(f"Error in chat_send: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'response': 'Sorry, I encountered an error.'
        }, status=500)