# orders/signals.py
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.db.models import Count
from .models import Order

@receiver(pre_save, sender=Order)
def check_duplicate_order_number(sender, instance, **kwargs):
    """Check for duplicate order numbers before saving"""
    if instance.order_number and instance.pk is None:  # New order
        if Order.objects.filter(order_number=instance.order_number).exists():
            # Generate new unique number
            from django.utils import timezone
            import uuid
            
            date_str = timezone.now().strftime("%Y%m%d")
            unique_id = uuid.uuid4().hex[:6].upper()
            instance.order_number = f"ORD-{date_str}-{unique_id}"
            
            # Ensure it's unique
            while Order.objects.filter(order_number=instance.order_number).exists():
                unique_id = uuid.uuid4().hex[:6].upper()
                instance.order_number = f"ORD-{date_str}-{unique_id}"