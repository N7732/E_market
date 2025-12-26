from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Count, Sum, F, Q

from product.models import Product, ProductAnalytics


class Command(BaseCommand):

    help = 'Generate analytics report for products'

    def handle(self, *args, **kwargs):
        """
        Generate analytics using real numbers (no simulated data):
        - Totals: products, new products in last 30 days
        - Units sold + revenue derived from price * purchase_count
        - Top categories by units sold
        - Top products by units sold and revenue
        - Persist a per-product daily snapshot in ProductAnalytics
        """

        today = timezone.now().date()
        products_qs = Product.objects.all()

        total_products = products_qs.count()
        products_added_last_month = products_qs.filter(
            created_at__gte=timezone.now() - timezone.timedelta(days=30)
        ).count()

        totals = products_qs.aggregate(
            total_units_sold=Sum('purchase_count', default=0),
            total_revenue=Sum(F('price') * F('purchase_count'), default=0),
            active_products=Count('id', filter=Q(status='active', is_available=True)),
        )

        top_categories = products_qs.values('category__name').annotate(
            count=Count('id'),
            units_sold=Sum('purchase_count'),
            revenue=Sum(F('price') * F('purchase_count')),
        ).order_by('-units_sold', '-revenue')[:5]

        top_products = products_qs.annotate(
            revenue=F('price') * F('purchase_count')
        ).order_by('-purchase_count', '-revenue')[:5]

        # Output summary
        self.stdout.write(self.style.SUCCESS('Analytics Report'))
        self.stdout.write(f'Total Products: {total_products}')
        self.stdout.write(f'Active Products: {totals["active_products"] or 0}')
        self.stdout.write(f'Products Added in Last 30 Days: {products_added_last_month}')
        self.stdout.write(f'Total Units Sold: {totals["total_units_sold"] or 0}')
        self.stdout.write(f'Total Revenue (RWF): {totals["total_revenue"] or 0}')

        self.stdout.write('\nTop 5 Categories (by units sold):')
        for category in top_categories:
            name = category['category__name'] or 'Uncategorized'
            units = category['units_sold'] or 0
            revenue = category['revenue'] or 0
            self.stdout.write(f"- {name}: {units} units, {revenue} RWF revenue")

        self.stdout.write('\nTop 5 Products (by units sold):')
        if top_products:
            for product in top_products:
                self.stdout.write(
                    f"- {product.name}: {product.purchase_count} units, {product.revenue} RWF"
                )
        else:
            self.stdout.write("- No product data available yet.")

        # Persist daily snapshot for dashboard use
        for product in products_qs:
            ProductAnalytics.objects.update_or_create(
                product=product,
                report_date=today,
                defaults={'sales_count': product.purchase_count},
            )

        self.stdout.write(self.style.SUCCESS("Analytics snapshot saved to ProductAnalytics."))