# orders/views.py
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse, HttpResponse
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

# ==================== CART VIEWS ====================

@login_required
@customer_required
def cart_view(request):
    """View shopping cart"""
    cart, created = Cart.objects.get_or_create(customer=request.user)
    cart_items = cart.items.select_related('product').all()
    
    # Update cart if product stock changed
    for item in cart_items:
        if item.product.is_track_inventory:
            available = item.product.get_available_quantity()
            if item.quantity > available and available > 0:
                item.quantity = available
                item.save()
                messages.warning(request, f"Updated {item.product.name} quantity to {available} due to stock changes.")
            elif available == 0:
                item.delete()
                messages.error(request, f"{item.product.name} is out of stock and was removed from your cart.")
    
    context = {
        'cart': cart,
        'cart_items': cart_items,
        'cart_total': cart.get_total(),
        'item_count': cart.get_item_count(),
    }
    
    return render(request, 'orders/cart.html', context)

@login_required
@customer_required
@require_POST
def add_to_cart(request, product_id):
    """Add product to cart"""
    product = get_object_or_404(Product, id=product_id, status='active', is_available=True)
    
    if not product.is_in_stock():
        messages.error(request, "This product is out of stock.")
        return redirect('product_detail', slug=product.slug)
    
    cart, created = Cart.objects.get_or_create(customer=request.user)
    
    try:
        with transaction.atomic():
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                product=product,
                defaults={'quantity': 1}
            )
            
            if not created:
                # Check if additional quantity can be added
                if not cart_item.can_be_added(1):
                    messages.error(request, f"Cannot add more {product.name} to cart. Available: {product.get_available_quantity()}")
                    return redirect('cart')
                
                cart_item.quantity = F('quantity') + 1
                cart_item.save()
                cart_item.refresh_from_db()
                
                # Reserve additional stock
                product.reserve_stock(1)
            else:
                # Reserve initial stock
                product.reserve_stock(1)
            
            messages.success(request, f"Added {product.name} to cart.")
    
    except Exception as e:
        messages.error(request, f"Failed to add to cart: {str(e)}")
    
    return redirect('cart')

@login_required
@customer_required
@require_POST
def update_cart_item(request, item_id):
    """Update cart item quantity"""
    cart_item = get_object_or_404(CartItem, id=item_id, cart__customer=request.user)
    form = CartItemForm(request.POST, instance=cart_item, product=cart_item.product)
    
    if form.is_valid():
        form.save()
        messages.success(request, "Cart updated.")
    else:
        for error in form.errors.values():
            messages.error(request, error)
    
    return redirect('cart')

@login_required
@customer_required
@require_POST
def remove_from_cart(request, item_id):
    """Remove item from cart"""
    cart_item = get_object_or_404(CartItem, id=item_id, cart__customer=request.user)
    product_name = cart_item.product.name
    cart_item.delete()
    messages.success(request, f"Removed {product_name} from cart.")
    return redirect('cart')

@login_required
@customer_required
def clear_cart(request):
    """Clear entire cart"""
    cart = get_object_or_404(Cart, customer=request.user)
    cart.clear()
    messages.success(request, "Cart cleared.")
    return redirect('cart')

# ==================== CHECKOUT VIEWS ====================

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
        if not item.product.is_in_stock():
            messages.error(request, f"{item.product.name} is out of stock. Please remove it from cart.")
            return redirect('cart')
    
    if request.method == 'POST':
        form = CheckoutForm(request.POST, customer=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
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
                    )
                    
                    # For now, set first product's vendor as order vendor
                    # In real app, you'd handle multiple vendors
                    if cart_items:
                        first_item = cart_items[0]
                        order.vendor = first_item.product.vendor
                    
                    order.save()
                    
                    # Create order items
                    total_amount = 0
                    for cart_item in cart_items:
                        order_item = OrderItem(
                            order=order,
                            product=cart_item.product,
                            vendor=cart_item.product.vendor,
                            price=cart_item.product.price,
                            quantity=cart_item.quantity,
                            total_price=cart_item.product.price * cart_item.quantity
                        )
                        order_item.save()
                        
                        # Commit stock (convert reservation to sale)
                        order_item.commit_stock()
                        
                        total_amount += order_item.total_price
                    
                    # Calculate totals
                    order.subtotal = total_amount
                    order.shipping_cost = Decimal('0.00')  # Free shipping for now
                    order.total_amount = total_amount
                    order.save()
                    
                    # Clear cart
                    cart.clear()
                    
                    # Generate invoice PDF
                    order.generate_invoice_pdf()
                    
                    # Save shipping address if requested
                    if form.cleaned_data.get('save_shipping_address'):
                        if hasattr(request.user, 'customerprofile'):
                            request.user.customerprofile.shipping_address = form.cleaned_data['shipping_address']
                            request.user.customerprofile.save()
                    
                    messages.success(request, f"Order #{order.order_number} placed successfully!")
                    return redirect('order_confirmation', order_number=order.order_number)
            
            except Exception as e:
                messages.error(request, f"Checkout failed: {str(e)}")
                return redirect('checkout')
    else:
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
    
    context = {
        'order': order,
        'order_items': order.items.all(),
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
    
    return render(request, 'orders/customer/order_list.html', context)

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
    
    return render(request, 'orders/customer/order_detail.html', context)

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
    
    return render(request, 'orders/vendor/order_list.html', context)

@login_required
@vendor_approved_required
def vendor_order_detail(request, order_number):
    """Vendor order detail view"""
    order = get_object_or_404(
        Order, 
        order_number=order_number,
        items__vendor=request.user
    ).distinct()
    
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
    
    return render(request, 'orders/vendor/order_detail.html', context)

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