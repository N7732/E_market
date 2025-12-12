import random
from django.core.management.base import BaseCommand
from product.models import Product
from django.utils import timezone
from django.db.models import Count
from product.models import Product, ProductImage,ProductAnalytics
class Command(BaseCommand):

    help = 'Generate analytics report for products'

    def handle(self, *args, **kwargs):
        total_products = Product.objects.count()
        products_added_last_month = Product.objects.filter(
            created_at__gte=timezone.now() - timezone.timedelta(days=30)
        ).count()
        top_categories = Product.objects.values('category__name').annotate(
            count=Count('id')
        ).order_by('-count')[:5]

        self.stdout.write(self.style.SUCCESS('Analytics Report'))
        self.stdout.write(f'Total Products: {total_products}')
        self.stdout.write(f'Products Added in Last 30 Days: {products_added_last_month}')
        self.stdout.write('Top 5 Categories:')
        for category in top_categories:
            self.stdout.write(f"- {category['category__name']}: {category['count']} products")
        
        # Simulate sales data for demonstration
        self.stdout.write('Top 5 Selling Products (Simulated Data):')
        for _ in range(5):
            product = random.choice(Product.objects.all())
            sales_count = random.randint(10, 100)
            self.stdout.write(f"- {product.name}: {sales_count} sales")

            # Store or log analytics data for vendor dashboard
            ProductAnalytics.objects.create(
                product=product,
                sales_count=product.purchase_count,
                report_date=timezone.now().date()
            )