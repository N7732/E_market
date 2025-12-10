# customer/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from .models import User, VendorProfile, CustomerProfile
from django.utils import timezone
from .form import AdminUserCreationForm, AdminUserChangeForm, VendorApprovalForm

class CustomerProfileInline(admin.StackedInline):
    model = CustomerProfile
    can_delete = False
    verbose_name_plural = 'Customer Profile'
    fk_name = 'user'
    readonly_fields = ['total_orders', 'total_spent', 'created_at', 'updated_at']

class VendorProfileInline(admin.StackedInline):
    model = VendorProfile
    can_delete = False
    verbose_name_plural = 'Vendor Profile'
    fk_name = 'user'
    form = VendorApprovalForm
    readonly_fields = ['approved_date', 'total_sales', 'created_at', 'updated_at']

class UserAdmin(BaseUserAdmin):
    form = AdminUserChangeForm
    add_form = AdminUserCreationForm
    
    list_display = ('username', 'email', 'phone', 'user_type', 'is_staff', 'is_active', 'is_approved_vendor')
    list_filter = ('user_type', 'is_staff', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'phone', 'vendorprofile__business_name')
    ordering = ('-date_joined',)
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'email', 'phone', 'location')}),
        ('Account Type', {'fields': ('user_type',)}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2', 'user_type', 'phone', 'location'),
        }),
    )
    
    inlines = []
    
    def get_inlines(self, request, obj=None):
        if obj and obj.user_type == 'vendor':
            return [VendorProfileInline]
        elif obj and obj.user_type == 'customer':
            return [CustomerProfileInline]
        return []
    
    def is_approved_vendor(self, obj):
        if obj.user_type == 'vendor' and hasattr(obj, 'vendorprofile'):
            if obj.vendorprofile.is_approved:
                return format_html('<span style="color: green;">✓ Approved</span>')
            else:
                return format_html('<span style="color: red;">Pending</span>')
        return '-'
    is_approved_vendor.short_description = 'Vendor Status'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs

@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
    form = VendorApprovalForm
    list_display = ('business_name', 'user', 'get_phone', 'is_approved', 'is_active', 
                   'total_sales', 'rating', 'created_at')
    list_filter = ('is_approved', 'is_active', 'created_at')
    search_fields = ('business_name', 'user__username', 'user__email', 'user__phone')
    readonly_fields = ('created_at', 'updated_at', 'approved_date', 'total_sales')
    actions = ['approve_vendors', 'reject_vendors', 'activate_vendors', 'deactivate_vendors']
    
    fieldsets = (
        ('Business Information', {
            'fields': ('user', 'business_name', 'business_address', 'tax_id', 
                      'business_description', 'website', 'business_logo')
        }),
        ('Payment Information', {
            'fields': ('default_momo_number', 'admin_override_momo'),
            'description': 'Admin override Momo takes priority over vendor\'s default'
        }),
        ('Approval & Status', {
            'fields': ('is_approved', 'approved_by', 'approved_date', 'is_active', 'rating')
        }),
        ('Statistics', {
            'fields': ('total_sales',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_phone(self, obj):
        return obj.user.phone
    get_phone.short_description = 'Phone'
    
    def approve_vendors(self, request, queryset):
        updated = queryset.update(is_approved=True, approved_by=request.user, approved_date=timezone.now())
        self.message_user(request, f'{updated} vendors approved successfully.')
    approve_vendors.short_description = "Approve selected vendors"
    
    def reject_vendors(self, request, queryset):
        updated = queryset.update(is_approved=False)
        self.message_user(request, f'{updated} vendors rejected.')
    reject_vendors.short_description = "Reject selected vendors"
    
    def activate_vendors(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} vendors activated.')
    activate_vendors.short_description = "Activate selected vendors"
    
    def deactivate_vendors(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} vendors deactivated.')
    deactivate_vendors.short_description = "Deactivate selected vendors"
    
    def save_model(self, request, obj, form, change):
        if 'is_approved' in form.changed_data and obj.is_approved:
            obj.approved_by = request.user
            obj.approved_date = timezone.now()
        super().save_model(request, obj, form, change)

@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_email', 'get_phone', 'total_orders', 'total_spent', 'created_at')
    list_filter = ('preferred_payment', 'created_at')
    search_fields = ('user__username', 'user__email', 'user__phone', 'shipping_address')
    readonly_fields = ('total_orders', 'total_spent', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Customer Information', {
            'fields': ('user', 'shipping_address')
        }),
        ('Payment Preferences', {
            'fields': ('preferred_payment', 'default_momo_number')
        }),
        ('Preferences', {
            'fields': ('receive_promotions', 'newsletter_subscription')
        }),
        ('Statistics', {
            'fields': ('total_orders', 'total_spent')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'
    
    def get_phone(self, obj):
        return obj.user.phone
    get_phone.short_description = 'Phone'

# Unregister default User admin and register our custom one
admin.site.unregister(User) if User in admin.site._registry else None
admin.site.register(User, UserAdmin)