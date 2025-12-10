# products/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Avg, F
from django.core.paginator import Paginator
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse, HttpResponseForbidden
from django.db import transaction
from django.views.decorators.http import require_POST
import json

from customer.Decorator import vendor_required, customer_required
from .models import Product, Category, ProductReview, StockHistory
from .form import ProductForm, ProductSearchForm, ProductReviewForm, StockAdjustmentForm

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
        ).select_related('vendor', 'category').prefetch_related('images')
        
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
                    Q(category__name__icontains=q) |
                    Q(tags__name__icontains=q)
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
        obj.increment_view_count()
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
        
        # Review form for authenticated customers
        review_form = None
        if self.request.user.is_authenticated and self.request.user.user_type == 'customer':
            # Check if user has already reviewed
            has_reviewed = reviews.filter(customer=self.request.user).exists()
            if not has_reviewed:
                review_form = ProductReviewForm(
                    product=product,
                    customer=self.request.user
                )
        
        context.update({
            'related_products': related_products,
            'reviews': reviews,
            'review_form': review_form,
            'has_reviewed': reviews.filter(customer=self.request.user).exists() if self.request.user.is_authenticated else False,
            'can_review': self.request.user.is_authenticated and 
                         self.request.user.user_type == 'customer' and
                         not reviews.filter(customer=self.request.user).exists(),
        })
        
        return context

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
        quantity__gt=0
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
    
    return render(request, 'products/vendor_product_list.html', context)

@login_required
@vendor_required
def vendor_add_product(request):
    """Vendor add product form"""
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, vendor=request.user)
        if form.is_valid():
            product = form.save()
            messages.success(request, f'Product "{product.name}" added successfully! It will be reviewed before going live.')
            return redirect('vendor_product_list')
    else:
        form = ProductForm(vendor=request.user)
    
    return render(request, 'products/vendor_add_product.html', {'form': form})

@login_required
@vendor_required
def vendor_edit_product(request, pk):
    """Vendor edit product form"""
    product = get_object_or_404(Product, pk=pk, vendor=request.user)
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product, vendor=request.user)
        if form.is_valid():
            product = form.save()
            messages.success(request, f'Product "{product.name}" updated successfully!')
            return redirect('vendor_product_list')
    else:
        form = ProductForm(instance=product, vendor=request.user)
    
    return render(request, 'products/vendor_edit_product.html', {'form': form, 'product': product})

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
    
    return render(request, 'products/vendor_delete_product.html', {'product': product})

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
            
            with transaction.atomic():
                if adjustment_type == 'add':
                    product.restock(quantity)
                    action = 'adjustment'
                    quantity_change = quantity
                elif adjustment_type == 'remove':
                    if product.quantity >= quantity:
                        product.quantity = F('quantity') - quantity
                        product.save()
                        action = 'adjustment'
                        quantity_change = -quantity
                    else:
                        messages.error(request, 'Cannot remove more stock than available.')
                        return redirect('vendor_stock_management', pk=pk)
                else:  # set
                    old_quantity = product.quantity
                    product.quantity = quantity
                    product.save()
                    action = 'adjustment'
                    quantity_change = quantity - old_quantity
                
                # Create stock history
                StockHistory.objects.create(
                    product=product,
                    action=action,
                    quantity_change=quantity_change,
                    new_quantity=product.quantity,
                    notes=notes,
                    performed_by=request.user
                )
                
                messages.success(request, f'Stock updated successfully!')
                return redirect('vendor_product_list')
    else:
        form = StockAdjustmentForm()
    
    # Get stock history
    stock_history = StockHistory.objects.filter(product=product).order_by('-created_at')[:20]
    
    context = {
        'product': product,
        'form': form,
        'stock_history': stock_history,
    }
    
    return render(request, 'products/vendor_stock_management.html', context)

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
            
            # Check if customer has purchased the product (for verified purchase)
            # This would query the orders app
            review.is_verified_purchase = False  # Implement order check
            
            review.save()
            messages.success(request, 'Thank you for your review! It will be visible after approval.')
            return redirect('product_detail', slug=product.slug)
    else:
        form = ProductReviewForm(product=product, customer=request.user)
    
    return render(request, 'products/add_review.html', {'form': form, 'product': product})

@require_POST
@login_required
def toggle_wishlist(request, pk):
    """Add/remove product from wishlist"""
    if request.user.user_type != 'customer':
        return JsonResponse({'error': 'Only customers can use wishlist'}, status=403)
    
    product = get_object_or_404(Product, pk=pk)
    
    # This would use a Wishlist model
    # For now, return success
    return JsonResponse({'success': True})

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
    ).select_related('vendor', 'category').prefetch_related('images')
    
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

# API Views for AJAX
def product_availability_check(request, pk):
    """Check product availability (for AJAX)"""
    product = get_object_or_404(Product, pk=pk)
    
    data = {
        'available': product.is_in_stock(),
        'available_quantity': product.get_available_quantity(),
        'allow_backorder': product.allow_backorder,
        'message': ''
    }
    
    if not data['available']:
        if product.allow_backorder:
            data['message'] = 'Available for backorder'
        else:
            data['message'] = 'Out of stock'
    
    return JsonResponse(data)

@require_POST
@login_required
def reserve_stock(request, pk):
    """Reserve stock for cart (for AJAX)"""
    product = get_object_or_404(Product, pk=pk)
    quantity = int(request.POST.get('quantity', 1))
    
    if quantity <= 0:
        return JsonResponse({'success': False, 'error': 'Invalid quantity'})
    
    if product.reserve_stock(quantity):
        return JsonResponse({'success': True})
    else:
        return JsonResponse({
            'success': False, 
            'error': 'Not enough stock available',
            'available': product.get_available_quantity()
        })