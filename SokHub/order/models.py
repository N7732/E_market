# orders/models.py
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import F, Q
from decimal import Decimal
import uuid
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from io import BytesIO
from django.core.files.base import ContentFile
import os

class Order(models.Model):
    """Main order model"""
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    )
    
    PAYMENT_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )
    
    PAYMENT_METHOD_CHOICES = (
        ('momo', 'MTN Momo'),
        ('cash', 'Cash on Delivery'),
        ('card', 'Credit Card'),
    )
    
    # Order Identification
    order_number = models.CharField(max_length=20, unique=True, editable=False)
    short_code = models.CharField(max_length=8, unique=True, editable=False)
    
    # Customer Information
    customer = models.ForeignKey('customer.User', on_delete=models.CASCADE, 
                                related_name='orders', limit_choices_to={'user_type': 'customer'})
    
    # Vendor Information (for vendor-specific orders)
    vendor = models.ForeignKey('customer.User', on_delete=models.CASCADE, 
                              related_name='vendor_orders', limit_choices_to={'user_type': 'vendor'},
                              null=True, blank=True)
    
    # Shipping Information
    shipping_address = models.TextField()
    shipping_city = models.CharField(max_length=100)
    shipping_phone = models.CharField(max_length=15)
    shipping_notes = models.TextField(blank=True, null=True)
    
    # Payment Information
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='momo')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    momo_number = models.CharField(max_length=15, blank=True, null=True)
    momo_transaction_id = models.CharField(max_length=100, blank=True, null=True)
    payment_date = models.DateTimeField(null=True, blank=True)
    
    # Order Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    status_changed_at = models.DateTimeField(auto_now_add=True)
    
    # Pricing
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # PDF Invoice
    invoice_pdf = models.FileField(upload_to='invoices/', null=True, blank=True)
    invoice_number = models.CharField(max_length=20, unique=True, editable=False)
    
    # Customer Notes
    customer_notes = models.TextField(blank=True, null=True)
    
    # Deletion Request
    delete_requested = models.BooleanField(default=False)
    delete_request_reason = models.TextField(blank=True, null=True)
    delete_requested_at = models.DateTimeField(null=True, blank=True)
    delete_approved = models.BooleanField(default=False)
    delete_approved_by = models.ForeignKey('customer.User', on_delete=models.SET_NULL, 
                                          null=True, blank=True, related_name='approved_deletions')
    delete_approved_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_number']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['vendor', 'status']),
            models.Index(fields=['status', 'payment_status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Order #{self.order_number} - {self.customer.username}"
    
    def save(self, *args, **kwargs):
        # Generate order number if new
        if not self.order_number:
            self.order_number = self.generate_order_number()
            self.short_code = self.order_number[-8:]
            self.invoice_number = f"INV-{self.order_number}"
        
        # Update status changed timestamp if status changed
        if self.pk:
            old_status = Order.objects.get(pk=self.pk).status
            if old_status != self.status:
                self.status_changed_at = timezone.now()
        
        super().save(*args, **kwargs)
    
    def generate_order_number(self):
        """Generate unique order number"""
        timestamp = timezone.now().strftime('%Y%m%d')
        random_part = uuid.uuid4().hex[:6].upper()
        return f"ORD-{timestamp}-{random_part}"
    
    def calculate_totals(self):
        """Calculate order totals from items"""
        subtotal = sum(item.total_price for item in self.items.all())
        self.subtotal = subtotal
        self.total_amount = subtotal + self.shipping_cost + self.tax_amount - self.discount_amount
        self.save()
    
    def get_absolute_url(self):
        return f"/orders/{self.order_number}/"
    
    def get_customer_dashboard_url(self):
        return f"/customer/orders/{self.order_number}/"
    
    def get_vendor_dashboard_url(self):
        return f"/vendor/orders/{self.order_number}/"
    
    def generate_invoice_pdf(self):
        """Generate PDF invoice for order"""
        buffer = BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.HexColor('#000000')
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=12,
            textColor=colors.HexColor('#000000')
        )
        
        normal_style = styles['Normal']
        normal_style.fontSize = 10
        
        # Story (content)
        story = []
        
        # Title
        story.append(Paragraph("SokHub Invoice", title_style))
        story.append(Spacer(1, 20))
        
        # Order Information
        order_info = [
            ['Invoice Number:', self.invoice_number],
            ['Order Number:', self.order_number],
            ['Date:', self.created_at.strftime('%B %d, %Y')],
            ['Status:', self.get_status_display()],
        ]
        
        order_table = Table(order_info, colWidths=[2*inch, 3*inch])
        order_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(order_table)
        story.append(Spacer(1, 20))
        
        # Two columns for addresses
        addresses_data = [
            [
                Paragraph("<b>Billed To:</b>", normal_style),
                Paragraph("<b>Shipped To:</b>", normal_style)
            ],
            [
                Paragraph(f"{self.customer.get_full_name() or self.customer.username}<br/>"
                         f"{self.customer.email}<br/>"
                         f"{self.customer.phone}", normal_style),
                Paragraph(f"{self.customer.get_full_name() or self.customer.username}<br/>"
                         f"{self.shipping_address}<br/>"
                         f"{self.shipping_city}<br/>"
                         f"Phone: {self.shipping_phone}", normal_style)
            ]
        ]
        
        addresses_table = Table(addresses_data, colWidths=[2.5*inch, 2.5*inch])
        story.append(addresses_table)
        story.append(Spacer(1, 30))
        
        # Order Items
        story.append(Paragraph("Order Items", heading_style))
        
        items_data = [['Product', 'Quantity', 'Unit Price', 'Total']]
        for item in self.items.all():
            items_data.append([
                item.product.name,
                str(item.quantity),
                f"RWF {item.price:.2f}",
                f"RWF {item.total_price:.2f}"
            ])
        
        items_table = Table(items_data, colWidths=[2.5*inch, 1*inch, 1.5*inch, 1.5*inch])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#000000')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ]))
        
        story.append(items_table)
        story.append(Spacer(1, 30))
        
        # Order Summary
        summary_data = [
            ['Subtotal:', f"RWF {self.subtotal:.2f}"],
            ['Shipping Cost:', f"RWF {self.shipping_cost:.2f}"],
            ['Tax:', f"RWF {self.tax_amount:.2f}"],
            ['Discount:', f"-RWF {self.discount_amount:.2f}"],
            ['', ''],
            ['<b>Total Amount:</b>', f"<b>RWF {self.total_amount:.2f}</b>"]
        ]
        
        summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, -2), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -2), 10),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 12),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
        ]))
        
        story.append(summary_table)
        story.append(Spacer(1, 30))
        
        # Payment Information
        if self.payment_method == 'momo' and self.momo_number:
            story.append(Paragraph("Payment Information", heading_style))
            payment_info = f"Paid via MTN Momo to: {self.momo_number}"
            if self.momo_transaction_id:
                payment_info += f"<br/>Transaction ID: {self.momo_transaction_id}"
            story.append(Paragraph(payment_info, normal_style))
        
        # Footer
        story.append(Spacer(1, 50))
        footer = Paragraph(
            "Thank you for shopping with SokHub!<br/>"
            "For any questions, contact support@sookhub.com",
            ParagraphStyle(
                'Footer',
                parent=normal_style,
                alignment=1,  # Center aligned
                textColor=colors.grey
            )
        )
        story.append(footer)
        
        # Build PDF
        doc.build(story)
        
        # Save to model
        pdf_content = buffer.getvalue()
        buffer.close()
        
        filename = f"invoice_{self.invoice_number}.pdf"
        self.invoice_pdf.save(filename, ContentFile(pdf_content), save=False)
        self.save()
        
        return filename
    
    def can_be_cancelled(self):
        """Check if order can be cancelled"""
        return self.status in ['pending', 'confirmed', 'processing']
    
    def request_deletion(self, reason):
        """Request order deletion"""
        self.delete_requested = True
        self.delete_request_reason = reason
        self.delete_requested_at = timezone.now()
        self.save()
    
    def approve_deletion(self, approved_by):
        """Approve order deletion"""
        self.delete_approved = True
        self.delete_approved_by = approved_by
        self.delete_approved_at = timezone.now()
        self.status = 'cancelled'
        self.save()
        
        # Restore stock
        for item in self.items.all():
            item.restore_stock()
    
    def mark_as_paid(self, momo_number=None, transaction_id=None):
        """Mark order as paid"""
        self.payment_status = 'completed'
        self.payment_date = timezone.now()
        if momo_number:
            self.momo_number = momo_number
        if transaction_id:
            self.momo_transaction_id = transaction_id
        self.status = 'confirmed'
        self.save()
        
        # Commit stock (convert reservations to actual sales)
        for item in self.items.all():
            item.commit_stock()
            
    def save(self, *args, **kwargs):
        # Generate order number if not set
        if not self.order_number:
            self.order_number = self.generate_order_number()
        
        # Ensure uniqueness even if manually set
        if self.pk is None:  # New order
            while Order.objects.filter(order_number=self.order_number).exists():
                self.order_number = self.generate_order_number()
        
        super().save(*args, **kwargs)
    
    def generate_order_number(self):
        """Generate unique order number"""
        date_str = timezone.now().strftime("%Y%m%d")
        unique_id = uuid.uuid4().hex[:6].upper()
        return f"ORD-{date_str}-{unique_id}"

class OrderItem(models.Model):
    """Individual items in an order"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('product.Product', on_delete=models.PROTECT, related_name='order_items')
    vendor = models.ForeignKey('customer.User', on_delete=models.CASCADE, 
                              limit_choices_to={'user_type': 'vendor'})
    
    # Product details at time of purchase
    product_name = models.CharField(max_length=200)
    product_sku = models.CharField(max_length=100, blank=True, null=True)
    product_image_url = models.URLField(blank=True, null=True)
    
    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    total_price = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    
    # Status
    is_cancelled = models.BooleanField(default=False)
    cancellation_reason = models.TextField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.quantity}x {self.product_name} in Order #{self.order.order_number}"
    
    def save(self, *args, **kwargs):
        # Calculate total price
        self.total_price = self.price * self.quantity
        
        # Set vendor from product
        if self.product and not self.vendor:
            self.vendor = self.product.vendor
        
        # Save product details
        if self.product and not self.product_name:
            self.product_name = self.product.name
            self.product_sku = self.product.sku
            if self.product.main_image:
                self.product_image_url = self.product.main_image.url
        
        super().save(*args, **kwargs)
        
        # Update order totals
        if self.order:
            self.order.calculate_totals()
    
    def reserve_stock(self):
        """Reserve stock for this item"""
        if self.product.is_track_inventory:
            return self.product.reserve_stock(self.quantity)
        return True
    
    def commit_stock(self):
        """Commit reserved stock to sale"""
        if self.product.is_track_inventory and not self.is_cancelled:
            self.product.commit_stock(self.quantity)
    
    def restore_stock(self):
        """Restore stock if order is cancelled"""
        if self.product.is_track_inventory and not self.is_cancelled:
            # Release reserved stock
            self.product.release_stock(self.quantity)
            self.is_cancelled = True
            self.save()

class OrderStatusHistory(models.Model):
    """Track order status changes"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    notes = models.TextField(blank=True, null=True)
    changed_by = models.ForeignKey('customer.User', on_delete=models.SET_NULL, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-changed_at']
    
    def __str__(self):
        return f"Order #{self.order.order_number}: {self.old_status} → {self.new_status}"

class Cart(models.Model):
    """Shopping cart for customers"""
    customer = models.OneToOneField('customer.User', on_delete=models.CASCADE, 
                                   related_name='cart', limit_choices_to={'user_type': 'customer'})
    session_key = models.CharField(max_length=40, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Cart for {self.customer.username}"
    
    def get_total(self):
        return sum(item.get_total() for item in self.items.all())
    
    def get_item_count(self):
        return self.items.count()
    
    def clear(self):
        """Clear cart and release reserved stock"""
        with transaction.atomic():
            for item in self.items.all():
                item.release_stock()
                item.delete()

class CartItem(models.Model):
    """Items in shopping cart"""
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('product.Product', on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    added_at = models.DateTimeField(auto_now_add=True)
    #get_total_price = models.DecimalField(max_digits=10, decimal_places=2, editable=False,null=True,default=0.00)
    
    class Meta:
        unique_together = ['cart', 'product']
    
    def __str__(self):
        return f"{self.quantity}x {self.product.name} in cart"
    
    def save(self, *args, **kwargs):
        # Reserve stock when adding to cart
        if self.pk is None:  # New item
            if not self.product.reserve_stock(self.quantity):
                raise ValidationError(f"Not enough stock for {self.product.name}. Available: {self.product.get_available_quantity()}")
        else:  # Updating quantity
            old_quantity = CartItem.objects.get(pk=self.pk).quantity
            quantity_diff = self.quantity - old_quantity
            
            if quantity_diff > 0:
                if not self.product.reserve_stock(quantity_diff):
                    raise ValidationError(f"Not enough stock for {self.product.name}. Available: {self.product.get_available_quantity()}")
            elif quantity_diff < 0:
                self.product.release_stock(abs(quantity_diff))
        
        super().save(*args, **kwargs)

    def get_total_price(self):
        return self.product.price * self.quantity
    
    
    def delete(self, *args, **kwargs):
        # Release reserved stock when removing from cart
        if self.product.is_track_inventory:
            self.product.release_stock(self.quantity)
        super().delete(*args, **kwargs)
    
    def get_total(self):
        return self.product.price * self.quantity
    
    def can_be_added(self, additional_quantity=1):
        """Check if additional quantity can be added to cart"""
        if not self.product.is_track_inventory:
            return True
        
        total_quantity = self.quantity + additional_quantity
        return self.product.can_fulfill_order(total_quantity)

class OrderNotification(models.Model):
    """Notifications for order status changes"""
    TYPE_CHOICES = (
        ('status_change', 'Status Change'),
        ('payment_received', 'Payment Received'),
        ('shipping_update', 'Shipping Update'),
        ('deletion_request', 'Deletion Request'),
        ('vendor_message', 'Vendor Message'),
    )
    
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    recipient = models.ForeignKey('customer.User', on_delete=models.CASCADE, related_name='order_notifications')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_notification_type_display()} for Order #{self.order.order_number}"

# Signals
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

@receiver(pre_save, sender=Order)
def update_order_status_history(sender, instance, **kwargs):
    """Create status history when order status changes"""
    if instance.pk:
        old_order = Order.objects.get(pk=instance.pk)
        if old_order.status != instance.status:
            OrderStatusHistory.objects.create(
                order=instance,
                old_status=old_order.status,
                new_status=instance.status,
                changed_by=instance.customer  # In real app, track who changed it
            )

@receiver(post_save, sender=Order)
def create_order_notification(sender, instance, created, **kwargs):
    """Create notifications for order events"""
    if created:
        # Notification to customer
        OrderNotification.objects.create(
            order=instance,
            notification_type='status_change',
            recipient=instance.customer,
            message=f"Your order #{instance.order_number} has been placed successfully and is now pending."
        )
        
        # Notification to vendor (if single vendor order)
        if instance.vendor:
            OrderNotification.objects.create(
                order=instance,
                notification_type='status_change',
                recipient=instance.vendor,
                message=f"New order #{instance.order_number} received from {instance.customer.username}."
            )
    
    # Notification for deletion request
    if instance.delete_requested and not instance.delete_approved:
        # Notify vendor
        if instance.vendor:
            OrderNotification.objects.create(
                order=instance,
                notification_type='deletion_request',
                recipient=instance.vendor,
                message=f"Customer {instance.customer.username} has requested to delete order #{instance.order_number}. Reason: {instance.delete_request_reason}"
            )

@receiver(post_save, sender=CartItem)
def update_cart_timestamp(sender, instance, **kwargs):
    """Update cart timestamp when items change"""
    instance.cart.updated_at = timezone.now()
    instance.cart.save()
