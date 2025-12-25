# service.py - COMPLETE VERSION (RAG ENHANCED WITH ANALYTICS & SMART FAILOVER & STATUS DIAGNOSIS)
import json
from datetime import datetime
from django.conf import settings
from django.db.models import Q, Sum, Count, Avg, Max, Min
from django.utils import timezone
import re
from typing import Dict, List, Optional, Tuple
import random
import urllib.request
import urllib.error

from .ai_service import AIService
from .ai_vendor_service import AIVendorService
# Import other services
from .currency_service import currency_converter
from .ml_service import ml_assistant

# Try to import models with fallbacks
try:
    from product.models import Product, Category
    from order.models import Order, OrderItem
    from customer.models import User, VendorProfile
    from .models import ChatSession
except ImportError:
    # Mock models for development
    class MockModel:
        objects = type('Manager', (), {'filter': lambda **kwargs: MockModel(),
                                       'first': lambda: None,
                                       'all': lambda: [],
                                       'count': lambda: 0,
                                       'aggregate': lambda **kwargs: {'price__max': 0, 'price__min': 0},
                                       'get': lambda **kwargs: None,
                                       'order_by': lambda *args: []})()
    Product = Category = Order = OrderItem = User = VendorProfile = ChatSession = MockModel

class EnhancedAIService:
    """Complete AI Service with DeepSeek RAG + Offline Analytics + Process Support + Diagnostics"""
    
    DEEPSEEK_API_KEY = "sk-ea580c5c98fd456f820507a4acf6d57b"
    DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
    
    # Price guide templates
    PRICE_GUIDES = {
        'low': {
            'en': "Best Budget Options: Look for products under RWF {max_price:,}.",
            'fr': "Options économiques: Cherchez des produits sous RWF {max_price:,}.",
            'rw': "Ibicuruzwa byiza kuri budeshi: Shakisha ibintu biri munsi ya RWF {max_price:,}.",
            'sw': "Chaguo la Bei Nafuu: Tafuta bidhaa chini ya RWF {max_price:,}."
        },
        'medium': {
            'en': "Good Value Range: Products between RWF {min_price:,} - RWF {max_price:,} offer good balance.",
            'fr': "Bon rapport qualité-prix: Produits entre RWF {min_price:,} - RWF {max_price:,} offrent un bon équilibre.",
            'rw': "Agaciro kandi gihagije: Ibicuruzwa hagati ya RWF {min_price:,} - RWF {max_price:,} bifite ubuziranenge.",
            'sw': "Thamani Nzuri: Bidhaa kati ya RWF {min_price:,} - {max_price:,} zina ubora mzuri."
        },
        'high': {
            'en': "Premium Quality: For best quality, look above RWF {min_price:,}.",
            'fr': "Qualité premium: Pour la meilleure qualité, regardez au-dessus de RWF {min_price:,}.",
            'rw': "Ubuziranenge bwiza: Reba ibiri hejuru ya RWF {min_price:,}.",
            'sw': "Ubora wa Juu: Kwa ubora bora, angalia juu ya RWF {min_price:,}."
        }
    }
    
    @staticmethod
    def process_message(message, user=None, user_type='client', language='en', session_id=None):
        """Main processing function with prioritized Local Intelligence"""
        
        try:
            # Clean message
            message = message.strip()
            if not message:
                return {"response": "Please provide a message", "error": "Empty message"}
            
            # Detect language if not provided
            if not language or language == 'en':
                language = AIService.detect_language(message)
            
            # Check for inappropriate content
            is_inappropriate, keyword = AIService.check_inappropriate_content(message)
            if is_inappropriate:
                return EnhancedAIService._get_warning_response(keyword, language)
            
            # --- PHASE 1: LOCAL INTELLIGENCE (Offline Brain) ---
            
            # 1. Greetings (Local)
            msg_lower = message.lower()
            greeting_keywords = [
                'hello', 'hi', 'hey', 'bonjour', 'salut', 'coucou',
                'muraho', 'meza', 'bimeze', 'bite', 'amakuru', 'umeho', 'waramutse', 'wiriwe',
                'habari', 'jambo', 'mambo', 'vipi', 'shikamoo', 'mzima', 'sawa', 'poa'
            ]
            
            if any(k == msg_lower or msg_lower.startswith(k + ' ') or msg_lower.startswith(k + '?') or msg_lower.endswith(' ' + k) for k in greeting_keywords):
                EnhancedAIService._reset_off_topic_count(session_id)
                return {
                    'type': 'greeting',
                    'message': AIService.get_greeting_response(user, language),
                    'language': language
                }

            # 2. System Status Check (User requested explicit status)
            if 'system status' in msg_lower or 'debug ai' in msg_lower or 'deepseek status' in msg_lower:
                return EnhancedAIService._check_api_status()

            # 3. Static Knowledge & Analytics (Local) - Handles "How to buy", "Max price", etc.
            static_response = EnhancedAIService._check_static_knowledge(message, language, user)
            if static_response:
                EnhancedAIService._reset_off_topic_count(session_id)
                return static_response

            # 4. Vendor Tools (Local)
            if user_type == 'vendor':
                if any(w in msg_lower for w in ['stock', 'inventory', 'quantity']):
                    return EnhancedAIService._handle_stock_request(user, language)
                if 'order' in msg_lower and any(w in msg_lower for w in ['list', 'show', 'my', 'update', 'status']):
                     return EnhancedAIService._handle_order_update_request(message, user)
                if any(w in msg_lower for w in ['business', 'report', 'sales', 'revenue']):
                     return AIVendorService.generate_business_report(user.id, 'monthly')

            # 5. Client Tools (Currency)
            if currency_converter.detect_currency_request(message, language):
                 return EnhancedAIService._handle_currency_conversion(message, language)

            # --- PHASE 2: RAG / DEEPSEEK (Cloud Brain) ---
            
            # Step A: Search system for ANY relevant data based on the message
            system_context = EnhancedAIService._search_system_data(message)
            
            # Step B: Pass to DeepSeek (or Local Failover if API error)
            response = EnhancedAIService._generate_rag_response(message, system_context, language, user)

            # Step C: Off-topic Monitoring (Post-processing)
            # Only increment if completely useless response (no context, no static answer)
            if not system_context and response.get('type') not in ['rag_response', 'static_info', 'search_results_fallback', 'analytics_info', 'fallback_smart', 'system_status', 'api_error', 'offline_chat']:
                EnhancedAIService._increment_off_topic_count(session_id)
            else:
                 EnhancedAIService._reset_off_topic_count(session_id)
            
            # Check Warning Limit
            if EnhancedAIService._get_off_topic_count(session_id) > 4:
                 return EnhancedAIService._get_warning_response("off_topic_limit", language)

            return response
            
        except Exception as e:
            print(f"process_message error: {e}")
            import traceback
            traceback.print_exc()
            return {
                'response': f"System Error: {str(e)}",
                'type': 'error'
            }
    
    @staticmethod
    def _check_api_status():
        """Explicitly checks DeepSeek API and tells user the truth."""
        import ssl
        try:
            # Bypass SSL verification for resilience
            ctx = ssl._create_unverified_context()
            
            req = urllib.request.Request(
                EnhancedAIService.DEEPSEEK_URL,
                data=json.dumps({"model": "deepseek-chat", "messages": [{"role": "user", "content": "ping"}]}).encode('utf-8'),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {EnhancedAIService.DEEPSEEK_API_KEY}"},
                method='POST'
            )
            with urllib.request.urlopen(req, context=ctx) as response:
                return {'type': 'system_status', 'message': "✅ **System Diagnosis: ONLINE**\n\nThe AI Brain is fully operational.", 'language': 'en'}
        except urllib.error.HTTPError as e:
            if e.code == 402:
                return {'type': 'system_status', 'message': "⚠️ **System Diagnosis: OFFLINE**\n\n**Reason:** AI Provider Payment Required (Quota Exceeded).\n**Impact:** Translation and complex chat features are currently disabled. Basic search and order tools are working.", 'language': 'en'}
            return {'type': 'system_status', 'message': f"⚠️ **System Diagnosis: ERROR**\nCode: {e.code}", 'language': 'en'}
        except Exception as e:
             return {'type': 'system_status', 'message': f"⚠️ **System Diagnosis: ERROR**\nConnection Failed: {str(e)}", 'language': 'en'}

    @staticmethod
    def _search_system_data(query):
        """Broad search returning raw data structures for RAG context."""
        context = []
        try:
            clean_query = query.lower()
            # Remove English AND Kinyarwanda/Swahili stop words to find the KEYWORD (e.g. 'Iron')
            remove_words = [
                'find', 'search', 'show', 'me', 'want', 'need', 'is', 'a', 'the', 'please', 'help', 'tell', 'about', 'looking', 'for', # English Generic
                'buy', 'purchase', 'get', 'ordering', 'order', 'pay', 'cost', 'price', # English Action
                'have', 'here', 'on', 'at', 'in', 'sokhub', 'you', 'your', 'products', 'items', 'list', 'all', 'available', # Conversational Fillers
                'ndashaka', 'ndashaka', 'nshaka', 'shaka', 'bashaka', 'kugura', 'gura', 'nkeneye', 'mbereka', 'nyereka', 'igiciro', # Kinyarwanda
                'natafuta', 'tafuta', 'nataka', 'nahitaji', 'onyesha', 'nipe', 'nunua', 'bei' # Swahili
            ]
            for word in remove_words:
                clean_query = clean_query.replace(f" {word} ", " ").replace(f"{word} ", " ").replace(f" {word}", " ").strip()
            
            clean_query = clean_query.strip()
            if len(clean_query) < 2:
                # If we stripped everything, return empty list
                return []

            # 1. Broad Search (Name, Description, Category, Vendor)
            products = Product.objects.filter(
                Q(name__icontains=clean_query) | 
                Q(description__icontains=clean_query) |
                Q(category__name__icontains=clean_query) |
                Q(vendor__vendorprofile__business_name__icontains=clean_query)
            ).select_related('vendor').distinct()[:5]

            # 2. Smart Catch: If NO products found, try searching just the Category Name with individual words
            if not products.exists() and ' ' in clean_query:
                parts = clean_query.split()
                for part in parts:
                    if len(part) > 3: # Only significant words
                        cat_products = Product.objects.filter(category__name__icontains=part)[:5]
                        if cat_products.exists():
                            products = cat_products
                            break
            
            for p in products:
                try: v_name = p.vendor.vendorprofile.business_name
                except: v_name = "Unknown Vendor"  
                context.append({
                    'type': 'Product',
                    'name': p.name,
                    'price': f"{p.price:,.0f} RWF",
                    'vendor': v_name,
                    'desc': p.description[:100] if p.description else ""
                })

            # 3. Vendors
            vendors = VendorProfile.objects.filter(
                Q(business_name__icontains=clean_query) |
                Q(business_description__icontains=clean_query)
            ).distinct()[:3]
            
            for v in vendors:
                context.append({'type': 'Vendor', 'name': v.business_name, 'desc': v.business_description[:100] if v.business_description else ""})

        except Exception as e:
            print(f"Search Data Error: {e}")
        
        return context

    @staticmethod
    def _check_static_knowledge(message, language, user):
        """Offline Brain: Handles Processes, Analytics, AND Identity"""
        msg_lower = message.lower()
        
        # 0. IDENTITY & BUSINESS INFO (High Priority)
        # This allows answering "What is SokHub" even without DeepSeek
        if 'sokhub' in msg_lower or 'what is this' in msg_lower or 'who are you' in msg_lower or 'company' in msg_lower:
            responses = {
                'en': "🚀 **About SokHub:**\n\nWe are a premier e-commerce platform connecting vendors and customers in Rwanda. You can buy Electronics, Fashion, Home goods, and more directly from local sellers.\n\nI am the **SokHub AI Assistant**, here to help you find products, check prices, and track orders!",
                'rw': "🚀 **Ibyerekeye SokHub:**\n\nTuri urubuga rwo guhahiraho ruhuza abacuruzi n'abaguzi mu Rwanda. Ushobora kugura Ibikoresho by'ikoranabuhanga, Imyenda, n'ibindi byinshi.\n\nNdi **SokHub AI**, nje kugufasha gushaka ibicuruzwa no kumenya ibiciro!",
                'fr': "🚀 **À propos de SokHub:**\n\nNous sommes une plateforme e-commerce connectant vendeurs et clients. Je suis l'assistant IA SokHub, ici pour vous aider !",
                'sw': "🚀 **Kuhusu SokHub:**\n\nSisi ni jukwaa la biashara la mtandaoni linalounganisha wauzaji na wateja. Unaweza kununua Vifaa vya Elektroniki, Mitindo, na Bidhaa za Nyumbani."
            }
            return {'type': 'static_info', 'message': responses.get(language, responses['en']), 'language': language}

        # 0.1 WHAT DO YOU SELL? (Business Scope)
        if any(w in msg_lower for w in ['what do you sell', 'sell', 'products', 'ibicuruzwa', 'bidhaa', 'muhaho']):
             if 'how' not in msg_lower and 'context' not in msg_lower: # Avoid collision with "how to sell"
                responses = {
                    'en': "🛍️ **Our Business Categories:**\n\nWe offer a wide range of products including:\n• **Electronics** (Phones, Laptops)\n• **Fashion** (Clothing, Shoes)\n• **Home & Garden**\n• **Sports & Outdoors**\n\nJust type what you are looking for!",
                    'rw': "🛍️ **Ibyo Ducuruza:**\n\nDuplite ibicuruzwa bitandukanye:\n• **Ikoranabuhanga** (Telefone, Mudasobwa)\n• **Imyenda n'Inkweto**\n• **Ibikoresho byo mu rugo**\n• **Siporo**\n\nAndika icyo ushaka!",
                    'fr': "🛍️ **Nos Produits:**\n\n• **Électronique**\n• **Mode**\n• **Maison**\n• **Sport**",
                    'sw': "🛍️ **Bidhaa Zetu:**\n\n• **Vifaa vya Elektroniki**\n• **Mitindo**\n• **Nyumbani**\n• **Michezo**"
                }
                return {'type': 'static_info', 'message': responses.get(language, responses['en']), 'language': language}
        
        # 1. Analytics: Maximum Price
        if 'maximum price' in msg_lower or 'highest price' in msg_lower or 'most expensive' in msg_lower:
            try:
                max_p = Product.objects.aggregate(Max('price'))['price__max']
                if max_p:
                    msg = {
                        'en': f"💰 The highest price found on our system is **RWF {max_p:,.0f}**.",
                        'rw': f"💰 Igiciro cyo hejuru cyane ni **RWF {max_p:,.0f}**."
                    }
                else:
                    msg = {'en': "💰 No products found to check prices.", 'rw': "Nta bicuruzwa bihari."}
                return {'type': 'analytics_info', 'message': msg.get(language, msg['en']), 'language': language}
            except: pass

        # 2. Analytics: Minimum Price
        if 'minimum price' in msg_lower or 'lowest price' in msg_lower or 'cheapest' in msg_lower:
            try:
                min_p = Product.objects.aggregate(Min('price'))['price__min']
                if min_p:
                    msg = {
                        'en': f"🏷️ The lowest starting price is **RWF {min_p:,.0f}**.",
                        'rw': f"🏷️ Igiciro cyo hasi cyane ni **RWF {min_p:,.0f}**."
                    }
                else:
                    msg = {'en': "🏷️ No products found.", 'rw': "Nta bicuruzwa bihari."}
                return {'type': 'analytics_info', 'message': msg.get(language, msg['en']), 'language': language}
            except: pass

        # 3. Analytics: Total Products
        if 'how many product' in msg_lower or 'total product' in msg_lower:
            count = Product.objects.count()
            msg = {
                'en': f"📦 We currently have **{count}** products listed on SokHub.",
                'rw': f"📦 Dufite ibicuruzwa **{count}** kuri SokHub."
            }
            return {'type': 'analytics_info', 'message': msg.get(language, msg['en']), 'language': language}
        
        # 4. How to Buy
        buy_keywords = ['how to buy', 'how can i buy', 'order process', 'process to buy', 'bigenda bite']
        if any(w in msg_lower for w in buy_keywords) or (('ukuntu' in msg_lower or 'uko' in msg_lower) and ('gura' in msg_lower or 'kugura' in msg_lower)):
            responses = {
                'en': "🛒 **How to Buy:**\n1. Search for a product.\n2. Click 'Add to Cart'.\n3. Go to Cart -> 'Checkout'.\n4. Enter details and Pay.",
                'fr': "🛒 **Comment acheter:**\n1. Cherchez un produit.\n2. Ajoutez au panier.\n3. Cliquez sur 'Payer'.",
                'rw': "🛒 **Uko Wagura:**\n1. Shakisha igicuruzwa.\n2. Kanda **'Add to Cart'**.\n3. Jya muri Cart ukande **'Checkout'**.\n4. Ishyura.",
                'sw': "🛒 **Jinsi ya Kununua:**\n1. Tafuta bidhaa.\n2. Bonyeza 'Ongeza kwa Kikapu'.\n3. Maliza."
            }
            return {'type': 'static_info', 'message': responses.get(language, responses['en']), 'language': language}
            
        # 5. Payment Methods
        pay_keywords = ['payment method', 'how to pay', 'momo', 'mobile money', 'visa', 'cash', 'kwishura']
        if any(w in msg_lower for w in pay_keywords):
            responses = {
                'en': "💳 **Payment Methods:**\n• Mobile Money (MTN/Airtel)\n• Cash on Delivery\n• Bank Cards",
                'rw': "💳 **Uko Wishyura:**\n• Mobile Money (MTN/Airtel)\n• Cash (Iyo bakugejejeho ibintu)\n• Bank Cards"
            }
            return {'type': 'static_info', 'message': responses.get(language, responses.get('rw', responses['en'])), 'language': language}

        return None

    @staticmethod
    def _generate_rag_response(user_query, context_data, language, user=None):
        """Uses DeepSeek to generate a response based on System Data (Context)."""
        import ssl
        try:
            # Prepare Context String
            if context_data:
                context_str = "SYSTEM DATA FOUND:\n" + "\n".join([f"- {item['type']}: {item['name']} ({item.get('price', '')})" for item in context_data])
            else:
                context_str = "SYSTEM DATA: None found matching keywords. General Question."

            user_name = user.username if user and hasattr(user, 'username') else "Client"
            
            # System Prompt
            system_prompt = f"You are SokHub AI, an expert e-commerce assistant. Answer strictly in {language}. If product data is provided, use it to sell the item. If not, explain SokHub's business categories (Electronics, Fashion). Be professional."

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {EnhancedAIService.DEEPSEEK_API_KEY}"
            }
            
            data = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Context: {context_str}\nQuestion: {user_query}"}
                ],
                "stream": False
            }
            
            ctx = ssl._create_unverified_context()
            
            req = urllib.request.Request(
                EnhancedAIService.DEEPSEEK_URL,
                data=json.dumps(data).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            
            with urllib.request.urlopen(req, context=ctx) as response:
                result = json.loads(response.read().decode('utf-8'))
                ai_reply = result['choices'][0]['message']['content']
                return {
                    'type': 'rag_response',
                    'message': ai_reply,
                    'language': language,
                    'data': context_data
                }

        except Exception as e:
            # FORCE OFFLINE MODE - 'Correcting the error' by simulating intelligence
            print(f"DeepSeek Offline: {e}")
            return EnhancedAIService._offline_chat_brain(user_query, context_data, language)

    @staticmethod
    def _offline_chat_brain(query, context_data, language):
        """A simple local rule-based AI to handle chats when the Brain is dead."""
        q_lower = query.lower()
        
        # 0. DESPERATE SEARCH (New): If we have NO context, try to find SOMETHING locally before giving up.
        # This handles cases where RAG search was too strict but there might be a match for a single word.
        if not context_data:
            ignored_words = ['i', 'want', 'need', 'buy', 'looking', 'for', 'show', 'me', 'what', 'is', 'a', 'do', 'you', 'have', 'best', 'good', 'cheap']
            words = [w for w in q_lower.split() if w not in ignored_words and len(w) > 2]
            
            for word in words:
                # Try finding products by name for this word
                found_products = Product.objects.filter(name__icontains=word)[:3]
                if found_products.exists():
                    context_data = [] # Initialize
                    for p in found_products:
                        try: v_name = p.vendor.vendorprofile.business_name
                        except: v_name = "Unknown Vendor"  
                        context_data.append({
                            'name': p.name,
                            'price': f"{p.price:,.0f} RWF",
                            'vendor': v_name
                        })
                    break # Stop after finding matches for one keyword

        # 1. If we actually found products locally (either originally or via Desperate Search), JUST SHOW THEM.
        if context_data:
             msg_lines = ["🔎 **Here is what I found:**"]
             if language == 'rw': msg_lines = ["🔎 **Dore ibyo nabonye:**"]
             if language == 'fr': msg_lines = ["🔎 **Voici ce que j'ai trouvé:**"]
             if language == 'sw': msg_lines = ["🔎 **Hiki ndicho nilichokaipata:**"]
             
             for item in context_data:
                 msg_lines.append(f"• **{item['name']}** - {item.get('price', '')} ({item.get('vendor', '')})")
             return {'type': 'search_results_fallback', 'message': "\n".join(msg_lines), 'language': language, 'data': context_data}

        # 2. Handle specific "Inka" (Cow) or common random search terms
        if 'inka' in q_lower or 'cow' in q_lower:
            return {
                'type': 'offline_chat',
                'message': "🐄 **Inka?**\nSorry, we don't sell live animals on SokHub yet! We mainly sell Electronics, Fashion, and Home goods.\n\nNtago ducuruza amatungo. Reba ibikoresho by'ikoranabuhanga cyangwa imyenda.", 
                'language': language
            }
            
        if 'food' in q_lower or 'ibiryo' in q_lower or 'amazi' in q_lower:
             return {'type': 'offline_chat', 'message': "🍔 We have some groceries! Try searching for 'Rice', 'Sugar', or 'Oil'.", 'language': language}
        
        # 3. Identity
        if 'who are you' in q_lower or 'uri nde' in q_lower or 'what is this' in q_lower:
            return {'type': 'offline_chat', 'message': "🤖 I am **SokHub AI**. Even when my cloud brain is offline (like now), I'm here to help you find products!", 'language': language}

        # 4. Generic Fallback (Polite, no error code) with Smart Suggestions
        cats = Category.objects.all().order_by('?')[:3]
        cat_names = ", ".join([c.name for c in cats]) if cats else "Electronics, Fashion"
        
        msgs = {
            'en': f"🤔 I heard '{query}', but I couldn't find a match in our store yet.\n\nI am currently operating in **Local Mode** (Fast Search), so I can best help you find **Products**. Try searching for: **{cat_names}**!",
            'rw': f"🤔 Numvise '{query}', ariko ntabwo nabibonye.\n\nUbu nshobora kugufasha gushaka ibicuruzwa gusa. Reba muri: **{cat_names}**.",
            'fr': f"🤔 Je n'ai pas trouvé '{query}'. Essayez nos catégories: **{cat_names}**.",
            'sw': f"🤔 Sikupata '{query}'. Jaribu kutafuta: **{cat_names}**."
        }
        return {'type': 'fallback', 'message': msgs.get(language, msgs['en']), 'language': language}

    # --- Helper methods for state management ---
    @staticmethod
    def _increment_off_topic_count(session_id):
        if not session_id: return
        try:
            session = ChatSession.objects.filter(session_id=session_id).first()
            if session:
                ctx = session.context
                ctx['off_topic_count'] = ctx.get('off_topic_count', 0) + 1
                session.context = ctx
                session.save()
        except: pass

    @staticmethod
    def _reset_off_topic_count(session_id):
        if not session_id: return
        try:
            session = ChatSession.objects.filter(session_id=session_id).first()
            if session:
                ctx = session.context
                ctx['off_topic_count'] = 0
                session.context = ctx
                session.save()
        except: pass

    @staticmethod
    def _get_off_topic_count(session_id):
        if not session_id: return 0
        try:
            session = ChatSession.objects.filter(session_id=session_id).first()
            return session.context.get('off_topic_count', 0) if session else 0
        except: return 0

    @staticmethod
    def _get_warning_response(keyword, language):
        warnings = {
            'en': "⚠️ PLEASE FOCUS ON BUSINESS.\nI am designed to help with Shopping and Selling on SokHub only.",
            'fr': "⚠️ CONCENTREZ-VOUS SUR LES AFFAIRES.\nJe suis conçu pour aider avec SokHub uniquement.",
            'rw': "⚠️ TUVUGANE IBY'UBUCURUZI.\nNdi hano gufasha abaguzi n'abagurisha kuri SokHub gusa.",
            'sw': "⚠️ TAFADHALI TUJIKITE KWENYE BIASHARA.\nNiko hapa kusaidia na SokHub tu."
        }
        return {'type': 'warning', 'message': warnings.get(language, warnings['en']), 'language': language}
    
    # --- Keep Essential Handlers ---
    @staticmethod
    def _handle_stock_request(user, language):
        """Handle stock/inventory requests - Real Implementation"""
        try:
            products = Product.objects.filter(vendor=user)
            total_products = products.count()
            low_stock = products.filter(quantity__lte=5).count()
            out_of_stock = products.filter(quantity=0).count()
            
            responses = {
                'en': f"📊 **Stock Overview**\n\n• Total Products: {total_products}\n• Low Stock: {low_stock}\n• Out of Stock: {out_of_stock}\n\nCheck your dashboard for details.",
                'fr': f"📊 **Aperçu du Stock**\n\n• Total: {total_products}\n• Stock bas: {low_stock}\n• Rupture: {out_of_stock}",
                'rw': f"📊 **Incamake ya Stock**\n\n• Igiteranyo: {total_products}\n• Ibiri gushira: {low_stock}\n• Ibyashize: {out_of_stock}",
                'sw': f"📊 **Muhtasari wa Hisa**\n\n• Jumla: {total_products}\n• Hisa ndogo: {low_stock}"
            }
            return {
                'type': 'stock_info',
                'message': responses.get(language, responses['en']),
                'language': language
            }
        except Exception as e:
            return {'type': 'error', 'message': f"Error checking stock: {str(e)}"}

    @staticmethod
    def _handle_order_update_request(message, user):
        """Handle order update requests - Real Implementation"""
        try:
            orders = Order.objects.filter(vendor=user).order_by('-created_at')[:5]
            if not orders.exists():
                 return {'type': 'order_info', 'message': "📦 You have no orders yet.", 'language': 'en'}
            order_list = []
            for order in orders:
                order_list.append(f"• **Order #{order.order_number}**: {order.status} (RWF {order.total_amount:,.0f})")
            order_str = "\n".join(order_list)
            return {'type': 'order_info', 'message': f"📦 **Recent Orders:**\n\n{order_str}\n\nGo to your dashboard to manage them.", 'language': 'en'}
        except Exception as e:
            return {'type': 'error', 'message': f"Error fetching orders: {str(e)}"}

    @staticmethod
    def _handle_currency_conversion(message, language):
        amount, target_currency = currency_converter.extract_currency_amount(message)
        if not amount:
             return {'type': 'currency_prompt', 'message': "Please specify an amount to convert.", 'language': language}
        result = currency_converter.format_conversion(amount, target_currency, language)
        return {'type': 'currency_result', 'message': result, 'language': language}

    # Legacy method stubs if needed by other imports (though process_message is main entry)
    @staticmethod
    def _search_system(message, language, strict=True):
        # Redirect to RAG logic
        return {'type': 'info', 'message': 'Please use main chat.'}

# Singleton instance
enhanced_ai_service = EnhancedAIService()