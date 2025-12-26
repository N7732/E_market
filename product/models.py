# products/models.py
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import F, Q
from decimal import Decimal
import uuid
from django.conf import settings
import os
from django.db.models.expressions import CombinedExpression
from django.utils.timezone import now
from django.db import transaction

def image_path(instance, filename):

    ext = filename.split('.')[-1].lower()
    
    # Generate unique filename to prevent conflicts
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    date_path = now().strftime("%Y/%m")
    full_path = os.path.join("products", date_path, filename)
    
    # Ensure directory exists
    media_dir = os.path.join(settings.MEDIA_ROOT, "products", date_path)
    os.makedirs(media_dir, exist_ok=True)
    return full_path


class Category(models.Model):
    """Product categories for better organization"""
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, 
                              related_name='children')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        return f"/products/category/{self.slug}/"
    
    def get_all_children(self):
        """Get all descendant categories"""
        children = list(self.children.all())
        for child in self.children.all():
            children.extend(child.get_all_children())
        return children

class Product(models.Model):
    """Main product model with inventory tracking"""
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('out_of_stock', 'Out of Stock'),
        ('discontinued', 'Discontinued'),
        ('pending_review', 'Pending Review'),
    )
    
    # Basic Information
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField()
    short_description = models.CharField(max_length=300, blank=True, null=True)
    
    # Vendor Relationship
    vendor = models.ForeignKey('customer.User', on_delete=models.CASCADE, 
                              limit_choices_to={'user_type': 'vendor'},
                              related_name='products')
    
    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2, 
                               validators=[MinValueValidator(Decimal('0.01'))])
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, 
                                          null=True, blank=True,
                                          validators=[MinValueValidator(Decimal('0.01'))])
    
    # Inventory Management
    sku = models.CharField(max_length=100, unique=True, blank=True, null=True)
    barcode = models.CharField(max_length=100, blank=True, null=True)
    quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    low_stock_threshold = models.IntegerField(default=5, validators=[MinValueValidator(1)])
    is_track_inventory = models.BooleanField(default=True)
    allow_backorder = models.BooleanField(default=False)
    
    # Categories & Tags
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, 
                                null=True, blank=True, related_name='products')
    tags = models.ManyToManyField('ProductTag', blank=True)
    
    # Status & Visibility
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    is_featured = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)
    requires_shipping = models.BooleanField(default=True)
    
    # Images
    main_image = models.ImageField(upload_to=image_path, null=True, blank=True)
    
    # SEO
    meta_title = models.CharField(max_length=200, blank=True, null=True)
    meta_description = models.TextField(blank=True, null=True)
    
    # Statistics
    view_count = models.IntegerField(default=0)
    purchase_count = models.IntegerField(default=0)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00,
                                        validators=[MinValueValidator(0), MaxValueValidator(5)])
    
    # Conflict Prevention
    reservation_count = models.IntegerField(default=0)  # Items reserved in carts
    last_restocked = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['status', 'is_available']),
            models.Index(fields=['vendor', 'status']),
            models.Index(fields=['category', 'is_available']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.vendor.vendorprofile.business_name if hasattr(self.vendor, 'vendorprofile') else self.vendor.username}"
    
    def save(self, *args, **kwargs):
        # Generate SKU if not provided
        if not self.sku:
            self.sku = f"PROD-{uuid.uuid4().hex[:8].upper()}"
        
        # Update status based on quantity
        if self.is_track_inventory and self.quantity <= 0 and not self.allow_backorder:
            self.status = 'out_of_stock'
            self.is_available = False
        elif self.status == 'out_of_stock' and self.quantity > 0:
            self.status = 'active'
            self.is_available = True
        
        # Set published date if publishing for first time
        if self.status == 'active' and not self.published_at:
            self.published_at = timezone.now()
        
        super().save(*args, **kwargs)
    
    def get_absolute_url(self):
        return f"/products/{self.slug}/"
    
    def get_available_quantity(self):
        """Get available quantity after deducting reservations"""
    # SIMPLE VERSION - just do the calculation
        try:
            return max(0, self.quantity - self.reservation_count)
        except:
            # If there's any error, return a safe value
            return 0
        

    def is_in_stock(self):
        """Check if product is in stock"""
        if not self.is_track_inventory:
            return True
        if self.allow_backorder:
            return True
        return self.get_available_quantity() > 0
    
    def can_fulfill_order(self, quantity):
        """Check if product can fulfill order quantity"""
        if not self.is_track_inventory:
            return True
        if self.allow_backorder:
            return True
        return self.get_available_quantity() >= quantity
    
    def reserve_stock(self, quantity):
        """Reserve stock for pending order (prevents overselling)"""
        if not self.is_track_inventory:
            return True
        
        with transaction.atomic():
            # Lock the product row for update
            product = Product.objects.select_for_update().get(pk=self.pk)
            available_qty = product.quantity - product.reservation_count
            
            if not product.allow_backorder and product.get_available_quantity() < quantity:
                return False
            
            product.reservation_count = F('reservation_count') + quantity
            product.save(update_fields=['reservation_count'])
            
            # Refresh from database
            product.refresh_from_db()
            return True
    
    def release_stock(self, quantity):
        """Release reserved stock"""
        if not self.is_track_inventory:
            return
        
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=self.pk)
            product.reservation_count = F('reservation_count') - quantity
            product.save(update_fields=['reservation_count'])
    
    def commit_stock(self, quantity):
        """Commit reserved stock to actual sale"""
        if not self.is_track_inventory:
            return
        
        with transaction.atomic():
            # Use direct update and get the result
            from django.db.models import F
            
            # Update using F() expressions
            updated = Product.objects.filter(pk=self.pk).update(
                quantity=F('quantity') - quantity,
                reservation_count=F('reservation_count') - quantity,
                purchase_count=F('purchase_count') + quantity
            )
            
            if updated:
                # Refresh to get actual values
                self.refresh_from_db()
                
                # Now check if low stock (with actual integer values)
                if self.quantity <= self.low_stock_threshold:
                    self.last_restocked = timezone.now()
                    self.save(update_fields=['last_restocked'])
    
    
    
    def restock(self, quantity):
        """Add stock to product"""
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=self.pk)
            product.quantity = F('quantity') + quantity
            product.last_restocked = timezone.now()
            
            # Update status if was out of stock
            if product.status == 'out_of_stock' and product.quantity > 0:
                product.status = 'active'
                product.is_available = True
            
            product.save(update_fields=['quantity', 'last_restocked', 'status', 'is_available'])
    
    def get_discount_percentage(self):
        """Calculate discount percentage if compare price exists"""
        if self.compare_at_price and self.compare_at_price > self.price:
            discount = ((self.compare_at_price - self.price) / self.compare_at_price) * 100
            return round(discount, 0)
        return 0
    
    def get_discount_amount(self):
        """Return the absolute discount amount for display"""
        if self.compare_at_price and self.compare_at_price > self.price:
            return self.compare_at_price - self.price
        return Decimal('0.00')
    
    def increment_view_count(self):
        """Increment view count"""
        self.view_count = F('view_count') + 1
        self.save(update_fields=['view_count'])
    
    def update_rating(self, new_rating):
        """Update average rating"""
        # This would be called from ProductReview model
        reviews = self.reviews.filter(is_approved=True)
        if reviews.exists():
            self.average_rating = reviews.aggregate(avg=models.Avg('rating'))['avg']
            self.save(update_fields=['average_rating'])

class ProductImage(models.Model):
    """Additional product images"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to=image_path)
    alt_text = models.CharField(max_length=200, blank=True, null=True)
    display_order = models.IntegerField(default=0)
    is_main = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['display_order', 'created_at']
    
    def save(self, *args, **kwargs):
        # If this is set as main, update other images
        if self.is_main:
            ProductImage.objects.filter(product=self.product).exclude(pk=self.pk).update(is_main=False)
        super().save(*args, **kwargs)

class ProductVariant(models.Model):
    """Product variants (size, color, etc.)"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    name = models.CharField(max_length=100)  # e.g., "Size", "Color"
    value = models.CharField(max_length=100)  # e.g., "Large", "Red"
    sku = models.CharField(max_length=100, unique=True, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    quantity = models.IntegerField(default=0)
    is_default = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ['product', 'name', 'value']
    
    def __str__(self):
        return f"{self.product.name} - {self.name}: {self.value}"

class ProductTag(models.Model):
    """Tags for product categorization and search"""
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class ProductReview(models.Model):
    """Customer reviews for products"""
    RATING_CHOICES = (
        (1, '1 Star'),
        (2, '2 Stars'),
        (3, '3 Stars'),
        (4, '4 Stars'),
        (5, '5 Stars'),
    )
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    customer = models.ForeignKey('customer.User', on_delete=models.CASCADE, 
                                limit_choices_to={'user_type': 'customer'})
    rating = models.IntegerField(choices=RATING_CHOICES)
    title = models.CharField(max_length=200)
    comment = models.TextField()
    is_approved = models.BooleanField(default=False)  # Vendor/admin must approve
    is_verified_purchase = models.BooleanField(default=False)
    
    # Helpful votes
    helpful_count = models.IntegerField(default=0)
    not_helpful_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['product', 'customer']  # One review per customer per product
    
    def __str__(self):
        return f"{self.product.name} - {self.customer.username}: {self.rating} stars"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update product's average rating
        if self.is_approved:
            self.product.update_rating(self.rating)

class ProductAttribute(models.Model):
    """Attributes for product specifications"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='attributes')
    name = models.CharField(max_length=100)  # e.g., "Weight", "Material"
    value = models.CharField(max_length=200)  # e.g., "1kg", "Cotton"
    display_order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['display_order', 'name']
    
    def __str__(self):
        return f"{self.name}: {self.value}"

class StockHistory(models.Model):
    """Track stock changes for inventory management"""
    ACTION_CHOICES = (
        ('purchase', 'Purchase'),
        ('sale', 'Sale'),
        ('adjustment', 'Adjustment'),
        ('return', 'Return'),
        ('reservation', 'Reservation'),
        ('release', 'Release'),
        ('damage', 'Damage'),
        ('expiry', 'Expiry'),
    )
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_history')
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    quantity_change = models.IntegerField()  # Positive for addition, negative for deduction
    new_quantity = models.IntegerField()
    notes = models.TextField(blank=True, null=True)
    reference = models.CharField(max_length=100, blank=True, null=True)  # Order ID, etc.
    performed_by = models.ForeignKey('customer.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Stock Histories"
    
    def __str__(self):
        return f"{self.product.name} - {self.action}: {self.quantity_change}"

# Signal to create stock history
@receiver(post_save, sender=Product)
def create_initial_stock_history(sender, instance, created, **kwargs):
    if created and instance.is_track_inventory:
        StockHistory.objects.create(
            product=instance,
            action='adjustment',
            quantity_change=instance.quantity,
            new_quantity=instance.quantity,
            notes='Initial stock',
            performed_by=instance.vendor
        )

class ProductAnalytics(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="analytics")
    sales_count = models.IntegerField(default=0)
    report_date = models.DateField()
    
    class Meta:
        ordering = ['-report_date']

    def __str__(self):
        return f"{self.product.name} - {self.sales_count} sales on {self.report_date}"

