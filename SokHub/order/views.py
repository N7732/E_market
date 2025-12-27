# orders/views.py
from datetime import timedelta
from decimal import Decimal
import uuid
import random
import string
import json
from django.forms import ValidationError
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import Http404, JsonResponse, HttpResponse
from django.views.decorators.http import require_POST, require_GET
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, F
from django.utils import timezone
from django.urls import reverse
from django.views.generic import DetailView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from customer.Decorator import customer_required, vendor_required, vendor_approved_required
from product.models import Product
from .models import Order, OrderItem, Cart, CartItem, OrderNotification, OrderStatusHistory
from .form import (
    CheckoutForm, CartItemForm, OrderStatusUpdateForm, 
    OrderDeletionRequestForm, OrderPaymentForm, 
    OrderFilterForm, VendorOrderFilterForm, BulkOrderUpdateForm
)
from django.db.models.functions import TruncMonth
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

# ==================== CART VIEWS ====================

@login_required
@customer_required
def cart_view(request):
    """Display the shopping cart"""
    cart = Cart.objects.filter(customer=request.user).first()
    cart_items = cart.items.all().select_related('product', 'product__vendor') if cart else []
    
    # Calculate totals
    subtotal = sum(item.get_total_price() for item in cart_items) if cart_items else 0
    shipping = 0 if subtotal > 50000 else 2500
    tax = subtotal * Decimal(0.18)
    total = subtotal + shipping + tax
    
    context = {
        'cart_items': cart_items,
        'cart_subtotal': subtotal,
        'cart_tax': tax,
        'cart_total': total,
        'cart_shipping': shipping,
        'cart_total_items': len(cart_items),
    }
    
    return render(request, 'orders/cart.html', context)

@login_required
@customer_required
def apply_coupon(request):
    """Apply discount coupon to cart"""
    if request.method == 'POST':
        coupon_code = request.POST.get('coupon_code')
        # Your coupon logic here
        return redirect('cart')
    return redirect('cart')

@require_POST
@login_required
@customer_required
def cart_add(request, product_id):
    """Add an item to the cart while respecting stock limits"""
    try:
        product = Product.objects.get(id=product_id, status='active', is_available=True)
        
        # Support both JSON and form submissions
        payload = {}
        if request.headers.get('Content-Type', '').startswith('application/json'):
            try:
                payload = json.loads(request.body or "{}")
            except ValueError:
                payload = {}
        quantity = payload.get('quantity') or request.POST.get('quantity') or 1
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            quantity = 1
        if quantity < 1:
            quantity = 1
        
        cart, _ = Cart.objects.get_or_create(customer=request.user)
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': quantity}
        )
        
        if created:
            if cart_item.quantity != quantity:
                cart_item.quantity = quantity
                cart_item.save()
        else:
            new_quantity = cart_item.quantity + quantity
            if not product.can_fulfill_order(new_quantity):
                message = f"Only {product.get_available_quantity()} units available for {product.name}."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': message}, status=400)
                messages.warning(request, message)
                return redirect('cart')
            cart_item.quantity = new_quantity
            cart_item.save()
        
        # Response handling
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': 'Product added to cart',
                'cart_item_count': cart.get_item_count(),
                'cart_total': str(cart.get_total())
            })
        
        messages.success(request, f'"{product.name}" added to cart.')
        return redirect('cart')
            
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Product not found'}, status=404)
    except ValidationError as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
        messages.error(request, str(e))
        return redirect('cart')
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        messages.error(request, 'Unable to add product to cart.')
        return redirect('product_detail', slug=product.slug if 'product' in locals() else '')

@login_required
@customer_required
def cart_remove(request, item_id):
    """Remove item from cart"""
    cart_item = get_object_or_404(CartItem, id=item_id, cart__customer=request.user)
    
    # Release reserved stock before deleting
    try:
        cart_item.product.release_stock(cart_item.quantity)
    except Exception as e:
        # Log error but continue
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to release stock: {str(e)}")
    
    product_name = cart_item.product.name
    cart_item.delete()
    
    messages.success(request, f"Removed {product_name} from cart")
    return redirect('cart')

@require_POST
@login_required
@customer_required
def cart_update(request):
    """Update cart quantities"""
    cart = Cart.objects.filter(customer=request.user).first()
    if not cart:
        messages.info(request, "Your cart is empty.")
        return redirect('product_list')
    
    for key, value in request.POST.items():
        if key.startswith('quantity_'):
            item_id = key.replace('quantity_', '')
            try:
                cart_item = CartItem.objects.get(id=item_id, cart=cart)
                quantity = int(value)
                
                if quantity < 1:
                    # Release stock before deleting
                    cart_item.product.release_stock(cart_item.quantity)
                    cart_item.delete()
                else:
                    # Calculate difference
                    diff = quantity - cart_item.quantity
                    if diff > 0:
                        # Need to reserve more stock
                        if not cart_item.product.reserve_stock(diff):
                            messages.warning(request, 
                                f"Not enough stock for {cart_item.product.name}")
                            continue
                    elif diff < 0:
                        # Need to release some stock
                        cart_item.product.release_stock(abs(diff))
                    
                    cart_item.quantity = quantity
                    cart_item.save()
            except (CartItem.DoesNotExist, ValueError):
                continue
    
    messages.success(request, "Cart updated successfully")
    return redirect('cart')

@login_required
@customer_required
def cart_clear(request):
    """Clear entire cart"""
    cart = Cart.objects.filter(customer=request.user).first()
    if not cart:
        messages.info(request, "Your cart is already empty.")
        return redirect('product_list')
    
    # Release all reserved stock before clearing
    for item in cart.items.all():
        try:
            item.product.release_stock(item.quantity)
        except Exception as e:
            # Log error but continue
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to release stock for {item.product.name}: {str(e)}")
    
    cart.items.all().delete()
    
    messages.success(request, "Cart cleared successfully")
    return redirect('cart')

# ==================== CHECKOUT VIEWS ====================

def send_order_confirmation_email(order, request):
    """Send order confirmation email immediately after order creation"""
    subject = f'Order Confirmation #{order.order_number} - SokHub'
    template_name = 'emails/order_confirmation.html'
    
    context = {
        'order': order,
        'order_items': order.items.all(),
        'user': order.customer,
        'settings': settings
    }
    
    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)
    
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.customer.email]
    )
    email.attach_alternative(html_content, "text/html")
    
    try:
        email.send()
    except Exception as e:
        # Log error but don't fail order creation
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send order confirmation email: {str(e)}")

@login_required
@customer_required
def checkout_view(request):
    """Checkout process"""
    cart = get_object_or_404(Cart, customer=request.user)
    cart_items = cart.items.select_related('product').all()
    
    if not cart_items:
        messages.error(request, "Your cart is empty.")
        return redirect('product_list')
    
    # Validate all items are in stock
    for item in cart_items:
        item.product.refresh_from_db()
        
        if not item.product.is_in_stock():
            messages.error(request, f"{item.product.name} is out of stock. Please remove it from cart.")
            return redirect('cart')
        
        if not item.product.can_fulfill_order(item.quantity):
            messages.error(request, f"Not enough stock for {item.product.name}. Available: {item.product.get_available_quantity()}")
            return redirect('cart')
    
    if request.method == 'POST':
        form = CheckoutForm(request.POST, customer=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # First, reserve stock for all items
                    reserved_items = []
                    for item in cart_items:
                        if not item.product.reserve_stock(item.quantity):
                            raise Exception(f"Cannot reserve stock for {item.product.name}")
                        reserved_items.append(item)
                    
                    # Generate unique invoice number
                    def generate_invoice_number():
                        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
                        random_str = uuid.uuid4().hex[:6].upper()
                        return f'INV-{timestamp}-{random_str}'
                    
                    # Generate unique short code (6 characters)
                    def generate_short_code():
                        # Generate a 6-character alphanumeric code
                        characters = string.ascii_uppercase + string.digits
                        return ''.join(random.choice(characters) for _ in range(6))
                    
                    # Generate both codes
                    invoice_number = generate_invoice_number()
                    short_code = generate_short_code()
                    
                    # Check if short code already exists (very unlikely but possible)
                    max_retries = 5
                    retry_count = 0
                    while Order.objects.filter(short_code=short_code).exists() and retry_count < max_retries:
                        short_code = generate_short_code()
                        retry_count += 1
                    
                    if retry_count == max_retries:
                        # Fallback: use part of UUID
                        short_code = uuid.uuid4().hex[:6].upper()
                    
                    # Create order
                    order = Order(
                        customer=request.user,
                        shipping_address=form.cleaned_data['shipping_address'],
                        shipping_city=form.cleaned_data['shipping_city'],
                        shipping_phone=form.cleaned_data['shipping_phone'],
                        shipping_notes=form.cleaned_data.get('shipping_notes', ''),
                        payment_method=form.cleaned_data['payment_method'],
                        momo_number=form.cleaned_data.get('momo_number'),
                        customer_notes=form.cleaned_data.get('customer_notes', ''),
                        status='confirmed',
                        payment_status='pending',
                        invoice_number=invoice_number,
                        short_code=short_code  # ADD THIS LINE
                    )
                    
                    if cart_items:
                        first_item = cart_items[0]
                        order.vendor = first_item.product.vendor
                    
                    order.save()
                    
                    # Create order items and commit stock
                    total_amount = 0
                    for item in cart_items:
                        order_item = OrderItem(
                            order=order,
                            product=item.product,
                            vendor=item.product.vendor,
                            price=item.product.price,
                            quantity=item.quantity,
                            total_price=item.product.price * item.quantity
                        )
                        order_item.save()
                        
                        # Commit the reserved stock
                        item.product.commit_stock(item.quantity)
                        
                        total_amount += order_item.total_price
                    
                    # Calculate totals
                    order.subtotal = total_amount
                    order.shipping_cost = Decimal('0.00')
                    order.total_amount = total_amount
                    order.save()
                    
                    # Clear cart WITHOUT releasing stock (stock already committed)
                    # Just delete cart items without calling release_stock
                    cart.items.all().delete()
                    
                    # Generate invoice PDF
                    order.generate_invoice_pdf()
                    
                    # Save shipping address if requested
                    if form.cleaned_data.get('save_shipping_address'):
                        if hasattr(request.user, 'customerprofile'):
                            request.user.customerprofile.shipping_address = form.cleaned_data['shipping_address']
                            request.user.customerprofile.save()
                    
                    # Send order confirmation email
                    try:
                        send_order_confirmation_email(order, request)
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f"Failed to send confirmation email: {str(e)}")
                    
                    # Notify vendor
                    if order.vendor:
                        OrderNotification.objects.create(
                            order=order,
                            notification_type='status_change',
                            recipient=order.vendor,
                            message=f"New order #{order.order_number} received from {order.customer.username}. Amount: RWF {order.total_amount}."
                        )
                    
                    messages.success(request, f"Order #{order.order_number} confirmed successfully!")
                    return redirect('order_confirmation', order_number=order.order_number)
            
            except Exception as e:
                # If order creation fails, release any reserved stock
                for item in cart_items:
                    try:
                        # CORRECT: Call release_stock on the product
                        item.product.release_stock(item.quantity)
                    except Exception as release_error:
                        # Log but continue with other items
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f"Failed to release stock for {item.product.name}: {str(release_error)}")
                
                messages.error(request, f"Checkout failed: {str(e)}")
                context = {
                    'form': form,
                    'cart': cart,
                    'cart_items': cart_items,
                    'subtotal': cart.get_total(),
                    'shipping_cost': Decimal('0.00'),
                    'total': cart.get_total(),
                }
                return render(request, 'orders/checkout.html', context)
        
        else:
            # Form is invalid
            context = {
                'form': form,
                'cart': cart,
                'cart_items': cart_items,
                'subtotal': cart.get_total(),
                'shipping_cost': Decimal('0.00'),
                'total': cart.get_total(),
            }
            return render(request, 'orders/checkout.html', context)
    
    else:
        # GET request
        form = CheckoutForm(customer=request.user)
        context = {
            'form': form,
            'cart': cart,
            'cart_items': cart_items,
            'subtotal': cart.get_total(),
            'shipping_cost': Decimal('0.00'),
            'total': cart.get_total(),
        }
        return render(request, 'orders/checkout.html', context)

@login_required
@customer_required
def order_confirmation(request, order_number):
    """Order confirmation page"""
    order = get_object_or_404(Order, order_number=order_number, customer=request.user)
    
    # Include status history and basic contact info for the template
    status_history = order.status_history.all()[:10]
    order_items = order.items.select_related('product')
    customer_email = order.customer.email if hasattr(order.customer, 'email') else None

    context = {
        'order': order,
        'order_items': order_items,
        'status_history': status_history,
        'customer_email': customer_email,
    }
    
    return render(request, 'orders/order_confirmation.html', context)

# ==================== ORDER MANAGEMENT VIEWS ====================

@login_required
@customer_required
def customer_order_list(request):
    """Customer's order history"""
    orders = Order.objects.filter(customer=request.user).select_related('vendor').prefetch_related('items')
    
    # Apply filters
    form = OrderFilterForm(request.GET)
    if form.is_valid():
        status = form.cleaned_data.get('status')
        payment_status = form.cleaned_data.get('payment_status')
        date_from = form.cleaned_data.get('date_from')
        date_to = form.cleaned_data.get('date_to')
        search = form.cleaned_data.get('search')
        
        if status:
            orders = orders.filter(status=status)
        if payment_status:
            orders = orders.filter(payment_status=payment_status)
        if date_from:
            orders = orders.filter(created_at__date__gte=date_from)
        if date_to:
            orders = orders.filter(created_at__date__lte=date_to)
        if search:
            orders = orders.filter(
                Q(order_number__icontains=search) |
                Q(vendor__vendorprofile__business_name__icontains=search)
            )
    
    # Pagination
    paginator = Paginator(orders, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Order statistics
    total_orders = orders.count()
    pending_orders = orders.filter(status='pending').count()
    delivered_orders = orders.filter(status='delivered').count()
    total_spent = orders.aggregate(total=Sum('total_amount'))['total'] or 0
    
    context = {
        'page_obj': page_obj,
        'form': form,
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'delivered_orders': delivered_orders,
        'total_spent': total_spent,
    }
    
    return render(request, 'customer/order_list.html', context)

@login_required
@customer_required
def customer_order_detail(request, order_number):
    """Customer order detail view"""
    order = get_object_or_404(Order, order_number=order_number, customer=request.user)
    
    # Mark notifications as read
    order.notifications.filter(recipient=request.user, is_read=False).update(is_read=True)
    
    context = {
        'order': order,
        'order_items': order.items.all(),
        'status_history': order.status_history.all()[:10],
    }
    
    return render(request, 'customer/order_detail.html', context)

@login_required
@vendor_approved_required
def vendor_order_list(request):
    """Vendor's order management"""
    orders = Order.objects.filter(
        items__vendor=request.user
    ).distinct().select_related('customer').prefetch_related('items')
    
    # Apply filters
    form = VendorOrderFilterForm(request.GET)
    if form.is_valid():
        status = form.cleaned_data.get('status')
        payment_status = form.cleaned_data.get('payment_status')
        date_from = form.cleaned_data.get('date_from')
        date_to = form.cleaned_data.get('date_to')
        search = form.cleaned_data.get('search')
        product_filter = form.cleaned_data.get('product')
        
        if status:
            orders = orders.filter(status=status)
        if payment_status:
            orders = orders.filter(payment_status=payment_status)
        if date_from:
            orders = orders.filter(created_at__date__gte=date_from)
        if date_to:
            orders = orders.filter(created_at__date__lte=date_to)
        if search:
            orders = orders.filter(
                Q(order_number__icontains=search) |
                Q(customer__username__icontains=search) |
                Q(customer__email__icontains=search)
            )
        if product_filter:
            orders = orders.filter(items__product_name__icontains=product_filter)
    
    # Pagination
    paginator = Paginator(orders, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Vendor statistics
    total_orders = orders.count()
    pending_orders = orders.filter(status='pending').count()
    processing_orders = orders.filter(status='processing').count()
    completed_orders = orders.filter(status='delivered').count()
    total_revenue = orders.aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Deletion requests
    deletion_requests = orders.filter(delete_requested=True, delete_approved=False).count()
    
    context = {
        'page_obj': page_obj,
        'form': form,
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'processing_orders': processing_orders,
        'completed_orders': completed_orders,
        'total_revenue': total_revenue,
        'deletion_requests': deletion_requests,
    }
    
    return render(request, 'vendor/order_list.html', context)

@login_required
@vendor_approved_required
def vendor_order_detail(request, order_number):
    """Vendor order detail view - handles duplicate order numbers"""
    try:
        # FIRST: Try to get the MOST RECENT order with this order number
        # that belongs to this vendor
        order = Order.objects.filter(
            order_number=order_number,
            items__vendor=request.user
        ).distinct().order_by('-created_at').first()
        
        if not order:
            # If no order found with vendor items, try any order
            order = Order.objects.filter(order_number=order_number).order_by('-created_at').first()
            
            if not order:
                raise Http404("Order not found")
            
            # Check if vendor has items in ANY of the duplicate orders
            all_orders = Order.objects.filter(order_number=order_number)
            vendor_has_items = False
            
            for ord in all_orders:
                if ord.items.filter(vendor=request.user).exists():
                    vendor_has_items = True
                    order = ord  # Use this order instead
                    break
            
            if not vendor_has_items:
                messages.error(request, "You don't have permission to view this order.")
                return redirect('vendor_order_list')
        
    except Order.DoesNotExist:
        raise Http404("Order not found")
    
    # Mark vendor notifications as read
    order.notifications.filter(recipient=request.user, is_read=False).update(is_read=True)
    
    # Get vendor-specific items
    vendor_items = order.items.filter(vendor=request.user)
    
    if request.method == 'POST':
        # Handle status update
        status_form = OrderStatusUpdateForm(request.POST, instance=order)
        if status_form.is_valid():
            old_status = order.status
            order = status_form.save()
            
            # If order is marked as delivered, send confirmation email
            if order.status == 'delivered' and old_status != 'delivered':
                try:
                    send_order_completion_email(order, request)
                    messages.success(request, f"Order marked as delivered and confirmation email sent to customer.")
                except Exception as e:
                    messages.warning(request, f"Order status updated, but email could not be sent: {str(e)}")
            
            # Create notification for customer
            OrderNotification.objects.create(
                order=order,
                notification_type='status_change',
                recipient=order.customer,
                message=f"Your order #{order.order_number} status has been updated from {old_status} to {order.status}."
            )
            
            messages.success(request, f"Order status updated to {order.get_status_display()}.")
            return redirect('vendor_order_detail', order_number=order.order_number)
    else:
        status_form = OrderStatusUpdateForm(instance=order)
    
    context = {
        'order': order,
        'vendor_items': vendor_items,
        'status_form': status_form,
        'status_history': order.status_history.all()[:10],
    }
    
    return render(request, 'vendor/order_detail.html', context)

@login_required
@vendor_approved_required
def vendor_mark_payment_completed(request, order_number):
    """Vendor marks payment as completed after phone verification"""
    try:
        # Get the specific order that belongs to this vendor
        order = Order.objects.filter(
            order_number=order_number,
            items__vendor=request.user
        ).distinct().first()
        
        if not order:
            messages.error(request, "Order not found or you don't have permission to access it.")
            return redirect('vendor_orders')
            
    except Order.MultipleObjectsReturned:
        # If somehow multiple orders exist, get the first one
        orders = Order.objects.filter(
            order_number=order_number,
            items__vendor=request.user
        ).distinct()
        order = orders.first()
        
        # Log this issue for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Multiple orders found for order_number: {order_number}, count: {orders.count()}")
    
    if request.method == 'POST':
        transaction_id = request.POST.get('transaction_id', '')
        
        # Mark payment as completed
        order.payment_status = 'completed'
        order.payment_date = timezone.now()
        if transaction_id:
            order.momo_transaction_id = transaction_id
        order.save()
        
        # Notify customer
        OrderNotification.objects.create(
            order=order,
            notification_type='payment_received',
            recipient=order.customer,
            message=f"Payment for order #{order.order_number} has been verified and confirmed by vendor."
        )
        
        messages.success(request, f"Payment for order #{order.order_number} marked as completed.")
        return redirect('vendor_order_detail', order_number=order.order_number)
    
    context = {
        'order': order,
    }
    return render(request, 'vendor/mark_payment.html', context)
@login_required
@vendor_approved_required
@vendor_required
def vendor_report(request):
    """Vendor sales report view - with shorter trend data"""
    if not request.user.is_authenticated or request.user.user_type != 'vendor':
        messages.error(request, "You must be logged in as a vendor to access this page.")
        return redirect('login')
    
    # Get vendor profile
    vendor_profile = request.user.vendorprofile
    
    # Get date range from request
    date_range = request.GET.get('date_range', '30d')
    end_date = timezone.now()
    
    if date_range == '30d':
        start_date = end_date - timedelta(days=30)
    elif date_range == '90d':
        start_date = end_date - timedelta(days=90)
    elif date_range == '1y':
        start_date = end_date - timedelta(days=365)
    elif date_range == 'all':
        start_date = None
    else:
        start_date = end_date - timedelta(days=30)
    
    # Base queryset for vendor's order items
    order_items_qs = OrderItem.objects.filter(
        vendor=request.user,
        order__status='delivered'
    )
    
    # Apply date filter if specified
    if start_date:
        order_items_qs = order_items_qs.filter(
            order__created_at__gte=start_date,
            order__created_at__lte=end_date
        )
    
    # Get sales data aggregated by product
    sales_data = order_items_qs.values(
        'product__name',
        'product__id'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum('total_price')
    ).order_by('-total_revenue')
    
    # Convert QuerySet to list and handle Decimal conversion
    sales_data_list = []
    for item in sales_data:
        # Convert Decimal to float for JSON serialization
        sales_data_list.append({
            'product__name': item['product__name'],
            'product__id': item['product__id'],
            'total_quantity': item['total_quantity'] or 0,
            'total_revenue': float(item['total_revenue']) if item['total_revenue'] else 0.0,
        })
    
    # Calculate totals
    total_revenue = sum(item['total_revenue'] for item in sales_data_list)
    total_quantity = sum(item['total_quantity'] for item in sales_data_list)
    
    # Add percentage for progress bars
    for item in sales_data_list:
        if total_revenue > 0 and item['total_revenue']:
            item['percentage'] = round((item['total_revenue'] / total_revenue) * 100, 1)
        else:
            item['percentage'] = 0
    
    # Get top 5 products for pie chart
    top_products = sales_data_list[:5] if sales_data_list else []
    top_products_labels = [item['product__name'] for item in top_products]
    top_products_revenue = [item['total_revenue'] for item in top_products]
    
    # **SHORTER TREND DATA - Last 6 months instead of 12**
    monthly_trend = OrderItem.objects.filter(
        vendor=request.user,
        order__status='delivered',
        order__created_at__gte=end_date - timedelta(days=180)  # 6 months
    ).annotate(
        month=TruncMonth('order__created_at')
    ).values('month').annotate(
        monthly_revenue=Sum('total_price'),
        monthly_quantity=Sum('quantity')
    ).order_by('month')
    
    # Convert monthly trend Decimal to float
    monthly_trend_list = []
    for item in monthly_trend:
        monthly_trend_list.append({
            'month': item['month'],
            'monthly_revenue': float(item['monthly_revenue']) if item['monthly_revenue'] else 0.0,
            'monthly_quantity': item['monthly_quantity'] or 0,
        })
    
    # Format trend data for chart - ONLY 6 MONTHS
    trend_labels = []
    trend_revenue = []
    trend_quantity = []
    
    # Only get last 6 months
    for i in range(6):
        month_date = end_date - timedelta(days=30 * (5 - i))
        month_str = month_date.strftime('%b')  # Only month abbreviation, no year
        
        # Find matching month data
        month_data = next((item for item in monthly_trend_list if 
                          item['month'].month == month_date.month and 
                          item['month'].year == month_date.year), None)
        
        trend_labels.append(month_str)
        if month_data:
            trend_revenue.append(month_data['monthly_revenue'])
            trend_quantity.append(month_data['monthly_quantity'])
        else:
            trend_revenue.append(0)
            trend_quantity.append(0)
    
    # Get summary statistics
    total_products = len(sales_data_list)
    avg_revenue_per_product = total_revenue / total_products if total_products > 0 else 0
    top_product_revenue = top_products[0]['total_revenue'] if top_products else 0
    
    # Get all categories for filter dropdown
    from product.models import Product
    categories = Product.objects.filter(vendor=request.user).values_list(
        'category__name', flat=True
    ).distinct().exclude(category__name__isnull=True)
    
    # Prepare context
    context = {
        'vendor': vendor_profile,
        'sales_data': sales_data_list,
        'total_revenue': float(total_revenue) if isinstance(total_revenue, Decimal) else total_revenue,
        'total_quantity': total_quantity,
        'total_products': total_products,
        'avg_revenue_per_product': float(avg_revenue_per_product) if isinstance(avg_revenue_per_product, Decimal) else avg_revenue_per_product,
        'top_product_revenue': float(top_product_revenue) if isinstance(top_product_revenue, Decimal) else top_product_revenue,
        
        # Chart data - SHORTER
        'top_products_labels': top_products_labels,
        'top_products_revenue': top_products_revenue,
        'trend_labels': trend_labels,  # Now only 6 items
        'trend_revenue': trend_revenue,  # Now only 6 items
        'trend_quantity': trend_quantity,  # Now only 6 items
        
        # Filter data
        'date_range': date_range,
        'start_date': start_date,
        'end_date': end_date,
        'categories': categories,
    }
    
    # AJAX request for chart updates
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'sales_data': sales_data_list,
            'total_revenue': float(total_revenue) if isinstance(total_revenue, Decimal) else total_revenue,
            'top_products_labels': top_products_labels,
            'top_products_revenue': top_products_revenue,
            'trend_labels': trend_labels,
            'trend_revenue': trend_revenue,
            'trend_quantity': trend_quantity,
        })
    
    return render(request, 'vendor/sale_reports.html', context)

# ==================== ORDER ACTIONS ====================

@login_required
@customer_required
@require_POST
def request_order_deletion(request, order_number):
    """Customer requests order deletion"""
    order = get_object_or_404(Order, order_number=order_number, customer=request.user)
    
    if not order.can_be_cancelled():
        messages.error(request, "This order cannot be cancelled at this stage.")
        return redirect('customer_order_detail', order_number=order_number)
    
    form = OrderDeletionRequestForm(request.POST)
    if form.is_valid():
        order.request_deletion(form.cleaned_data['reason'])
        messages.success(request, "Deletion request sent to vendor. You will be notified when approved.")
    else:
        messages.error(request, "Please provide a valid reason.")
    
    return redirect('customer_order_detail', order_number=order_number)

@login_required
@vendor_approved_required
@require_POST
def approve_order_deletion(request, order_number):
    """Vendor approves order deletion"""
    order = get_object_or_404(
        Order, 
        order_number=order_number,
        items__vendor=request.user,
        delete_requested=True,
        delete_approved=False
    ).distinct()
    
    order.approve_deletion(request.user)
    
    # Notify customer
    OrderNotification.objects.create(
        order=order,
        notification_type='deletion_request',
        recipient=order.customer,
        message=f"Your deletion request for order #{order.order_number} has been approved. The order has been cancelled and refund processed if applicable."
    )
    
    messages.success(request, "Order deletion approved and cancelled.")
    return redirect('vendor_order_detail', order_number=order_number)

@login_required
@vendor_approved_required
@require_POST
def reject_order_deletion(request, order_number):
    """Vendor rejects order deletion"""
    order = get_object_or_404(
        Order, 
        order_number=order_number,
        items__vendor=request.user,
        delete_requested=True,
        delete_approved=False
    ).distinct()
    
    order.delete_requested = False
    order.delete_request_reason = ''
    order.save()
    
    # Notify customer
    OrderNotification.objects.create(
        order=order,
        notification_type='deletion_request',
        recipient=order.customer,
        message=f"Your deletion request for order #{order.order_number} has been rejected. Please contact vendor for more information."
    )
    
    messages.info(request, "Order deletion request rejected.")
    return redirect('vendor_order_detail', order_number=order_number)

@login_required
@customer_required
@require_POST
def confirm_payment(request, order_number):
    """Customer confirms payment made"""
    order = get_object_or_404(Order, order_number=order_number, customer=request.user)
    
    if order.payment_status != 'pending':
        messages.error(request, "Payment already processed.")
        return redirect('customer_order_detail', order_number=order_number)
    
    form = OrderPaymentForm(request.POST)
    if form.is_valid():
        order.mark_as_paid(
            momo_number=form.cleaned_data['momo_number'],
            transaction_id=form.cleaned_data.get('transaction_id')
        )
        
        # Notify vendor
        if order.vendor:
            OrderNotification.objects.create(
                order=order,
                notification_type='payment_received',
                recipient=order.vendor,
                message=f"Payment received for order #{order.order_number} from {order.customer.username}. Amount: RWF {order.total_amount}"
            )
        
        messages.success(request, "Payment confirmed! Vendor has been notified.")
    else:
        messages.error(request, "Please provide valid payment details.")
    
    return redirect('customer_order_detail', order_number=order_number)

@login_required
@customer_required
def download_invoice(request, order_number):
    """Download order invoice PDF"""
    order = get_object_or_404(Order, order_number=order_number, customer=request.user)
    
    if not order.invoice_pdf:
        order.generate_invoice_pdf()
    
    response = HttpResponse(order.invoice_pdf.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{order.invoice_number}.pdf"'
    return response

# ==================== AJAX/API VIEWS ====================

@login_required
@require_GET
def get_cart_count(request):
    """Get cart item count for AJAX"""
    if request.user.user_type == 'customer':
        cart = Cart.objects.filter(customer=request.user).first()
        count = cart.items.count() if cart else 0
        return JsonResponse({'count': count})
    return JsonResponse({'count': 0})

@login_required
@customer_required
@require_GET
def get_unread_notifications(request):
    """Get unread order notifications"""
    notifications = OrderNotification.objects.filter(
        recipient=request.user,
        is_read=False
    ).order_by('-created_at')[:10]
    
    notification_list = []
    for notification in notifications:
        notification_list.append({
            'id': notification.id,
            'type': notification.get_notification_type_display(),
            'message': notification.message,
            'order_number': notification.order.order_number,
            'created_at': notification.created_at.strftime('%b %d, %H:%M'),
            'url': notification.order.get_customer_dashboard_url(),
        })
    
    return JsonResponse({'notifications': notification_list})

@login_required
@require_POST
def mark_notification_read(request, notification_id):
    """Mark notification as read"""
    notification = get_object_or_404(OrderNotification, id=notification_id, recipient=request.user)
    notification.is_read = True
    notification.save()
    return JsonResponse({'success': True})

@login_required
@vendor_approved_required
@require_POST
def bulk_update_orders(request):
    """Bulk update orders (vendor)"""
    form = BulkOrderUpdateForm(request.POST)
    if form.is_valid():
        action = form.cleaned_data['action']
        order_ids = form.cleaned_data['order_ids'].split(',')
        notes = form.cleaned_data.get('notes', '')
        
        orders = Order.objects.filter(
            id__in=order_ids,
            items__vendor=request.user
        ).distinct()
        
        updated_count = 0
        for order in orders:
            if action == 'confirm' and order.status == 'pending':
                order.status = 'confirmed'
                order.save()
                updated_count += 1
            elif action == 'process' and order.status == 'confirmed':
                order.status = 'processing'
                order.save()
                updated_count += 1
            elif action == 'ship' and order.status == 'processing':
                order.status = 'shipped'
                order.save()
                updated_count += 1
            elif action == 'cancel' and order.can_be_cancelled():
                order.status = 'cancelled'
                order.save()
                updated_count += 1
        
        messages.success(request, f"{updated_count} orders updated.")
    else:
        messages.error(request, "Invalid bulk update request.")
    
    return redirect('vendor_order_list')

def send_order_completion_email(order, request):
    """Send order completion email to customer when vendor marks order as delivered"""
    subject = f'Order #{order.order_number} Has Been Delivered!'
    template_name = 'emails/order_confirmation.html'
    
    context = {
        'order': order,
        'order_items': order.items.all(),
        'user': order.customer,
        'settings': settings
    }
    
    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)
    
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.customer.email]
    )
    email.attach_alternative(html_content, "text/html")
    email.send()