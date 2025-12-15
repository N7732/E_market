# products/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Avg, F, Sum
from django.core.paginator import Paginator
from django.views.generic import ListView, DetailView
from django.http import JsonResponse
from django.db import transaction
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from customer.Decorator import vendor_required, customer_required
from .models import Product, Category, ProductReview, StockHistory
from .form import ProductForm, ProductSearchForm, ProductReviewForm, StockAdjustmentForm

# =========== PUBLIC VIEWS ===========
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
        
        # Apply search filters
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
                # Include products in subcategories
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
        # Increment view count
        obj.view_count = F('view_count') + 1
        obj.save(update_fields=['view_count'])
        obj.refresh_from_db()
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        
        # Get related products
        related_products = Product.objects.filter(
            category=product.category,
            status='active',
            is_available=True
        ).exclude(pk=product.pk)[:4]
        
        # Get approved reviews
        reviews = product.reviews.filter(is_approved=True).select_related('customer')
        
        context.update({
            'related_products': related_products,
            'reviews': reviews,
            'has_reviewed': reviews.filter(customer=self.request.user).exists() if self.request.user.is_authenticated else False,
            'can_review': self.request.user.is_authenticated and 
                         self.request.user.user_type == 'customer' and
                         not reviews.filter(customer=self.request.user).exists(),
            'rating_range': range(5, 0, -1),  # [5, 4, 3, 2, 1]
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
        form = ProductReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.product = product
            review.customer = request.user
            review.save()
            
            messages.success(request, 'Thank you for your review!')
            return redirect('product_detail', slug=product.slug)
    else:
        form = ProductReviewForm()
    
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
    
    context = {
        'page_obj': page_obj,
        'total_products': total_products,
        'active_products': active_products,
        'out_of_stock': out_of_stock,
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
@vendor_required
def vendor_delete_product(request, pk):
    """Vendor delete product"""
    product = get_object_or_404(Product, pk=pk, vendor=request.user)
    
    if request.method == 'POST':
        product_name = product.name
        product.delete()
        messages.success(request, f'Product "{product_name}" deleted successfully!')
        return redirect('vendor_product_list')
    
    return render(request, 'vendor/delete_product.html', {'product': product})

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
    
    total_sales = products.aggregate(
        total_revenue=Sum(F('price') * F('purchase_count'), default=0),
        total_orders=Sum('purchase_count', default=0),
        average_rating=Avg('average_rating', default=0)
    )
    
    top_selling_products = products.order_by('-purchase_count')[:5]
    
    context = {
        'total_sales': total_sales,
        'top_selling_products': top_selling_products,
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

# =========== HELPER FUNCTIONS ===========
def product_detail_api(request, product_id):
    """API endpoint for product details (used in AJAX overlay) - OPTIONAL"""
    try:
        product = Product.objects.get(id=product_id, status='active', is_available=True)
        
        product_data = {
            'id': product.id,
            'slug': product.slug,
            'name': product.name,
            'price': str(product.price),
            'compare_at_price': str(product.compare_at_price) if product.compare_at_price else None,
            'category': product.category.name if product.category else 'Uncategorized',
            'vendor': product.vendor.username,
            'description': product.description or 'No description available.',
            'main_image': product.main_image.url if product.main_image else '',
            'is_in_stock': product.is_in_stock(),
            'available_quantity': product.get_available_quantity(),
            'average_rating': float(product.average_rating) if product.average_rating else 0,
            'review_count': product.reviews.count(),
        }
        
        return JsonResponse({'success': True, 'product': product_data})
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Product not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

# Add this to product/views.py
@csrf_exempt
def product_detail_api(request, product_id):
    """API endpoint for product details overlay"""
    try:
        product = Product.objects.get(id=product_id, status='active', is_available=True)
        
        product_data = {
            'id': product.id,
            'slug': product.slug,
            'name': product.name,
            'price': str(product.price),
            'compare_at_price': str(product.compare_at_price) if product.compare_at_price else None,
            'category': product.category.name if product.category else 'Uncategorized',
            'vendor': product.vendor.vendorprofile.business_name if hasattr(product.vendor, 'vendorprofile') and product.vendor.vendorprofile.business_name else product.vendor.username,
            'description': product.description or 'No description available.',
            'main_image': product.main_image.url if product.main_image else '',
            'discount_percentage': product.get_discount_percentage() if hasattr(product, 'get_discount_percentage') else 0,
        }
        
        return JsonResponse({'success': True, 'product': product_data})
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Product not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})