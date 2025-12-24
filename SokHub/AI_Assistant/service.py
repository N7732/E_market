# services.py - Add AI services
import requests
from django.conf import settings
from .security import AIAssistantPermissions
from .models import Product, Store, Order, Vendor

class AIClientService:
    """AI services for clients"""
    
    @staticmethod
    def find_products_by_wish(client_wish, user_location=None):
        """
        Find products based on client's wish
        Args:
            client_wish (str): Client's description of desired product
            user_location (tuple): (latitude, longitude) optional
        """
        # 1. Analyze client wish using NLP
        keywords = AIService._extract_keywords(client_wish)
        
        # 2. Search products
        products = Product.objects.filter(
            name__icontains=keywords[0] if keywords else '',
            is_available=True
        )
        
        # 3. Filter by location if provided
        if user_location:
            products = AIService._filter_by_location(products, user_location)
        
        # 4. Rank results
        ranked_products = AIService._rank_products(products, keywords)
        
        return ranked_products
    
    @staticmethod
    def find_nearby_stores(user_location, radius_km=5):
        """Find stores near client's location"""
        from geopy.distance import geodesic
        
        stores = Store.objects.all()
        nearby_stores = []
        
        for store in stores:
            if store.location:
                store_loc = (store.location.latitude, store.location.longitude)
                distance = geodesic(user_location, store_loc).km
                
                if distance <= radius_km:
                    store.distance = distance
                    nearby_stores.append(store)
        
        return sorted(nearby_stores, key=lambda x: x.distance)

class AIVendorService:
    """AI services for vendors"""
    
    @staticmethod
    def generate_business_report(vendor_id, period='monthly'):
        """
        Generate AI analysis of vendor's business
        Args:
            vendor_id: Vendor's ID
            period: 'daily', 'weekly', 'monthly'
        """
        vendor = Vendor.objects.get(id=vendor_id)
        
        # Get sales data
        orders = Order.objects.filter(
            vendor=vendor,
            created_at__gte=AIService._get_period_start(period)
        )
        
        # Calculate metrics
        total_sales = sum(order.total_price for order in orders)
        total_orders = orders.count()
        popular_products = AIService._get_popular_products(orders)
        
        # AI Analysis
        analysis = {
            'performance_score': AIService._calculate_performance_score(orders),
            'trend': AIService._analyze_sales_trend(orders),
            'recommendations': AIService._generate_recommendations(vendor, orders),
            'customer_insights': AIService._analyze_customer_behavior(orders),
            'forecast': AIService._sales_forecast(orders)
        }
        
        return {
            'vendor': vendor.name,
            'period': period,
            'metrics': {
                'total_sales': total_sales,
                'total_orders': total_orders,
                'average_order_value': total_sales / total_orders if total_orders > 0 else 0,
            },
            'popular_products': popular_products,
            'ai_analysis': analysis
        }
    
    @staticmethod
    def calculate_delivery_distance(vendor_id, client_location):
        """Calculate road distance to client"""
        from geopy.distance import geodesic
        
        vendor = Vendor.objects.get(id=vendor_id)
        
        if vendor.store.location and client_location:
            # Simple geodesic distance (straight line)
            straight_distance = geodesic(
                (vendor.store.location.latitude, vendor.store.location.longitude),
                client_location
            ).km
            
            # Estimate road distance (add 20% for road curvature)
            estimated_road_distance = straight_distance * 1.2
            
            return {
                'straight_distance_km': round(straight_distance, 2),
                'estimated_road_distance_km': round(estimated_road_distance, 2),
                'estimated_delivery_time_min': round(estimated_road_distance * 2)  # Assuming 30km/h average
            }
        
        return None

class AIService:
    """Common AI utilities"""
    
    @staticmethod
    def _extract_keywords(text):
        """Simple keyword extraction (can be enhanced with NLP)"""
        # Remove common words
        stop_words = ['i', 'want', 'need', 'looking', 'for', 'a', 'an', 'the']
        words = text.lower().split()
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        
        return keywords[:5]  # Return top 5 keywords
    
    @staticmethod
    def _filter_by_location(products, user_location, max_distance_km=10):
        """Filter products by store location"""
        from geopy.distance import geodesic
        
        filtered_products = []
        
        for product in products:
            if product.store and product.store.location:
                store_loc = (product.store.location.latitude, product.store.location.longitude)
                distance = geodesic(user_location, store_loc).km
                
                if distance <= max_distance_km:
                    product.distance = distance
                    filtered_products.append(product)
        
        return filtered_products
    
    @staticmethod
    def _rank_products(products, keywords):
        """Rank products based on relevance to keywords"""
        ranked = []
        
        for product in products:
            score = 0
            
            # Check keyword matches in product name and description
            for keyword in keywords:
                if keyword in product.name.lower():
                    score += 3
                if product.description and keyword in product.description.lower():
                    score += 1
            
            # Consider distance if available
            if hasattr(product, 'distance'):
                score += max(0, 10 - product.distance) / 2  # Closer = higher score
            
            ranked.append((product, score))
        
        # Sort by score descending
        ranked.sort(key=lambda x: x[1], reverse=True)
        
        return [item[0] for item in ranked]
    
# Update services.py
from .mapping_service import mapping_service

class EnhancedAIVendorService:
    """Vendor service with accurate mapping"""
    
    @staticmethod
    def calculate_delivery_details(vendor_id, client_location, mode='driving'):
        """Calculate accurate delivery distance and time"""
        vendor = Vendor.objects.get(id=vendor_id)
        
        if vendor.store and vendor.store.location:
            store_location = (vendor.store.location.latitude, 
                            vendor.store.location.longitude)
            
            # Get accurate road distance
            distance_info = mapping_service.calculate_road_distance(
                store_location, 
                client_location, 
                mode
            )
            
            # Calculate delivery cost
            delivery_cost = EnhancedAIVendorService._calculate_delivery_cost(
                distance_info['distance_meters'],
                mode
            )
            
            # Estimate delivery time with traffic
            delivery_time = EnhancedAIVendorService._estimate_delivery_time(
                distance_info['duration_seconds'],
                mode
            )
            
            return {
                **distance_info,
                'delivery_cost': delivery_cost,
                'delivery_time_window': delivery_time,
                'suggested_delivery_slots': EnhancedAIVendorService._get_delivery_slots(),
                'alternative_routes': EnhancedAIVendorService._get_alternative_routes(
                    store_location, 
                    client_location
                )
            }
        
        return None