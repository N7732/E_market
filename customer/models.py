
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

class User(AbstractUser):
    USER_TYPE_CHOICES = (
        ('vendor', 'Vendor'),
        ('customer', 'Customer'),
        ('admin', 'Admin'),
    )
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='customer')
    phone = models.CharField(max_length=15, unique=True)
    location = models.TextField()
    email = models.EmailField(unique=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    is_email_verified = models.BooleanField(default=False)
    def __str__(self):
        return f"{self.username} ({self.get_user_type_display()})"
    def is_vendor_approved(self):
        """Check if vendor is approved by admin"""
        if self.user_type == 'vendor' and hasattr(self, 'vendorprofile'):
            return self.vendorprofile.is_approved
        return False

    def get_dashboard_url(self):

        """Get appropriate dashboard based on user type"""
        if self.user_type == 'vendor':
            return '/vendor/dashboard/'
        elif self.user_type == 'customer':
            return '/customer/dashboard/'
        elif self.user_type == 'admin' or self.is_staff:
            return '/admin/'
        return '/'
    
class VendorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='vendorprofile')
    business_name = models.CharField(max_length=200)
    business_address = models.TextField()
    tax_id = models.CharField(max_length=50, blank=True, null=True)
    default_momo_number = models.CharField(max_length=15)
    admin_override_momo = models.CharField(max_length=15, blank=True, null=True, 
                                          help_text="Admin can set different Momo number for this vendor")
    
    # Approval system
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, 
                                   related_name='approved_vendors')
    approved_date = models.DateTimeField(null=True, blank=True)
    
    # Business details
    business_description = models.TextField(blank=True, null=True)
    business_logo = models.ImageField(upload_to='vendor_logos/', blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_sales = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.business_name
    
    def get_momo_number(self):
        """Get Momo number - admin override takes priority"""
        return self.admin_override_momo or self.default_momo_number
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Vendor Profile"
        verbose_name_plural = "Vendor Profiles"

class CustomerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customerprofile')
    shipping_address = models.TextField()
    preferred_payment = models.CharField(
        max_length=20, 
        choices=[('momo', 'MTN Momo'), ('cash', 'Cash on Delivery'), ('card', 'Credit Card')],
        default='momo'
    )
    default_momo_number = models.CharField(max_length=15, blank=True, null=True)
    
    # Customer preferences
    receive_promotions = models.BooleanField(default=True)
    newsletter_subscription = models.BooleanField(default=False)
    
    # Stats
    total_orders = models.IntegerField(default=0)
    total_spent = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Customer Profile"
        verbose_name_plural = "Customer Profiles"

# Signal to create profile when user is created
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.user_type == 'vendor':
            VendorProfile.objects.create(user=instance)
        elif instance.user_type == 'customer':
            CustomerProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if instance.user_type == 'vendor' and hasattr(instance, 'vendorprofile'):
        instance.vendorprofile.save()
    elif instance.user_type == 'customer' and hasattr(instance, 'customerprofile'):
        instance.customerprofile.save()
        
        # customer/models.py
from django.db import models
from django.utils import timezone
import random

class OTP(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(default=timezone.now)
    is_verified = models.BooleanField(default=False)

    def generate_code(self):
        self.code = str(random.randint(100000, 999999))
        self.created_at = timezone.now()
        self.save()
