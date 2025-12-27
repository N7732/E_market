# orders/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Cart URLs
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/<int:product_id>/', views.cart_add, name='cart_add'),
    path('cart/remove/<int:item_id>/', views.cart_remove, name='cart_remove'),
    path('cart/update/', views.cart_update, name='cart_update'),
    path('cart/clear/', views.cart_clear, name='cart_clear'),
    path('coupon/apply/', views.apply_coupon, name='apply_coupon'),
    
    # Checkout URLs
    path('checkout/', views.checkout_view, name='checkout'),
    path('confirmation/<str:order_number>/', views.order_confirmation, name='order_confirmation'),
    
    # Customer Order URLs
    path('customer/orders/', views.customer_order_list, name='customer_order_list'),
    path('customer/orders/<str:order_number>/', views.customer_order_detail, name='customer_order_detail'),
    path('customer/orders/<str:order_number>/delete/', views.request_order_deletion, name='request_order_deletion'),
    path('customer/orders/<str:order_number>/payment/', views.confirm_payment, name='confirm_payment'),
    path('customer/orders/<str:order_number>/invoice/', views.download_invoice, name='download_invoice'),
    
    # Vendor Order URLs
    path('vendor/orders/', views.vendor_order_list, name='vendor_order_list'),
    path('vendor/orders/<str:order_number>/', views.vendor_order_detail, name='vendor_order_detail'),
    path('vendor/orders/<str:order_number>/delete/approve/', views.approve_order_deletion, name='approve_order_deletion'),
    path('vendor/orders/<str:order_number>/delete/reject/', views.reject_order_deletion, name='reject_order_deletion'),
    path('vendor/orders/bulk-update/', views.bulk_update_orders, name='bulk_update_orders'),
    path('vendor/orders/<str:order_number>/payment/complete/', views.vendor_mark_payment_completed, name='vendor_mark_payment_completed'),
    
    # API/Utility URLs
    path('api/cart-count/', views.get_cart_count, name='get_cart_count'),
    path('api/notifications/', views.get_unread_notifications, name='get_unread_notifications'),
    path('api/notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),

    # Reports
    path('vendor/reports/sales/', views.vendor_report, name='vendor_reports'),
]