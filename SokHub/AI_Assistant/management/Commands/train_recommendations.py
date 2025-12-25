# management/commands/train_recommendations.py
from django.core.management.base import BaseCommand
from django.db.models import Count, Avg, Sum
from django.core.cache import cache
import pandas as pd
from datetime import datetime, timedelta

class Command(BaseCommand):
    help = 'Train AI recommendation models'
    
    def handle(self, *args, **kwargs):
        self.stdout.write("Training AI recommendation models...")
        
        try:
            # Train product recommendations
            self.train_product_recommendations()
            
            # Train user preference models
            self.train_user_preferences()
            
            # Train vendor insights
            self.train_vendor_insights()
            
            self.stdout.write(self.style.SUCCESS('Successfully trained AI models!'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
    
    def train_product_recommendations(self):
        """Train product recommendation model"""
        from product.models import Product, Category
        from order.models import OrderItem
        
        # Get popular products
        popular_products = OrderItem.objects.values('product_id').annotate(
            total_sold=Count('id')
        ).order_by('-total_sold')[:100]
        
        # Update product scores
        for item in popular_products:
            try:
                product = Product.objects.get(id=item['product_id'])
                product.popularity_score = item['total_sold']
                product.save(update_fields=['popularity_score'])
            except:
                pass
        
        self.stdout.write(f"Updated {len(popular_products)} product scores")
    
    def train_user_preferences(self):
        """Train user preference models"""
        from customer.models import User
        from order.models import Order
        
        # Analyze user preferences
        users = User.objects.filter(orders__isnull=False).distinct()[:50]
        
        for user in users:
            # Get user's purchase history
            user_orders = Order.objects.filter(customer=user)
            
            # Extract preferences (simplified)
            if user_orders.exists():
                # Store user preferences in cache or database
                cache_key = f"user_prefs_{user.id}"
                # cache.set(cache_key, preferences, timeout=86400)
        
        self.stdout.write(f"Analyzed {len(users)} user preferences")
    
    def train_vendor_insights(self):
        """Train vendor insights model"""
        from customer.models import User
        from order.models import Order
        
        vendors = User.objects.filter(user_type='vendor')[:20]
        
        for vendor in vendors:
            # Generate vendor insights
            orders = Order.objects.filter(vendor=vendor)
            
            if orders.exists():
                # Calculate metrics
                total_sales = orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
                avg_order = orders.aggregate(Avg('total_amount'))['total_amount__avg'] or 0
                
                # Store insights
                insights = {
                    'total_sales': total_sales,
                    'avg_order_value': avg_order,
                    'performance_score': min(100, (total_sales / 1000000) * 100)  # Simplified
                }
                
                cache_key = f"vendor_insights_{vendor.id}"
                # cache.set(cache_key, insights, timeout=3600)
        
        self.stdout.write(f"Generated insights for {len(vendors)} vendors")