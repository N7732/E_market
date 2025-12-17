# products/urls.py
from django.urls import path
from . import views
from .views import ProductListView, ProductDetailView

urlpatterns = [
    # Public product pages
    path('', ProductListView.as_view(), name='product_list'),
    path('category/<slug:slug>/', views.category_detail, name='category_detail'),
    
    # Vendor product management
    path('vendor/products/', views.vendor_product_list, name='vendor_product_list'),
    path('vendor/products/add/', views.vendor_add_product, name='vendor_add_product'),
    path('vendor/products/<int:pk>/edit/', views.vendor_edit_product, name='vendor_edit_product'),
    path('vendor/products/<int:pk>/delete/', views.vendor_delete_product, name='vendor_delete_product'),
    path('vendor/products/<int:pk>/stock/', views.vendor_stock_management, name='vendor_stock_management'),
    path('vendor/products/<int:pk>/status/', views.vendor_toggle_product_status, name='vendor_toggle_product_status'),
    
    #Review moderation
    path('product/<int:product_id>/review/', views.add_review, name='add_review'),
    path('<int:pk>/review/', views.add_product_review, name='add_product_review'),
    
    # AJAX/API endpoints
    path('api/<int:pk>/availability/', views.product_availability_check, name='product_availability_check'),
    path('api/<int:pk>/reserve/', views.reserve_stock, name='reserve_stock'),
    path('api/<int:pk>/wishlist/', views.toggle_wishlist, name='toggle_wishlist'),
    
    # Analytics
    path('vendor/analytics/sales/', views.vendor_analytics, name='vendor_analytics'),
    
    # Product detail should remain last to avoid conflicts with vendor paths
    path('<slug:slug>/', ProductDetailView.as_view(), name='product_detail'),
]