# products/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Avg, F, Sum, Count
from django.core.paginator import Paginator
from django.views.generic import ListView, DetailView
from django.http import JsonResponse, HttpResponseForbidden
from django.db import transaction
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from customer.Decorator import vendor_required, customer_required
from .models import Product, Category, ProductReview, StockHistory
from .form import ProductForm, ProductSearchForm, ProductReviewForm, StockAdjustmentForm

# =========== PUBLIC VIEWS ===========

@login_required
def add_review(request, product_id):
    """Add a review for a product"""
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'POST':
        form = ProductReviewForm(request.POST, product=product, customer=request.user)
        if form.is_valid():
            review = form.save(commit=False)
            review.product = product
            review.customer = request.user
            review.save()
            return redirect('product_detail', slug=product.slug)
    else:
        form = ProductReviewForm(product=product, customer=request.user)
    
    return render(request, 'products/add_review.html', {
        'product': product,
        'form': form
    })

class ProductListView(ListView):
    """Public product listing page"""
    model = Product
    template_name = 'products/product_list.html'
    context_object_name = 'products'
    paginate_by = 12
    def get_queryset(self):
        queryset = Product.objects.filter(
            status='active', 
            is_available=True
        ).select_related('vendor', 'category')
        
        form = ProductSearchForm(self.request.GET)
        if form.is_valid():
            q = form.cleaned_data.get('q')
            category = form.cleaned_data.get('category')
            min_price = form.cleaned_data.get('min_price')
            max_price = form.cleaned_data.get('max_price')
            in_stock = form.cleaned_data.get('in_stock')
            sort_by = form.cleaned_data.get('sort_by')
            
            if q:
                queryset = queryset.filter(
                    Q(name__icontains=q) |
                    Q(description__icontains=q) |
                    Q(short_description__icontains=q) |
                    Q(category__name__icontains=q)
                ).distinct()
            
            if category:
                subcategories = category.get_all_children()
                category_ids = [category.id] + [c.id for c in subcategories]
                queryset = queryset.filter(category_id__in=category_ids)
            
            if min_price:
                queryset = queryset.filter(price__gte=min_price)
            
            if max_price:
                queryset = queryset.filter(price__lte=max_price)
            
            if in_stock:
                queryset = queryset.filter(
                    Q(is_track_inventory=False) |
                    Q(quantity__gt=0) |
                    Q(allow_backorder=True)
                )
            
            # Apply sorting
            if sort_by == 'price_low':
                queryset = queryset.order_by('price')
            elif sort_by == 'price_high':
                queryset = queryset.order_by('-price')
            elif sort_by == 'popular':
                queryset = queryset.order_by('-purchase_count')
            elif sort_by == 'rating':
                queryset = queryset.order_by('-average_rating')
            else:  # newest
                queryset = queryset.order_by('-published_at', '-created_at')
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_form'] = ProductSearchForm(self.request.GET)
        context['categories'] = Category.objects.filter(is_active=True, parent__isnull=True)
        context['featured_products'] = Product.objects.filter(
            status='active', 
            is_available=True,
            is_featured=True
        )[:8]
        return context

class ProductDetailView(DetailView):
    """Product detail page"""
    model = Product
    template_name = 'products/product_detail.html'
    context_object_name = 'product'
    
    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        obj.view_count = F('view_count') + 1
        obj.save(update_fields=['view_count'])
        obj.refresh_from_db()
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object
        
        # Get related products
        related_products = Product.objects.filter(
            category=product.category,
            status='active',
            is_available=True
        ).exclude(pk=product.pk)[:4]
        
        # Get approved reviews
        reviews = product.reviews.filter(is_approved=True).select_related('customer')
        
        # Basic previous/next navigation within active products
        base_filters = {'status': 'active', 'is_available': True}
        published_reference = product.published_at or product.created_at
        prev_product = Product.objects.filter(
            published_at__lt=published_reference,
            **base_filters
        ).order_by('-published_at', '-created_at').first()
        next_product = Product.objects.filter(
            published_at__gt=published_reference,
            **base_filters
        ).order_by('published_at', 'created_at').first()
        
        review_form = None
        if self.request.user.is_authenticated and getattr(self.request.user, 'user_type', None) == 'customer':
            review_form = ProductReviewForm(product=product, customer=self.request.user)
        
        user_has_review = False
        if self.request.user.is_authenticated:
            user_has_review = product.reviews.filter(customer=self.request.user).exists()
        
        context.update({
            'related_products': related_products,
            'reviews': reviews,
            'has_reviewed': user_has_review,
            'can_review': self.request.user.is_authenticated and 
                         self.request.user.user_type == 'customer' and
                         not user_has_review,
            'rating_range': range(5, 0, -1),  # [5, 4, 3, 2, 1]
            'prev_product': prev_product,
            'next_product': next_product,
            'review_form': review_form,
        })
        return context

def category_detail(request, slug):
    """Category page with products"""
    category = get_object_or_404(Category, slug=slug, is_active=True)
    
    # Get products in this category and subcategories
    subcategories = category.get_all_children()
    category_ids = [category.id] + [c.id for c in subcategories]
    
    products = Product.objects.filter(
        category_id__in=category_ids,
        status='active',
        is_available=True
    ).select_related('vendor', 'category')
    
    # Apply sorting
    sort_by = request.GET.get('sort', 'newest')
    if sort_by == 'price_low':
        products = products.order_by('price')
    elif sort_by == 'price_high':
        products = products.order_by('-price')
    elif sort_by == 'popular':
        products = products.order_by('-purchase_count')
    else:  # newest
        products = products.order_by('-published_at', '-created_at')
    
    # Pagination
    paginator = Paginator(products, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'category': category,
        'page_obj': page_obj,
        'sort_by': sort_by,
        'subcategories': subcategories,
    }
    
    return render(request, 'products/category_detail.html', context)

# =========== CUSTOMER VIEWS ===========
@login_required
@customer_required
def add_product_review(request, pk):
    """Customer adds a product review"""
    product = get_object_or_404(Product, pk=pk, status='active')
    
    # Check if user has already reviewed
    if product.reviews.filter(customer=request.user).exists():
        messages.error(request, 'You have already reviewed this product.')
        return redirect('product_detail', slug=product.slug)
    
    if request.method == 'POST':
        form = ProductReviewForm(request.POST, product=product, customer=request.user)
        if form.is_valid():
            review = form.save(commit=False)
            review.product = product
            review.customer = request.user
            review.save()
            
            messages.success(request, 'Thank you for your review!')
            return redirect('product_detail', slug=product.slug)
    else:
        form = ProductReviewForm(product=product, customer=request.user)
    
    return render(request, 'products/add_review.html', {'form': form, 'product': product})

# =========== VENDOR VIEWS ===========
@login_required
@vendor_required
def vendor_product_list(request):
    """Vendor's product management page"""
    products = Product.objects.filter(vendor=request.user).select_related('category')
    
    # Filter by status
    status_filter = request.GET.get('status')
    if status_filter:
        products = products.filter(status=status_filter)
    
    # Search
    search_query = request.GET.get('q')
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(sku__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(products, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistics
    total_products = products.count()
    active_products = products.filter(status='active').count()
    out_of_stock = products.filter(status='out_of_stock').count()
    low_stock = products.filter(
        is_track_inventory=True,
        quantity__lte=F('low_stock_threshold'),
        status='active'
    ).count()
    
    context = {
        'page_obj': page_obj,
        'total_products': total_products,
        'active_products': active_products,
        'out_of_stock': out_of_stock,
        'low_stock': low_stock,
        'status_filter': status_filter,
        'search_query': search_query,
    }
    
    return render(request, 'vendor/product_list.html', context)

@login_required
@vendor_required
def vendor_add_product(request):
    """Vendor add product form"""
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.vendor = request.user
            product.save()
            messages.success(request, f'Product "{product.name}" added successfully!')
            return redirect('vendor_product_list')
    else:
        form = ProductForm()
    
    return render(request, 'vendor/add_product.html', {'form': form})

@login_required
@vendor_required
def vendor_edit_product(request, pk):
    """Vendor edit product form"""
    product = get_object_or_404(Product, pk=pk, vendor=request.user)
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            product = form.save()
            messages.success(request, f'Product "{product.name}" updated successfully!')
            return redirect('vendor_product_list')
    else:
        form = ProductForm(instance=product)
    
    return render(request, 'vendor/edit_product.html', {'form': form, 'product': product})

@login_required
def vendor_delete_product(request, pk):
    """Allow vendors to remove their own products and admins to override"""
    product = get_object_or_404(Product, pk=pk)
    
    is_owner = request.user.user_type == 'vendor' and product.vendor == request.user
    is_admin = request.user.is_staff
    if not (is_owner or is_admin):
        return HttpResponseForbidden("You do not have permission to delete this product.")
    
    redirect_target = 'vendor_product_list' if is_owner else 'product_list'
    
    if request.method == 'POST':
        product_name = product.name
        product.delete()
        messages.success(request, f'Product "{product_name}" deleted successfully!')
        return redirect(redirect_target)
    
    return render(request, 'vendor/delete_product.html', {
        'product': product,
        'is_owner': is_owner,
        'redirect_target': redirect_target,
    })

@login_required
@vendor_required
def vendor_toggle_product_status(request, pk):
    """Allow vendors to publish/unpublish their products without admin help"""
    product = get_object_or_404(Product, pk=pk, vendor=request.user)
    
    if request.method != 'POST':
        messages.error(request, 'Invalid request.')
        return redirect('vendor_product_list')
    
    if product.status == 'active':
        product.status = 'draft'
        product.is_available = False
        message = f'Product "{product.name}" moved to draft.'
    else:
        if product.is_track_inventory and not product.allow_backorder and product.get_available_quantity() <= 0:
            messages.error(request, 'Cannot activate a product without available stock.')
            return redirect('vendor_product_list')
        product.status = 'active'
        product.is_available = True
        if not product.published_at:
            product.published_at = timezone.now()
        message = f'Product "{product.name}" is now active.'
    
    product.save(update_fields=['status', 'is_available', 'published_at'])
    messages.success(request, message)
    return redirect('vendor_product_list')

@login_required
@vendor_required
def vendor_stock_management(request, pk):
    """Vendor stock management for a product"""
    product = get_object_or_404(Product, pk=pk, vendor=request.user)
    
    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST)
        if form.is_valid():
            adjustment_type = form.cleaned_data['adjustment_type']
            quantity = form.cleaned_data['quantity']
            notes = form.cleaned_data['notes']
            
            try:
                with transaction.atomic():
                    old_quantity = product.quantity
                    
                    if adjustment_type == 'add':
                        product.quantity += quantity
                        quantity_change = quantity
                    elif adjustment_type == 'remove':
                        if product.quantity >= quantity:
                            product.quantity -= quantity
                            quantity_change = -quantity
                        else:
                            messages.error(request, 'Cannot remove more stock than available.')
                            return redirect('vendor_stock_management', pk=pk)
                    else:  # set
                        quantity_change = quantity - old_quantity
                        product.quantity = quantity
                    
                    product.save()
                    
                    # Create stock history
                    StockHistory.objects.create(
                        product=product,
                        action='adjustment',
                        quantity_change=quantity_change,
                        new_quantity=product.quantity,
                        notes=notes,
                        performed_by=request.user
                    )
                    
                    messages.success(request, 'Stock updated successfully!')
                    return redirect('vendor_product_list')
            except Exception as e:
                messages.error(request, f'Error updating stock: {str(e)}')
    else:
        form = StockAdjustmentForm()
    
    # Get stock history
    stock_history = StockHistory.objects.filter(product=product).order_by('-created_at')[:20]
    
    context = {
        'product': product,
        'form': form,
        'stock_history': stock_history,
    }
    
    return render(request, 'vendor/stock_management.html', context)

@login_required
@vendor_required
def vendor_analytics(request):
    """Vendor analytics dashboard"""
    # Aggregate sales data
    products = Product.objects.filter(vendor=request.user)
    
    totals = products.aggregate(
        total_revenue=Sum(F('price') * F('purchase_count'), default=0),
        total_orders=Sum('purchase_count', default=0),
        average_rating=Avg('average_rating', default=0),
        product_count=Count('id'),
    )
    
    top_selling_products = products.annotate(
        revenue=F('price') * F('purchase_count')
    ).order_by('-purchase_count', '-revenue')[:5]
    
    category_breakdown = products.values('category__name').annotate(
        units=Sum('purchase_count'),
        revenue=Sum(F('price') * F('purchase_count'))
    ).order_by('-units', '-revenue')
    
    total_revenue = totals.get('total_revenue') or 0
    total_orders = totals.get('total_orders') or 0
    avg_order_value = float(total_revenue) / float(total_orders) if total_orders else 0
    
    analytics_data = {
        'total_revenue': float(total_revenue),
        'total_orders': int(total_orders),
        'avg_order_value': float(avg_order_value),
        'average_rating': float(totals.get('average_rating') or 0),
        'product_count': int(totals.get('product_count') or 0),
        'top_products': [
            {
                'name': p.name,
                'units': int(p.purchase_count or 0),
                'revenue': float(p.revenue or 0),
                'image': p.main_image.url if p.main_image else '',
            } for p in top_selling_products
        ],
        'categories': [
            {
                'name': c['category__name'] or 'Uncategorized',
                'units': int(c['units'] or 0),
                'revenue': float(c['revenue'] or 0),
            } for c in category_breakdown
        ],
    }
    
    context = {
        'total_sales': totals,
        'top_selling_products': top_selling_products,
        'analytics_data': analytics_data,
    }
    return render(request, 'vendor/analytics.html', context)

# =========== API ENDPOINTS ===========
@csrf_exempt
def product_availability_check(request, pk):
    """Check product availability (for AJAX)"""
    product = get_object_or_404(Product, pk=pk)
    
    data = {
        'available': product.is_in_stock(),
        'available_quantity': product.get_available_quantity(),
        'allow_backorder': getattr(product, 'allow_backorder', False),
        'message': ''
    }
    
    if not data['available']:
        if data['allow_backorder']:
            data['message'] = 'Available for backorder'
        else:
            data['message'] = 'Out of stock'
    
    return JsonResponse(data)

@csrf_exempt
@require_POST
@login_required
def reserve_stock(request, pk):
    """Reserve stock for cart (for AJAX)"""
    product = get_object_or_404(Product, pk=pk)
    
    try:
        quantity = int(request.POST.get('quantity', 1))
        if quantity <= 0:
            return JsonResponse({'success': False, 'error': 'Invalid quantity'})
        
        # Simple stock reservation logic
        if product.is_in_stock() and quantity <= product.get_available_quantity():
            return JsonResponse({'success': True})
        else:
            return JsonResponse({
                'success': False, 
                'error': 'Not enough stock available',
                'available': product.get_available_quantity()
            })
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Invalid quantity format'})

@csrf_exempt
@require_POST
@login_required
def toggle_wishlist(request, pk):
    """Add/remove product from wishlist"""
    product = get_object_or_404(Product, pk=pk)
    
    # Simple wishlist toggle logic
    # You would need to implement Wishlist model
    return JsonResponse({'success': True, 'message': 'Wishlist updated'})