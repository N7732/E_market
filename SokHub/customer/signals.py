from django.db.models.signals import post_save
from django.dispatch import receiver
from customer.models import User, VendorProfile


@receiver(post_save, sender=User)
def create_vendor_profile(sender, instance, created, **kwargs):
    """Auto-create VendorProfile when vendor user is created"""
    if created and instance.user_type == 'vendor':
        VendorProfile.objects.get_or_create(user=instance)
