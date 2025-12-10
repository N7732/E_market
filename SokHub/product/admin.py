# products/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum, Count, Avg
from django.utils import timezone
from .models import (
    Category, Product, ProductImage, ProductVariant, 
    ProductTag, ProductReview, ProductAttribute, StockHistory
)

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ['image', 'alt_text', 'display_order', 'is_main']
    readonly_fields = ['image_preview']
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" />', obj.image.url)
        return "No image"
    image_preview.short_description = "Preview"

class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ['name', 'value', 'sku', 'price', 'quantity', 'is_default']

class ProductAttributeInline(admin.TabularInline):
    model = ProductAttribute
    extra = 1
    fields = ['name', 'value', 'display_order']

class StockHistoryInline(admin.TabularInline):
    model = StockHistory
    extra = 0
    fields = ['action', 'quantity_change', 'new_quantity', 'notes', 'performed_by', 'created_at']
    readonly_fields = ['created_at']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'product_count', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ['name']}
    ordering = ['name']
    
    def product_count(self, obj):
        return obj.products.count()
    product_count.short_description = 'Products'

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'vendor_info', 'category', 'price', 'available_quantity', 
        'status_badge', 'is_featured', 'created_at'
    ]
    list_filter = [
        'status', 'is_featured', 'is_available', 'category', 
        'vendor', 'created_at'
    ]
    search_fields = ['name', 'description', 'sku', 'vendor__username']
    readonly_fields = [
        'view_count', 'purchase_count', 'average_rating', 
        'reservation_count', 'last_restocked', 'published_at'
    ]
    prepopulated_fields = {'slug': ['name']}
    inlines = [ProductImageInline, ProductVariantInline, ProductAttributeInline, StockHistoryInline]
    actions = [
        'activate_products', 'deactivate_products', 'mark_as_featured', 
        'mark_as_not_featured', 'export_products_csv'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'short_description', 'vendor')
        }),
        ('Pricing', {
            'fields': ('price', 'compare_at_price')
        }),
        ('Inventory', {
            'fields': ('sku', 'barcode', 'quantity', 'low_stock_threshold', 
                      'is_track_inventory', 'allow_backorder', 'reservation_count')
        }),
        ('Categorization', {
            'fields': ('category', 'tags')
        }),
        ('Status & Visibility', {
            'fields': ('status', 'is_featured', 'is_available', 'requires_shipping')
        }),
        ('Images', {
            'fields': ('main_image',)
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description')
        }),
        ('Statistics', {
            'fields': ('view_count', 'purchase_count', 'average_rating', 
                      'last_restocked', 'published_at'),
            'classes': ('collapse',)
        }),
    )
    
    def vendor_info(self, obj):
        if hasattr(obj.vendor, 'vendorprofile'):
            return obj.vendor.vendorprofile.business_name
        return obj.vendor.username
    vendor_info.short_description = 'Vendor'
    
    def available_quantity(self, obj):
        available = obj.get_available_quantity()
        if obj.is_track_inventory:
            if available <= obj.low_stock_threshold:
                return format_html('<span style="color: orange;">{}</span>', available)
            elif available == 0:
                return format_html('<span style="color: red;">{}</span>', available)
        return available
    available_quantity.short_description = 'Available Qty'
    
    def status_badge(self, obj):
        colors = {
            'active': 'green',
            'draft': 'gray',
            'out_of_stock': 'red',
            'discontinued': 'black',
            'pending_review': 'orange',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 10px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def activate_products(self, request, queryset):
        updated = queryset.update(status='active', is_available=True, published_at=timezone.now())
        self.message_user(request, f'{updated} products activated.')
    activate_products.short_description = "Activate selected products"
    
    def deactivate_products(self, request, queryset):
        updated = queryset.update(status='draft', is_available=False)
        self.message_user(request, f'{updated} products deactivated.')
    deactivate_products.short_description = "Deactivate selected products"
    
    def mark_as_featured(self, request, queryset):
        updated = queryset.update(is_featured=True)
        self.message_user(request, f'{updated} products marked as featured.')
    mark_as_featured.short_description = "Mark as featured"
    
    def mark_as_not_featured(self, request, queryset):
        updated = queryset.update(is_featured=False)
        self.message_user(request, f'{updated} products marked as not featured.')
    mark_as_not_featured.short_description = "Mark as not featured"

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ['product', 'image_preview', 'display_order', 'is_main', 'created_at']
    list_filter = ['is_main', 'created_at']
    search_fields = ['product__name', 'alt_text']
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" />', obj.image.url)
        return "No image"
    image_preview.short_description = "Image"

@admin.register(ProductTag)
class ProductTagAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'product_count', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ['name']}
    
    def product_count(self, obj):
        return obj.product_set.count()
    product_count.short_description = 'Products'

@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ['product', 'customer', 'rating_stars', 'is_approved', 'is_verified_purchase', 'created_at']
    list_filter = ['rating', 'is_approved', 'is_verified_purchase', 'created_at']
    search_fields = ['product__name', 'customer__username', 'title', 'comment']
    actions = ['approve_reviews', 'reject_reviews']
    
    def rating_stars(self, obj):
        stars = '★' * obj.rating + '☆' * (5 - obj.rating)
        return format_html('<span style="color: gold; font-size: 16px;">{}</span>', stars)
    rating_stars.short_description = 'Rating'
    
    def approve_reviews(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f'{updated} reviews approved.')
    approve_reviews.short_description = "Approve selected reviews"
    
    def reject_reviews(self, request, queryset):
        updated = queryset.update(is_approved=False)
        self.message_user(request, f'{updated} reviews rejected.')
    reject_reviews.short_description = "Reject selected reviews"

@admin.register(StockHistory)
class StockHistoryAdmin(admin.ModelAdmin):
    list_display = ['product', 'action', 'quantity_change', 'new_quantity', 'performed_by', 'created_at']
    list_filter = ['action', 'created_at']
    search_fields = ['product__name', 'notes', 'reference']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'