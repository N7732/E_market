"""AIVendorService used by service.py

Provides real business analytics for vendors.
"""
from datetime import datetime, timedelta
from typing import Dict, Any
from django.db.models import Sum, Count, F, Avg
from django.utils import timezone

# Try imports
try:
    from order.models import Order, OrderItem
    from product.models import Product
except ImportError:
    pass

class AIVendorService:
    @staticmethod
    def generate_business_report(user_id: int, period: str = 'monthly') -> Dict[str, Any]:
        """Generate a real business report for the vendor."""
        
        try:
            # Date range
            now = timezone.now()
            if period == 'daily':
                start_date = now - timedelta(days=1)
            elif period == 'weekly':
                start_date = now - timedelta(days=7)
            else: # monthly
                start_date = now - timedelta(days=30)
            
            # 1. Sales Overview (From Orders)
            # We look at Confirmed/Delivered orders
            orders = Order.objects.filter(
                vendor__id=user_id,
                created_at__gte=start_date,
                status__in=['confirmed', 'processing', 'shipped', 'delivered']
            )
            
            total_sales = orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
            order_count = orders.count()
            avg_order_value = total_sales / order_count if order_count > 0 else 0
            
            # 2. Product Performance (From OrderItems)
            # Find best selling products
            top_products_qs = OrderItem.objects.filter(
                vendor__id=user_id,
                order__created_at__gte=start_date,
                order__status__in=['confirmed', 'processing', 'shipped', 'delivered']
            ).values(
                'product__name'
            ).annotate(
                total_qty=Sum('quantity'),
                total_revenue=Sum('total_price')
            ).order_by('-total_revenue')[:5]
            
            top_products = []
            for p in top_products_qs:
                top_products.append({
                    'name': p['product__name'],
                    'qty': p['total_qty'],
                    'revenue': float(p['total_revenue'])
                })

            # 3. Inventory Health
            products = Product.objects.filter(vendor__id=user_id)
            low_stock_count = products.filter(quantity__lte=5).count()
            
            return {
                'type': 'vendor_report',
                'user_id': user_id,
                'period': period,
                'generated_at': now.isoformat(),
                'summary': {
                    'total_sales': float(total_sales),
                    'orders': order_count,
                    'average_order_value': float(avg_order_value),
                    'low_stock_products': low_stock_count,
                    'top_products': top_products
                },
                'message': AIVendorService._format_report_message(period, total_sales, order_count, top_products)
            }
            
        except Exception as e:
            print(f"Report generation error: {e}")
            return {
                'type': 'error',
                'message': f"Could not generate report: {str(e)}",
                'summary': {}
            }

    @staticmethod
    def _format_report_message(period, sales, orders, top_products):
        """Format a readable message for the report"""
        
        period_map = {'daily': 'Last 24 Hours', 'weekly': 'Last 7 Days', 'monthly': 'Last 30 Days'}
        period_str = period_map.get(period, period)
        
        msg = [f"📊 **Business Report ({period_str})**\n"]
        msg.append(f"💰 **Revenue:** RWF {sales:,.0f}")
        msg.append(f"📦 **Orders:** {orders}")
        
        if top_products:
            msg.append("\n🏆 **Top Products:**")
            for i, p in enumerate(top_products, 1):
                msg.append(f"{i}. {p['name']} ({p['qty']} sold)")
        else:
            msg.append("\nNo sales recorded in this period.")
            
        return "\n".join(msg)

__all__ = ['AIVendorService']
