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
    from .service import EnhancedAIService
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
    """SIMPLE WORKING AI CHAT ENDPOINT - Use this to test"""
    try:
        if request.method != 'POST':
            return JsonResponse({
                'success': False,
                'error': 'Method not allowed',
                'response': 'Please use POST method'
            }, status=405)
        
        # Parse request
        try:
            data = json.loads(request.body.decode('utf-8'))
        except:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON',
                'response': 'Please send valid JSON'
            }, status=400)
        
        message = data.get('message', data.get('query', '')).strip()
        if not message:
            return JsonResponse({
                'success': False,
                'error': 'Empty message',
                'response': 'Please provide a message'
            }, status=400)
        
        # Simple AI logic that always works
        msg_lower = message.lower()
        
        # Greetings
        greetings = {
            'hi': "Hello! 👋 I'm SokHub AI Assistant. How can I help you today?",
            'hello': "Greetings! Welcome to SokHub Marketplace.",
            'bonjour': "Bonjour! Je suis l'assistant AI de SokHub.",
            'bjr': "Bonjour! Comment puis-je vous aider sur SokHub?",
            'muraho': "Muraho! Ndi umuyobozi wa SokHub AI.",
            'habari': "Habari! Mimi ni msaidizi wa SokHub.",
            'hey': "Hey there! 🤖 Ready to explore SokHub?"
        }
        
        # Check exact matches first
        if msg_lower in greetings:
            return JsonResponse({
                'success': True,
                'response': greetings[msg_lower],
                'intent': 'greeting'
            })
        
        # Check partial matches
        for greet_key, greet_response in greetings.items():
            if greet_key in msg_lower:
                return JsonResponse({
                    'success': True,
                    'response': greet_response,
                    'intent': 'greeting'
                })
        
        # SokHub related
        if 'sokhub' in msg_lower:
            return JsonResponse({
                'success': True,
                'response': "🚀 **Welcome to SokHub!**\n\nSokHub is Rwanda's leading e-commerce marketplace where you can buy and sell products easily.\n\nI can help you with:\n• Finding products 🛍️\n• Selling items 🏪\n• Business analytics 📊\n• Order tracking 📦\n\nWhat would you like to do?",
                'intent': 'platform_info'
            })
        
        # Product search
        product_words = ['product', 'buy', 'price', 'cost', 'shop', 'store', 'item', 'thing']
        if any(word in msg_lower for word in product_words):
            return JsonResponse({
                'success': True,
                'response': "🛍️ **Product Search**\n\nI can help you find products! Try asking:\n• 'Show me phones'\n• 'Laptops under 200,000'\n• 'Shoes for men'\n• 'Price of Samsung TV'\n\nWhat are you looking for?",
                'intent': 'shopping'
            })
        
        # Vendor queries
        if any(word in msg_lower for word in ['vendor', 'sell', 'business', 'report', 'sales']):
            return JsonResponse({
                'success': True,
                'response': "🏪 **Vendor Support**\n\nFor business owners, I can help with:\n• Sales reports 📊\n• Order management 📦\n• Stock tracking 📈\n• Business growth tips 💡\n\nAre you a vendor looking for assistance?",
                'intent': 'vendor_support'
            })
        
        # Default response
        username = request.user.username if request.user.is_authenticated else "there"
        return JsonResponse({
            'success': True,
            'response': f"🤖 **SokHub AI Assistant**\n\nHi {username}! I understand you mentioned: '{message}'.\n\nI'm here to help you with everything related to SokHub marketplace - shopping, selling, or business inquiries!\n\nTry asking me:\n• 'What is SokHub?'\n• 'Find me products'\n• 'Help with my business'\n• 'Contact a vendor'",
            'intent': 'general'
        })
        
    except Exception as e:
        print(f"Error in ai_simple_chat: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'success': True,
            'response': "Hello! I'm SokHub AI Assistant. I can help you buy or sell products on our marketplace. How can I assist you today?",
            'intent': 'greeting'
        })

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
def chat_send(request):
    """Send a message in chat - FIXED VERSION"""
    try:
        if request.method != 'POST':
            return JsonResponse({
                'success': False,
                'error': 'Method not allowed',
                'response': 'Please use POST method'
            }, status=405)
        
        # Parse request
        try:
            data = json.loads(request.body.decode('utf-8'))
        except:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON',
                'response': 'Please send valid JSON'
            }, status=400)
        
        message = data.get('message', '').strip()
        session_id = data.get('session_id', '')
        
        if not message:
            return JsonResponse({
                'success': False,
                'error': 'Empty message',
                'response': 'Please provide a message'
            }, status=400)
        
        user = request.user if request.user.is_authenticated else None
        
        # SIMPLE RESPONSE LOGIC (Fallback if EnhancedAIService fails)
        def get_simple_response(user_message):
            msg_lower = user_message.lower()
            
            # Greetings
            if any(word in msg_lower for word in ['hi', 'hello', 'hey', 'bonjour', 'muraho']):
                username = user.username if user else "there"
                return {
                    'response': f"Hello {username}! 👋 I'm SokHub AI. How can I help you today?",
                    'intent': 'greeting',
                    'metadata': {'confidence': 1.0, 'language': 'en'}
                }
            
            # SokHub
            if 'sokhub' in msg_lower:
                return {
                    'response': "🚀 SokHub is Rwanda's e-commerce marketplace! Buy and sell products easily.",
                    'intent': 'platform_info',
                    'metadata': {'confidence': 1.0, 'language': 'en'}
                }
            
            # Products
            if any(word in msg_lower for word in ['product', 'buy', 'price', 'shop']):
                return {
                    'response': "🛍️ Looking for products? I can help! Try asking for specific items.",
                    'intent': 'shopping',
                    'metadata': {'confidence': 0.9, 'language': 'en'}
                }
            
            # Default
            return {
                'response': f"I understand you're asking about '{user_message}'. I'm SokHub AI, here to help!",
                'intent': 'general',
                'metadata': {'confidence': 0.8, 'language': 'en'}
            }
        
        # Try to use EnhancedAIService if available
        ai_response = None
        if HAS_ENHANCED_AI:
            try:
                # Prepare parameters for EnhancedAIService
                session_context = {}
                conversation_history = []
                
                # Try to get session if chat service is available
                if HAS_CHAT_SERVICE and HAS_CHAT_MODELS and session_id:
                    try:
                        session = chat_service.chat_service.get_or_create_session(user, session_id)
                        session_context = session.context
                        conversation_history = chat_service.chat_service.get_conversation_history(session)
                        
                        # Add user message to session
                        chat_service.chat_service.add_message(
                            session=session,
                            role='user',
                            content=message,
                            metadata={'timestamp': datetime.now().isoformat()}
                        )
                    except Exception as e:
                        print(f"Chat session error: {e}")
                        # Continue without session
                        pass
                
                # Process with EnhancedAIService
                ai_response = EnhancedAIService.process_chat_message(
                    message=message,
                    user=user,
                    user_id=user.id if user else None,
                    session_context=session_context,
                    conversation_history=conversation_history
                )
                
                # Add AI response to session if available
                if HAS_CHAT_SERVICE and HAS_CHAT_MODELS and session_id and 'session' in locals():
                    chat_service.chat_service.add_message(
                        session=session,
                        role='assistant',
                        content=ai_response['response'],
                        metadata=ai_response.get('metadata', {})
                    )
                    
            except Exception as e:
                print(f"EnhancedAIService error: {e}")
                traceback.print_exc()
                ai_response = get_simple_response(message)
        else:
            # Use simple response
            ai_response = get_simple_response(message)
        
        # Return response
        return JsonResponse({
            'success': True,
            'session_id': session_id,
            'response': ai_response.get('response', ''),
            'message_id': f"msg_{datetime.now().timestamp()}",
            'context': {},
            'intent': ai_response.get('intent', 'general')
        })
        
    except Exception as e:
        print(f"Error in chat_send: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e),
            'response': 'Sorry, I encountered an error processing your message.'
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