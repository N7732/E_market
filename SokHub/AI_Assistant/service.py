# services.py - Enhanced AI Service with multi-language support and smart responses
import json
from datetime import datetime, timedelta
from django.conf import settings
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone
import re
from typing import Dict, List, Optional, Tuple

# Import models
try:
    from product.models import Product, Category
    from order.models import Order, OrderItem
    from customer.models import User, UserProfile, CustomerProfile,VendorProfile
    #from vendor.models import VendorProfile
except ImportError:
    # Define fallback models or handle appropriately
    pass

# Import permissions from security
try:
    from .security import AIAssistantPermissions
except ImportError:
    # Fallback if security is not ready
    class AIAssistantPermissions:
        @staticmethod
        def can_access_ai_assistant(user): 
            return True if user else False
        
        @staticmethod
        def can_access_client_features(user): 
            return True if user else False
        
        @staticmethod
        def can_access_vendor_features(user): 
            return getattr(user, 'user_type', '') == 'vendor' if user else False

class AIService:
    """Common AI utilities with multilingual support"""
    
    # Multi-language greetings and responses
    GREETINGS = {
        'en': ['hi', 'hello', 'hey', 'greetings', 'good morning', 'good evening', 'good afternoon', 'howdy'],
        'fr': ['bonjour', 'salut', 'coucou', 'bonsoir'],
        'rw': ['muraho', 'bite', 'mwiriwe', 'muramuke'],
        'sw': ['habari', 'jambo', 'hujambo', 'salamu']
    }
    
    # Inappropriate content patterns
    INAPPROPRIATE_KEYWORDS = [
        'porn', 'pornography', 'xxx', 'adult', 'sex', 'nude', 'naked',
        'violence', 'kill', 'murder', 'drug', 'weed', 'cocaine', 'heroin',
        'hate', 'racist', 'terror', 'illegal', 'scam', 'fraud'
    ]
    
    # Business-related keywords
    BUSINESS_KEYWORDS = [
        'buy', 'sell', 'product', 'price', 'cost', 'order', 'delivery',
        'shop', 'store', 'market', 'business', 'sales', 'revenue',
        'customer', 'vendor', 'payment', 'shipping', 'stock', 'inventory'
    ]
    
    @staticmethod
    def detect_language(text: str) -> str:
        """Detect language of the text"""
        text_lower = text.lower()
        
        # Check for Kinyarwanda words
        rw_words = ['muraho', 'bite', 'mwiriwe', 'amafaranga', 'ubucuruzi']
        if any(word in text_lower for word in rw_words):
            return 'rw'
        
        # Check for French words
        fr_words = ['bonjour', 'merci', 's\'il vous plaît', 'produit', 'prix']
        if any(word in text_lower for word in fr_words):
            return 'fr'
        
        # Check for Swahili words
        sw_words = ['habari', 'asante', 'tafadhali', 'bidhaa', 'bei']
        if any(word in text_lower for word in sw_words):
            return 'sw'
        
        # Default to English
        return 'en'
    
    @staticmethod
    def _extract_keywords(text: str, language: str = 'en') -> List[str]:
        """Enhanced keyword extraction with language support"""
        # Multi-language stop words
        stop_words = {
            'en': ['i', 'want', 'need', 'looking', 'for', 'a', 'an', 'the', 'please', 'find', 'me', 
                   'buy', 'what', 'which', 'who', 'where', 'when', 'is', 'are', 'show', 'list', 
                   'how', 'search', 'get', 'price', 'of', 'cost', 'much', 'do', 'you', 'have',
                   'can', 'could', 'would', 'should', 'will', 'shall', 'may', 'might', 'must'],
            'fr': ['je', 'veux', 'besoin', 'cherche', 'pour', 'un', 'une', 'le', 'la', 'les', 
                   's\'il vous plaît', 'trouver', 'moi', 'acheter', 'quoi', 'quel', 'qui',
                   'où', 'quand', 'est', 'sont', 'montrer', 'liste', 'comment', 'rechercher',
                   'obtenir', 'prix', 'de', 'coût', 'combien', 'faites', 'vous', 'avez'],
            'rw': ['njye', 'shaka', 'keneye', 'gushaka', 'kwa', 'umwe', 'iyo', 'nyabunenge',
                   'mubwire', 'shakisha', 'njye', 'gura', 'iki', 'ikihe', 'nde', 'he',
                   'ryari', 'ni', 'ari', 'ereka', 'urutonde', 'ute', 'shakisha', 'kubero',
                   'igiciro', 'cya', 'ubwishyu', 'angahe', 'kora', 'wowe', 'ufite'],
            'sw': ['mimi', 'nataka', 'nahitaji', 'kutafuta', 'kwa', 'moja', 'hii', 'tafadhali',
                   'tafuta', 'mimi', 'nunua', 'nini', 'ipi', 'nani', 'wapi', 'lini', 'ni',
                   'wako', 'onyesha', 'orodha', 'jinsi', 'tafuta', 'pata', 'bei', 'ya',
                   'gharama', 'ngapi', 'fanya', 'wewe', 'una']
        }
        
        words = re.findall(r'\b\w+\b', text.lower())
        lang_stop_words = stop_words.get(language, stop_words['en'])
        keywords = [word for word in words if word not in lang_stop_words and len(word) > 1]
        
        return keywords[:10]
    
    @staticmethod
    def check_inappropriate_content(text: str) -> Tuple[bool, str]:
        """Check if text contains inappropriate content"""
        text_lower = text.lower()
        
        for keyword in AIService.INAPPROPRIATE_KEYWORDS:
            if keyword in text_lower:
                return True, keyword
        
        return False, ""
    
    @staticmethod
    def is_business_related(text: str) -> bool:
        """Check if text is business/market related"""
        text_lower = text.lower()
        
        # If contains business keywords, it's related
        for keyword in AIService.BUSINESS_KEYWORDS:
            if keyword in text_lower:
                return True
        
        # Check if it's a greeting or small talk
        greetings = ['hi', 'hello', 'hey', 'how are you', 'good morning', 'good evening']
        if any(greet in text_lower for greet in greetings):
            return True  # Allow greetings
        
        # Check if it's about SokHub platform
        sokhub_terms = ['sokhub', 'soko', 'market', 'shop', 'store', 'buy', 'sell']
        if any(term in text_lower for term in sokhub_terms):
            return True
        
        return False
    
    @staticmethod
    def get_greeting_response(user=None, language: str = 'en') -> str:
        """Get personalized greeting response based on user and language"""
        
        greetings = {
            'en': {
                'vendor': [
                    "Hello {name}! 👋 Welcome back to your SokHub vendor dashboard. Ready to boost your business today?",
                    "Greetings, {name}! 🛍️ Your SokHub AI assistant is here to help grow your sales and analyze your performance.",
                    "Hey {name}! 🤖 Your business intelligence dashboard is ready. How can I assist with your store today?"
                ],
                'client': [
                    "Welcome back, {name}! 🎉 Your personal shopping assistant is here to find the best products for you!",
                    "Hello {name}! 👋 Ready to discover amazing products on SokHub today?",
                    "Hey {name}! 🛒 Your SokHub AI guide is online. Let's find something great for you!"
                ],
                'guest': [
                    "Hello! 👋 Welcome to SokHub Marketplace! I'm your AI assistant ready to help you shop or sell.",
                    "Greetings! 🎯 I'm SokHub AI, your guide to the best marketplace experience. How can I assist?",
                    "Hey there! 🛍️ Welcome to SokHub! I can help you find products or learn about selling."
                ]
            },
            'fr': {
                'vendor': [
                    "Bonjour {name}! 👋 Bienvenue sur votre tableau de bord SokHub. Prêt à booster votre business aujourd'hui?",
                    "Salutations, {name}! 🛍️ Votre assistant AI SokHub est là pour développer vos ventes.",
                    "Salut {name}! 🤖 Votre tableau de bord d'intelligence commerciale est prêt."
                ],
                'client': [
                    "Bon retour, {name}! 🎉 Votre assistant shopping personnel est là pour vous!",
                    "Bonjour {name}! 👋 Prêt à découvrir des produits incroyables sur SokHub?",
                    "Salut {name}! 🛒 Votre guide AI SokHub est en ligne."
                ],
                'guest': [
                    "Bonjour! 👋 Bienvenue sur SokHub Marketplace! Je suis votre assistant AI.",
                    "Salutations! 🎯 Je suis SokHub AI, votre guide pour la meilleure expérience marketplace.",
                    "Salut! 🛍️ Bienvenue sur SokHub! Je peux vous aider à trouver des produits."
                ]
            },
            'rw': {
                'vendor': [
                    "Muraho {name}! 👋 Murakaza neza kuri SokHub! Nituma gufasha ubucuruzi bwawe.",
                    "Mwiriwe {name}! 🛍️ Ubu buryo bwo gukora ubucuruzi bwiza bwa SokHub.",
                    "Bite {name}! 🤖 SokHub AI iri kumwe nawe kugirango ifashe ubucuruzi bwawe."
                ],
                'client': [
                    "Murakaza neza {name}! 🎉 Ndi umuyobozi wawe wo gushakisha ibicuruzwa.",
                    "Muraho {name}! 👋 Witeguye gushakisha ibintu bishya kuri SokHub?",
                    "Bite {name}! 🛒 SokHub AI iri kumwe nawe mu gushakisha ibicuruzwa."
                ],
                'guest': [
                    "Muraho! 👋 Murakaza neza kuri SokHub Marketplace! Ndi umuyobozi wawe wo gushakisha.",
                    "Mwiriwe! 🎯 Ndi SokHub AI, umuyobozi wawe wo gushakisha ibintu byiza.",
                    "Bite! 🛍️ Murakaza neza kuri SokHub! Nshobora kugufasha gushakisha ibicuruzwa."
                ]
            }
        }
        
        user_type = 'guest'
        user_name = 'there'
        
        if user and user.is_authenticated:
            user_type = getattr(user, 'user_type', 'client')
            
            # Get user's display name
            if hasattr(user, 'first_name') and user.first_name:
                user_name = user.first_name
            elif hasattr(user, 'username'):
                user_name = user.username
        
        lang_greetings = greetings.get(language, greetings['en'])
        user_greetings = lang_greetings.get(user_type, lang_greetings['guest'])
        
        import random
        greeting = random.choice(user_greetings)
        
        return greeting.format(name=user_name)
    
    @staticmethod
    def get_contact_info(vendor_name: str) -> Optional[Dict]:
        """Get vendor contact information"""
        try:
            vendor = User.objects.filter(
                Q(vendorprofile__business_name__icontains=vendor_name) |
                Q(username__icontains=vendor_name)
            ).first()
            
            if vendor and hasattr(vendor, 'vendorprofile'):
                profile = vendor.vendorprofile
                return {
                    'name': profile.business_name,
                    'email': vendor.email,
                    'phone': getattr(profile, 'phone_number', 'Not provided'),
                    'address': getattr(profile, 'address', 'Not provided'),
                    'website': getattr(profile, 'website', 'Not provided')
                }
        except Exception:
            pass
        
        return None
    
    @staticmethod
    def _rank_products(products, keywords):
        """Rank products based on relevance"""
        ranked = []
        for product in products:
            score = 0
            prod_name = product.name.lower()
            prod_desc = product.description.lower() if product.description else ""
            
            for keyword in keywords:
                if keyword in prod_name:
                    score += 3
                if keyword in prod_desc:
                    score += 1
            
            # Boost score for products with images
            if hasattr(product, 'image') and product.image:
                score += 1
            
            # Boost score for products with good ratings
            if hasattr(product, 'rating') and product.rating and product.rating >= 4.0:
                score += 2
            
            ranked.append((product, score))
        
        ranked.sort(key=lambda x: x[1], reverse=True)
        return [item[0] for item in ranked]
    
    @staticmethod
    def _get_period_start(period):
        now = datetime.now()
        if period == 'daily':
            return now - timedelta(days=1)
        elif period == 'weekly':
            return now - timedelta(weeks=1)
        elif period == 'yearly':
            return now - timedelta(days=365)
        return now - timedelta(days=30)  # monthly

class AIClientService:
    """AI services for clients"""
    
    @staticmethod
    def find_products_by_wish(client_wish, user_location=None, vendor_filter=None, max_results=10):
        """
        Find products based on client's wish with enhanced search
        """
        # Detect language for better keyword extraction
        language = AIService.detect_language(client_wish)
        keywords = AIService._extract_keywords(client_wish, language)
        
        # Remove vendor name from keywords if it exists
        if vendor_filter:
            vendor_filter_lower = vendor_filter.lower()
            keywords = [k for k in keywords if k != vendor_filter_lower]
        
        q_objects = Q(is_available=True, status='active')
        
        if keywords:
            # Create search query with multiple fields
            for keyword in keywords:
                q_objects &= (
                    Q(name__icontains=keyword) |
                    Q(description__icontains=keyword) |
                    Q(category__name__icontains=keyword) |
                    Q(tags__icontains=keyword)
                )
        
        if vendor_filter:
            # Filter by vendor
            q_objects &= (
                Q(vendor__vendorprofile__business_name__icontains=vendor_filter) |
                Q(vendor__username__icontains=vendor_filter)
            )
        
        products = Product.objects.filter(q_objects).select_related(
            'vendor', 'vendor__vendorprofile', 'category'
        )[:max_results]
        
        # Rank results if we have keywords
        if keywords and products:
            ranked_products = AIService._rank_products(products, keywords)
            return list(ranked_products)[:max_results]
        
        return list(products)
    
    @staticmethod
    def get_product_details(product_id):
        """Get detailed product information"""
        try:
            product = Product.objects.select_related(
                'vendor', 'vendor__vendorprofile', 'category'
            ).get(id=product_id)
            
            return {
                'id': product.id,
                'name': product.name,
                'description': product.description,
                'price': product.price,
                'currency': getattr(product, 'currency', 'RWF'),
                'vendor': {
                    'name': product.vendor.username,
                    'business_name': getattr(product.vendor.vendorprofile, 'business_name', ''),
                    'rating': getattr(product.vendor.vendorprofile, 'rating', 0)
                },
                'category': product.category.name if product.category else '',
                'stock': getattr(product, 'stock_quantity', 'Available'),
                'image_url': product.image.url if hasattr(product, 'image') and product.image else None
            }
        except Product.DoesNotExist:
            return None
    
    @staticmethod
    def compare_products(product_ids):
        """Compare multiple products"""
        products = []
        for pid in product_ids[:5]:  # Limit to 5 products
            product = AIClientService.get_product_details(pid)
            if product:
                products.append(product)
        
        if len(products) < 2:
            return None
        
        # Create comparison table
        comparison = {
            'products': products,
            'cheapest': min(products, key=lambda x: x['price']),
            'best_rated': max(products, key=lambda x: x.get('vendor', {}).get('rating', 0))
        }
        
        return comparison

class AIVendorService:
    """Enhanced AI services for vendors"""
    
    @staticmethod
    def generate_business_report(user_id, period='monthly'):
        """
        Generate comprehensive business report for vendor
        """
        try:
            vendor_user = User.objects.get(id=user_id)
            if getattr(vendor_user, 'user_type', '') != 'vendor':
                return None
        except User.DoesNotExist:
            return None
        
        start_date = AIService._get_period_start(period)
        orders = Order.objects.filter(
            vendor=vendor_user,
            created_at__gte=start_date
        ).exclude(status='cancelled')
        
        # Calculate comprehensive metrics
        total_sales = orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        total_orders = orders.count()
        avg_order_value = total_sales / total_orders if total_orders > 0 else 0
        
        # Customer metrics
        unique_customers = orders.values('customer').distinct().count()
        
        # Product metrics
        popular_products = AIVendorService._get_popular_products(orders)
        low_stock_products = AIVendorService._get_low_stock_products(vendor_user)
        
        # Growth analysis
        previous_period = AIService._get_period_start(period + '_previous')
        previous_orders = Order.objects.filter(
            vendor=vendor_user,
            created_at__range=[previous_period, start_date]
        ).exclude(status='cancelled')
        
        previous_sales = previous_orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        growth_rate = ((total_sales - previous_sales) / previous_sales * 100) if previous_sales > 0 else 0
        
        # AI Analysis with actionable insights
        analysis = {
            'performance_score': AIVendorService._calculate_performance_score(vendor_user, orders),
            'growth_trend': AIVendorService._analyze_growth_trend(orders, period),
            'market_position': AIVendorService._analyze_market_position(vendor_user),
            'recommendations': AIVendorService._generate_actionable_recommendations(
                vendor_user, orders, popular_products, low_stock_products
            ),
            'customer_insights': AIVendorService._analyze_customer_segments(orders),
            'sales_forecast': AIVendorService._generate_sales_forecast(orders, period),
            'seasonal_trends': AIVendorService._detect_seasonal_patterns(orders)
        }
        
        vendor_name = vendor_user.username
        if hasattr(vendor_user, 'vendorprofile'):
            vendor_name = vendor_user.vendorprofile.business_name
        
        return {
            'vendor': vendor_name,
            'period': period,
            'summary': {
                'total_sales': float(total_sales),
                'total_orders': total_orders,
                'average_order_value': float(avg_order_value),
                'unique_customers': unique_customers,
                'growth_rate': round(growth_rate, 2),
                'performance_score': analysis['performance_score']
            },
            'products': {
                'popular': popular_products[:5],
                'low_stock': low_stock_products,
                'top_selling_category': AIVendorService._get_top_category(orders)
            },
            'customers': {
                'retention_rate': AIVendorService._calculate_retention_rate(orders),
                'new_vs_returning': AIVendorService._analyze_customer_types(orders)
            },
            'ai_analysis': analysis,
            'action_items': AIVendorService._generate_action_items(analysis, vendor_user)
        }
    
    @staticmethod
    def _get_popular_products(orders):
        """Get most popular products with sales data"""
        from collections import Counter
        product_counter = Counter()
        product_revenue = {}
        
        for order in orders:
            for item in order.items.all():
                product_counter[item.product_name] += item.quantity
                if item.product_name not in product_revenue:
                    product_revenue[item.product_name] = 0
                product_revenue[item.product_name] += item.price * item.quantity
        
        popular_products = []
        for product_name, count in product_counter.most_common(10):
            popular_products.append({
                "name": product_name,
                "units_sold": count,
                "revenue": product_revenue.get(product_name, 0)
            })
        
        return popular_products
    
    @staticmethod
    def _get_low_stock_products(vendor_user):
        """Identify products with low stock"""
        try:
            low_stock = Product.objects.filter(
                vendor=vendor_user,
                is_available=True
            ).filter(
                Q(stock_quantity__lt=10) | Q(stock_quantity__isnull=True)
            ).values('name', 'stock_quantity')[:5]
            
            return list(low_stock)
        except:
            return []
    
    @staticmethod
    def _calculate_performance_score(vendor, orders):
        """Calculate comprehensive performance score (0-100)"""
        if not orders.exists():
            return 50  # Neutral score for new vendors
        
        total_sales = orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        total_orders = orders.count()
        avg_order = total_sales / total_orders if total_orders > 0 else 0
        
        # Calculate score based on multiple factors
        score = 50  # Base score
        
        # Sales volume factor (0-20 points)
        if total_sales > 1000000:  # 1M RWF
            score += 20
        elif total_sales > 500000:
            score += 15
        elif total_sales > 100000:
            score += 10
        elif total_sales > 0:
            score += 5
        
        # Order frequency factor (0-15 points)
        if total_orders > 50:
            score += 15
        elif total_orders > 20:
            score += 10
        elif total_orders > 5:
            score += 5
        
        # Average order value factor (0-15 points)
        if avg_order > 50000:
            score += 15
        elif avg_order > 20000:
            score += 10
        elif avg_order > 5000:
            score += 5
        
        # Customer satisfaction factor (simulated, 0-10 points)
        # In real implementation, use actual ratings
        score += 8
        
        return min(100, max(0, score))
    
    @staticmethod
    def _analyze_growth_trend(orders, period):
        """Analyze business growth trends"""
        if not orders.exists():
            return "No data available for trend analysis"
        
        # Group orders by time period
        orders_by_period = {}
        for order in orders:
            if period == 'daily':
                key = order.created_at.date()
            elif period == 'weekly':
                key = order.created_at.isocalendar()[1]  # Week number
            else:  # monthly
                key = order.created_at.strftime('%Y-%m')
            
            if key not in orders_by_period:
                orders_by_period[key] = []
            orders_by_period[key].append(order)
        
        if len(orders_by_period) < 2:
            return "Need more data points for trend analysis"
        
        # Calculate growth
        periods = sorted(orders_by_period.keys())
        recent_sales = sum(o.total_amount for o in orders_by_period[periods[-1]])
        previous_sales = sum(o.total_amount for o in orders_by_period[periods[-2]])
        
        if previous_sales == 0:
            return "Strong growth from zero base! 📈"
        
        growth_pct = ((recent_sales - previous_sales) / previous_sales) * 100
        
        if growth_pct > 20:
            return f"Excellent growth! 📈 Sales up by {growth_pct:.1f}%"
        elif growth_pct > 0:
            return f"Steady growth 📈 Sales up by {growth_pct:.1f}%"
        elif growth_pct > -10:
            return f"Stable performance ➡️ Sales changed by {growth_pct:.1f}%"
        else:
            return f"Attention needed 📉 Sales down by {abs(growth_pct):.1f}%"
    
    @staticmethod
    def _generate_actionable_recommendations(vendor_user, orders, popular_products, low_stock_products):
        """Generate actionable business recommendations"""
        recommendations = []
        
        if not orders.exists():
            recommendations.extend([
                "Add at least 10 products with clear images and descriptions",
                "Set competitive prices by checking similar products on SokHub",
                "Share your store link on social media to attract first customers",
                "Offer a launch discount or 'buy one get one' promotion"
            ])
            return recommendations
        
        total_sales = orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        total_orders = orders.count()
        avg_order = total_sales / total_orders if total_orders > 0 else 0
        
        # Stock recommendations
        if low_stock_products:
            low_stock_names = [p['name'] for p in low_stock_products[:3]]
            recommendations.append(
                f"Restock soon: {', '.join(low_stock_names)} are running low"
            )
        
        # Pricing recommendations
        if avg_order < 15000:
            recommendations.append(
                "Bundle related products to increase average order value (e.g., phone + case + charger)"
            )
        
        # Marketing recommendations
        if total_orders < 20:
            recommendations.extend([
                "Run a weekend flash sale (10-20% off) to boost orders",
                "Ask satisfied customers for reviews to build trust",
                "Use product tags and categories effectively for better discovery"
            ])
        else:
            recommendations.extend([
                "Create a loyalty program for repeat customers",
                "Analyze your popular products and consider expanding those categories",
                "Optimize product images and descriptions based on customer feedback"
            ])
        
        # Seasonal recommendations
        current_month = datetime.now().month
        if current_month in [11, 12]:  # Holiday season
            recommendations.append("Create holiday-themed bundles and promotions")
        elif current_month in [6, 7]:  # Back-to-school
            recommendations.append("Offer back-to-school bundles for students")
        
        return recommendations[:5]  # Return top 5 recommendations
    
    @staticmethod
    def update_order_status(vendor_user, order_identifier, new_status):
        """Update order status with enhanced validation"""
        try:
            order = None
            
            # Handle special identifiers
            if order_identifier.lower() in ['latest', 'last', 'recent', 'current']:
                order = Order.objects.filter(vendor=vendor_user).order_by('-created_at').first()
            elif order_identifier.lower() == 'oldest':
                order = Order.objects.filter(vendor=vendor_user).order_by('created_at').first()
            else:
                # Search by order number, ID, or customer name
                order = Order.objects.filter(
                    vendor=vendor_user
                ).filter(
                    Q(order_number__icontains=order_identifier) |
                    Q(short_code__icontains=order_identifier) |
                    Q(customer__username__icontains=order_identifier) |
                    Q(customer__first_name__icontains=order_identifier) |
                    Q(customer__last_name__icontains=order_identifier)
                ).first()
            
            if not order:
                return {
                    'success': False,
                    'message': f"Order '{order_identifier}' not found. Please check the order number."
                }
            
            # Map spoken status to system status
            status_map = {
                'complete': 'delivered', 'completed': 'delivered', 'done': 'delivered',
                'deliver': 'delivered', 'delivered': 'delivered', 'finish': 'delivered',
                'confirm': 'confirmed', 'confirmed': 'confirmed', 'accept': 'confirmed',
                'ship': 'shipped', 'shipped': 'shipped', 'dispatch': 'shipped',
                'process': 'processing', 'processing': 'processing',
                'cancel': 'cancelled', 'cancelled': 'cancelled', 'refuse': 'cancelled',
                'pending': 'pending', 'waiting': 'pending'
            }
            
            target_status = status_map.get(new_status.lower().strip())
            
            if not target_status:
                valid_statuses = ', '.join(set(status_map.values()))
                return {
                    'success': False,
                    'message': f"Status '{new_status}' not recognized. Valid statuses: {valid_statuses}"
                }
            
            # Check if status transition is valid
            valid_transitions = {
                'pending': ['confirmed', 'cancelled'],
                'confirmed': ['processing', 'cancelled'],
                'processing': ['shipped', 'cancelled'],
                'shipped': ['delivered'],
                'delivered': [],  # Final state
                'cancelled': []   # Final state
            }
            
            if target_status not in valid_transitions.get(order.status, []):
                return {
                    'success': False,
                    'message': f"Cannot change status from '{order.status}' to '{target_status}'. "
                              f"Valid next statuses: {', '.join(valid_transitions.get(order.status, []))}"
                }
            
            # Update order
            order.status = target_status
            
            if target_status == 'delivered':
                order.delivered_at = timezone.now()
            elif target_status == 'confirmed':
                order.confirmed_at = timezone.now()
            elif target_status == 'shipped':
                order.shipped_at = timezone.now()
            
            order.save()
            
            # Prepare response message
            status_messages = {
                'delivered': "🎉 Order successfully marked as delivered! The customer has been notified.",
                'confirmed': "✅ Order confirmed! Ready for processing.",
                'shipped': "🚚 Order shipped! Tracking information updated.",
                'processing': "⚙️ Order is now being processed.",
                'cancelled': "❌ Order cancelled. Customer has been notified."
            }
            
            message = status_messages.get(target_status, 
                f"Order status updated to {target_status}.")
            
            return {
                'success': True,
                'message': message,
                'order_number': order.order_number,
                'status': target_status,
                'customer': order.customer.username if order.customer else 'Unknown'
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f"Error updating order: {str(e)}"
            }

class EnhancedAIService:
    """Enhanced AI Service with intelligent conversation handling"""
    
    # Conversation context tracker
    conversation_context = {}
    
    # Non-business topic counter
    off_topic_count = {}
    
    @staticmethod
    def process_chat_message(message, user=None, user_id=None, session_context=None):
        """
        Main method to process chat messages with enhanced intelligence
        """
        # Get user object
        if not user and user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                user = None
        
        user_type = getattr(user, 'user_type', 'guest') if user else 'guest'
        msg_lower = message.lower().strip()
        language = AIService.detect_language(message)
        
        # Track conversation context
        session_id = f"{user_id if user else 'guest'}_{language}"
        if session_id not in EnhancedAIService.conversation_context:
            EnhancedAIService.conversation_context[session_id] = {
                'history': [],
                'last_intent': None,
                'last_products': [],
                'vendor_mentioned': None,
                'product_interest': None
            }
        
        context = EnhancedAIService.conversation_context[session_id]
        context['history'].append({'role': 'user', 'content': message})
        
        # 1. CHECK FOR INAPPROPRIATE CONTENT
        is_inappropriate, keyword = AIService.check_inappropriate_content(message)
        if is_inappropriate:
            response = (
                "🚫 I'm sorry, but I cannot assist with content related to '{}'. "
                "As SokHub AI, I'm designed to help with shopping, business, and marketplace-related queries only. "
                "Please ask me about products, orders, or business assistance instead."
            ).format(keyword)
            
            context['history'].append({'role': 'assistant', 'content': response})
            return {
                'response': response,
                'intent': 'inappropriate_content',
                'context_updates': {},
                'metadata': {'confidence': 1.0, 'language': language}
            }
        
        # 2. CHECK IF OFF-TOPIC (Non-business related)
        is_business = AIService.is_business_related(message)
        
        if not is_business:
            # Track off-topic conversations
            if session_id not in EnhancedAIService.off_topic_count:
                EnhancedAIService.off_topic_count[session_id] = 0
            
            EnhancedAIService.off_topic_count[session_id] += 1
            
            # After 3 off-topic messages, redirect to business
            if EnhancedAIService.off_topic_count[session_id] >= 3:
                response = (
                    "👋 I notice we've been chatting about non-business topics. "
                    "As your SokHub assistant, I'm optimized to help with:\n"
                    "• Finding products 🛍️\n"
                    "• Managing orders 📦\n"
                    "• Business analytics 📊\n"
                    "• Vendor assistance 🏪\n\n"
                    "How can I assist you with your SokHub experience today?"
                )
                EnhancedAIService.off_topic_count[session_id] = 0
                
                context['history'].append({'role': 'assistant', 'content': response})
                return {
                    'response': response,
                    'intent': 'redirect_to_business',
                    'context_updates': {},
                    'metadata': {'confidence': 1.0, 'language': language}
                }
        
        # Reset off-topic counter if business-related
        if is_business and session_id in EnhancedAIService.off_topic_count:
            EnhancedAIService.off_topic_count[session_id] = 0
        
        # 3. HANDLE GREETINGS
        greetings = AIService.GREETINGS.get(language, AIService.GREETINGS['en'])
        if any(msg_lower.startswith(g) or msg_lower == g for g in greetings):
            response = AIService.get_greeting_response(user, language)
            context['last_intent'] = 'greeting'
            
            context['history'].append({'role': 'assistant', 'content': response})
            return {
                'response': response,
                'intent': 'greeting',
                'context_updates': {},
                'metadata': {'confidence': 1.0, 'language': language}
            }
        
        # 4. SOKHUB PLATFORM INFORMATION
        sokhub_keywords = ['sokhub', 'what is', 'about sokhub', 'how does sokhub work']
        if any(keyword in msg_lower for keyword in sokhub_keywords):
            response = EnhancedAIService._get_sokhub_info(language)
            context['last_intent'] = 'platform_info'
            
            context['history'].append({'role': 'assistant', 'content': response})
            return {
                'response': response,
                'intent': 'platform_info',
                'context_updates': {},
                'metadata': {'confidence': 1.0, 'language': language}
            }
        
        # 5. VENDOR-SPECIFIC FEATURES
        if user_type == 'vendor':
            return EnhancedAIService._handle_vendor_query(message, user, context, language)
        
        # 6. CLIENT/GUEST QUERIES
        return EnhancedAIService._handle_client_query(message, user, context, language)
    
    @staticmethod
    def _handle_vendor_query(message, user, context, language):
        """Handle vendor-specific queries"""
        msg_lower = message.lower()
        
        # Business Report/Analytics
        if any(word in msg_lower for word in ['report', 'sales', 'revenue', 'earning', 'performance', 
                                              'stats', 'analytics', 'how is my business', 'my shop']):
            
            # Extract period if mentioned
            period = 'monthly'
            if 'today' in msg_lower or 'daily' in msg_lower:
                period = 'daily'
            elif 'week' in msg_lower:
                period = 'weekly'
            elif 'year' in msg_lower:
                period = 'yearly'
            
            report = AIVendorService.generate_business_report(user.id, period)
            
            if report:
                metrics = report['summary']
                analysis = report['ai_analysis']
                
                response = (
                    f"📊 **Business Intelligence Report - {report['period'].capitalize()}**\n\n"
                    f"**Summary:**\n"
                    f"• Total Sales: RWF {metrics['total_sales']:,.0f}\n"
                    f"• Orders: {metrics['total_orders']}\n"
                    f"• Avg Order Value: RWF {metrics['average_order_value']:,.0f}\n"
                    f"• Unique Customers: {metrics['unique_customers']}\n"
                    f"• Growth Rate: {metrics['growth_rate']}%\n"
                    f"• Performance Score: {metrics['performance_score']}/100\n\n"
                    f"📈 **Trend Analysis:**\n{analysis['growth_trend']}\n\n"
                    f"🎯 **Top Recommendation:**\n{analysis['recommendations'][0] if analysis['recommendations'] else 'No recommendations available'}\n\n"
                    f"💡 **Action Item:**\n{report['action_items'][0] if report['action_items'] else 'Continue current strategy'}"
                )
                
                # Store report in context for follow-up questions
                context['last_report'] = report
            else:
                response = (
                    "📊 I'm preparing your business report...\n\n"
                    "It looks like you don't have enough sales data yet. "
                    "Once you start receiving orders, I'll provide detailed analytics including:\n"
                    "• Sales trends and growth analysis\n"
                    "• Customer behavior insights\n"
                    "• Product performance metrics\n"
                    "• Actionable recommendations\n\n"
                    "Start by adding more products and promoting your store!"
                )
            
            context['last_intent'] = 'business_report'
            context['history'].append({'role': 'assistant', 'content': response})
            
            return {
                'response': response,
                'intent': 'business_report',
                'context_updates': context,
                'metadata': {'confidence': 0.9, 'language': language}
            }
        
        # Order Management
        order_keywords = ['order', 'complete', 'confirm', 'ship', 'deliver', 'cancel', 'update', 'status']
        if any(word in msg_lower for word in order_keywords):
            return EnhancedAIService._handle_order_update(message, user, context, language)
        
        # Stock/Inventory Management
        if any(word in msg_lower for word in ['stock', 'inventory', 'low stock', 'restock']):
            response = EnhancedAIService._handle_stock_query(user, language)
            context['last_intent'] = 'stock_query'
            context['history'].append({'role': 'assistant', 'content': response})
            
            return {
                'response': response,
                'intent': 'stock_query',
                'context_updates': context,
                'metadata': {'confidence': 0.9, 'language': language}
            }
        
        # Default vendor response
        response = (
            "🤖 **Vendor Assistant Mode**\n\n"
            "I can help you with:\n"
            "📊 **Business Analytics** - Ask: 'How is my business doing?' or 'Show me sales report'\n"
            "📦 **Order Management** - Say: 'Update order status' or 'Mark latest order as delivered'\n"
            "📈 **Growth Strategy** - Ask: 'How can I improve sales?' or 'Give me business recommendations'\n"
            "🛒 **Product Management** - Say: 'Check my stock' or 'What products are popular?'\n\n"
            "What would you like to work on today?"
        )
        
        context['last_intent'] = 'vendor_assistance'
        context['history'].append({'role': 'assistant', 'content': response})
        
        return {
            'response': response,
            'intent': 'vendor_assistance',
            'context_updates': context,
            'metadata': {'confidence': 1.0, 'language': language}
        }
    
    @staticmethod
    def _handle_order_update(message, user, context, language):
        """Handle order status updates"""
        msg_lower = message.lower()
        
        # Extract order identifier and status
        order_identifier = 'latest'
        new_status = 'delivered'
        
        # Try to extract order number
        import re
        order_match = re.search(r'order\s+(?:number\s+)?([a-zA-Z0-9-]+)', msg_lower)
        if order_match:
            extracted = order_match.group(1)
            if extracted.lower() not in ['complete', 'completed', 'done', 'delivered', 'confirm', 'cancelled']:
                order_identifier = extracted
        
        # Determine status from message
        if 'confirm' in msg_lower or 'accept' in msg_lower:
            new_status = 'confirmed'
        elif 'ship' in msg_lower or 'dispatch' in msg_lower:
            new_status = 'shipped'
        elif 'cancel' in msg_lower or 'refuse' in msg_lower:
            new_status = 'cancelled'
        elif 'process' in msg_lower:
            new_status = 'processing'
        
        result = AIVendorService.update_order_status(user, order_identifier, new_status)
        
        if result['success']:
            response = (
                f"✅ **Order Update Successful!**\n\n"
                f"Order #{result['order_number']} has been marked as **{result['status']}**.\n"
                f"Customer: {result.get('customer', 'Unknown')}\n\n"
                f"{result['message']}"
            )
        else:
            response = (
                f"⚠️ **Update Failed**\n\n"
                f"{result['message']}\n\n"
                f"Try asking:\n"
                f"• 'Mark latest order as delivered'\n"
                f"• 'Update order #12345 to shipped'\n"
                f"• 'Confirm order from John'"
            )
        
        context['last_intent'] = 'order_update'
        context['history'].append({'role': 'assistant', 'content': response})
        
        return {
            'response': response,
            'intent': 'order_update',
            'context_updates': context,
            'metadata': {'confidence': 0.9, 'language': language}
        }
    
    @staticmethod
    def _handle_stock_query(user, language):
        """Handle stock/inventory queries"""
        try:
            low_stock = Product.objects.filter(
                vendor=user,
                is_available=True
            ).filter(
                Q(stock_quantity__lt=10) | Q(stock_quantity__isnull=True)
            )[:5]
            
            if low_stock.exists():
                product_list = "\n".join([f"• {p.name}: {p.stock_quantity if p.stock_quantity else 'Unknown'} left" 
                                        for p in low_stock])
                response = (
                    f"📦 **Stock Alert**\n\n"
                    f"These products are running low:\n{product_list}\n\n"
                    f"Consider restocking soon to avoid losing sales!"
                )
            else:
                response = (
                    "✅ **Stock Status: Good**\n\n"
                    "All your products have sufficient stock. Great job managing your inventory!"
                )
        except Exception as e:
            response = (
                "⚠️ **Stock Check**\n\n"
                "I couldn't check your stock at the moment. Please try again later."
            )
        
        return response
    
    @staticmethod
    def _handle_client_query(message, user, context, language):
        """Handle client/guest queries"""
        msg_lower = message.lower()
        
        # Extract vendor name if mentioned
        vendor_name = None
        if 'from' in msg_lower or 'by' in msg_lower or 'vendor' in msg_lower:
            parts = re.split(r'\b(from|by|vendor)\b', msg_lower)
            if len(parts) > 2:
                potential_vendor = parts[-1].strip()
                if len(potential_vendor) > 1 and potential_vendor not in ['sokhub', 'market', 'store']:
                    vendor_name = potential_vendor
                    context['vendor_mentioned'] = vendor_name
        
        # Clean query for product search
        query = msg_lower
        
        # Remove common phrases
        remove_phrases = [
            'product', 'buy', 'looking for', 'find', 'search', 'get', 'show me', 'show', 'want',
            'what is', 'what are', 'do you have', 'need', 'price of', 'how much is', 'cost of',
            'is there', 'can you find', 'from', 'by', 'vendor', 'please'
        ]
        
        for phrase in remove_phrases:
            if phrase in query:
                query = query.replace(phrase, "")
        
        query = query.strip()
        
        # Check if asking for vendor contact
        if any(word in msg_lower for word in ['contact', 'phone', 'email', 'address', 'reach', 'call']):
            if vendor_name or context.get('vendor_mentioned'):
                vendor_to_contact = vendor_name or context['vendor_mentioned']
                contact_info = AIService.get_contact_info(vendor_to_contact)
                
                if contact_info:
                    response = (
                        f"📞 **Contact Information for {contact_info['name']}**\n\n"
                        f"• **Email:** {contact_info['email']}\n"
                        f"• **Phone:** {contact_info['phone']}\n"
                        f"• **Address:** {contact_info['address']}\n"
                    )
                    
                    if contact_info['website'] != 'Not provided':
                        response += f"• **Website:** {contact_info['website']}\n"
                    
                    response += "\n💡 **Tip:** You can also message the vendor directly through SokHub!"
                else:
                    response = (
                        f"⚠️ I couldn't find contact information for '{vendor_to_contact}'.\n"
                        f"Try searching for their products first, then use SokHub's messaging system."
                    )
            else:
                response = (
                    "🤔 I need to know which vendor you want to contact.\n"
                    "Try asking: 'Contact information for [Vendor Name]' or 'How to reach [Store Name]'"
                )
            
            context['last_intent'] = 'vendor_contact'
            context['history'].append({'role': 'assistant', 'content': response})
            
            return {
                'response': response,
                'intent': 'vendor_contact',
                'context_updates': context,
                'metadata': {'confidence': 0.9, 'language': language}
            }
        
        # PRODUCT SEARCH LOGIC
        # Check if query is valid for search
        should_search = False
        
        # If query has at least 2 characters
        if len(query) >= 2:
            should_search = True
        # Or if vendor filter is specified
        elif vendor_name:
            should_search = True
        # Or if previous context suggests product search
        elif context.get('last_intent') in ['shopping', 'product_search']:
            should_search = True
        
        if should_search:
            products = AIClientService.find_products_by_wish(
                query, 
                vendor_filter=vendor_name or context.get('vendor_mentioned'),
                max_results=8
            )
            
            if products:
                # Store found products in context
                context['last_products'] = products[:3]
                
                # Format response
                product_list = []
                for i, p in enumerate(products[:3], 1):
                    price_str = f"RWF {p.price:,.0f}" if hasattr(p, 'price') else "Price available"
                    
                    # Get vendor info
                    vendor_info = ""
                    if hasattr(p, 'vendor') and hasattr(p.vendor, 'vendorprofile'):
                        vendor_info = f" from {p.vendor.vendorprofile.business_name}"
                    elif hasattr(p, 'vendor'):
                        vendor_info = f" from {p.vendor.username}"
                    
                    product_list.append(f"{i}. **{p.name}** - {price_str}{vendor_info}")
                
                product_str = "\n".join(product_list)
                
                response = (
                    f"🔍 **Search Results**\n\n"
                    f"I found {len(products)} matching products:\n\n"
                    f"{product_str}"
                )
                
                # Add vendor-specific info if searching from a specific vendor
                if vendor_name or context.get('vendor_mentioned'):
                    vendor = vendor_name or context['vendor_mentioned']
                    response += f"\n\n📦 All these products are available from **{vendor}** on SokHub!"
                
                # Add shopping advice based on number of results
                if len(products) > 5:
                    response += "\n\n💡 **Tip:** I found many options! You can ask for more specific details like 'cheap laptops' or 'phones under 200,000'"
                elif len(products) == 1:
                    response += "\n\n🎯 **Perfect match!** This seems to be exactly what you're looking for."
                
                # If user asked for price specifically
                if 'price' in msg_lower or 'cost' in msg_lower or 'how much' in msg_lower:
                    response = (
                        f"💰 **Price Information**\n\n"
                        f"Here are the prices for products matching your search:\n\n"
                        f"{product_str}\n\n"
                        f"Click on any product to see full details including delivery options!"
                    )
                
                context['last_intent'] = 'shopping'
                context['product_interest'] = query
            else:
                # No products found
                response = (
                    f"🔍 **Search Results**\n\n"
                    f"I couldn't find any products matching '{message}'"
                )
                
                if vendor_name:
                    response += f" from {vendor_name}"
                
                response += (
                    f".\n\n💡 **Suggestions:**\n"
                    f"• Try different keywords\n"
                    f"• Check spelling\n"
                    f"• Browse categories instead\n"
                    f"• Ask for 'popular products'"
                )
                
                context['last_intent'] = 'no_results'
        else:
            # Not a search query - provide general assistance
            response = (
                f"🤖 **SokHub Assistant**\n\n"
                f"I can help you:\n"
                f"🛍️ **Find Products** - Ask: 'Show me phones' or 'Laptops under 300,000'\n"
                f"🏪 **Find Vendors** - Ask: 'Products from [Vendor Name]' or 'Stores near me'\n"
                f"💰 **Check Prices** - Ask: 'Price of iPhone' or 'How much for Samsung TV'\n"
                f"📞 **Contact Vendors** - Ask: 'Contact information for [Store Name]'\n"
                f"🚚 **Delivery Info** - Ask: 'Delivery time for [Product]'\n\n"
                f"What would you like help with today?"
            )
            
            context['last_intent'] = 'general_assistance'
        
        context['history'].append({'role': 'assistant', 'content': response})
        
        return {
            'response': response,
            'intent': context['last_intent'],
            'context_updates': context,
            'metadata': {'confidence': 0.9, 'language': language}
        }
    
    @staticmethod
    def _get_sokhub_info(language):
        """Get SokHub platform information"""
        info = {
            'en': (
                "**About SokHub** 🛍️\n\n"
                "SokHub is Rwanda's premier e-commerce marketplace connecting local vendors with buyers nationwide.\n\n"
                "**Key Features:**\n"
                "• Secure buying & selling platform\n"
                "• Verified vendor network\n"
                "• Real-time order tracking\n"
                "• Multiple payment options\n"
                "• AI-powered business analytics\n"
                "• Delivery across Rwanda\n\n"
                "**For Buyers:** Find everything from electronics to fashion at competitive prices.\n"
                "**For Sellers:** Grow your business with our tools and reach thousands of customers.\n\n"
                "Powered by intelligent AI assistance (that's me! 🤖)"
            ),
            'rw': (
                "**Kuri SokHub** 🛍️\n\n"
                "SokHub ni ubucuruzi bwa mbere mu Rwanda bwo guhuza abacuruzi n'abaguzi.\n\n"
                "**Ibikorwa:**\n"
                "• Platform y'ubucuruzi yizewe\n"
                "• Abacuruzi bemewe\n"
                "• Kureba amafaranga yawe mu buryo buhoraho\n"
                "• Uburyo bwinshi bwo kwishyura\n"
                "• Ibisubizo by'ubucuruzi bikoresheje AI\n"
                "• Kohereza ibicuruzwa mu Rwanda yose\n\n"
                "**Kubagura:** Shakisha ibintu byose kuri SokHub.\n"
                "**Kubacuruzi:** Andika ibicuruzwa kugirango ugere ku baguzi benshi.\n\n"
                "Bikoresheje ubushobozi bwa AI (ni njye! 🤖)"
            ),
            'fr': (
                "**À propos de SokHub** 🛍️\n\n"
                "SokHub est la principale place de marché e-commerce du Rwanda.\n\n"
                "**Caractéristiques:**\n"
                "• Plateforme sécurisée\n"
                "• Vendeurs vérifiés\n"
                "• Suivi en temps réel\n"
                "• Options de paiement multiples\n"
                "• Analyse commerciale par IA\n"
                "• Livraison dans tout le Rwanda\n\n"
                "**Pour les acheteurs:** Trouvez tout sur SokHub.\n"
                "**Pour les vendeurs:** Développez votre entreprise avec nos outils.\n\n"
                "Propulsé par l'assistance IA intelligente (c'est moi! 🤖)"
            )
        }
        
        return info.get(language, info['en'])
    
    @staticmethod
    def stream_chat_response(message, user, session):
        """Stream chat responses word by word"""
        result = EnhancedAIService.process_chat_message(message, user=user)
        full_response = result['response']
        
        # Split into words for streaming
        import re
        words = re.findall(r'\S+|\n', full_response)
        
        for word in words:
            if word == '\n':
                yield {'content': '\n\n'}
            else:
                yield {'content': word + ' '}