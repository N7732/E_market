# orders/management/commands/fix_duplicate_orders.py
import uuid
from django.core.management.base import BaseCommand
from django.db.models import Count
from order.models import Order
from django.db import transaction
from django.utils import timezone

class Command(BaseCommand):
    help = 'Fix duplicate order numbers in the database'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes'
        )
        parser.add_argument(
            '--method',
            type=str,
            default='rename',
            choices=['rename', 'delete', 'keep_first'],
            help='Method to fix duplicates: rename (generate new numbers), delete (remove duplicates), keep_first (keep only first)'
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        method = options['method']
        
        # Find all duplicate order numbers
        duplicates = Order.objects.values('order_number').annotate(
            count=Count('id')
        ).filter(count__gt=1).order_by('order_number')
        
        total_duplicates = sum(dup['count'] - 1 for dup in duplicates)
        
        self.stdout.write(f"Found {duplicates.count()} duplicate order numbers")
        self.stdout.write(f"Total duplicate records: {total_duplicates}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN - No changes will be made\n"))
        
        fixed_count = 0
        deleted_count = 0
        
        with transaction.atomic():
            for dup in duplicates:
                order_number = dup['order_number']
                duplicate_count = dup['count']
                
                self.stdout.write(f"\n{'='*60}")
                self.stdout.write(f"Order Number: {order_number}")
                self.stdout.write(f"Duplicate Count: {duplicate_count}")
                self.stdout.write(f"{'='*60}")
                
                # Get all orders with this order number
                orders = Order.objects.filter(order_number=order_number).order_by('created_at')
                
                # Display duplicate orders
                for i, order in enumerate(orders):
                    self.stdout.write(f"{i+1}. ID: {order.id} | Customer: {order.customer} | "
                                    f"Created: {order.created_at} | Status: {order.status}")
                
                if method == 'rename':
                    # Keep all but rename duplicates
                    self.stdout.write("\nMethod: Rename duplicates (keep all orders)")
                    
                    for i, order in enumerate(orders):
                        if i == 0:
                            self.stdout.write(f"  ✓ Keeping ID {order.id} as {order.order_number}")
                        else:
                            new_order_number = self.generate_unique_order_number(order.created_at)
                            if not dry_run:
                                order.order_number = new_order_number
                                order.save()
                            self.stdout.write(f"  {'✓' if not dry_run else '∼'} Renaming ID {order.id} → {new_order_number}")
                            fixed_count += 1
                
                elif method == 'delete':
                    # Delete all but the first order
                    self.stdout.write("\nMethod: Delete duplicate orders (keep only first)")
                    
                    for i, order in enumerate(orders):
                        if i == 0:
                            self.stdout.write(f"  ✓ Keeping ID {order.id}")
                        else:
                            if not dry_run:
                                order.delete()
                            self.stdout.write(f"  {'✗' if not dry_run else '∼'} Deleting ID {order.id}")
                            deleted_count += 1
                
                elif method == 'keep_first':
                    # Keep only the first, rename others
                    self.stdout.write("\nMethod: Keep first order only")
                    
                    first_order = orders.first()
                    for i, order in enumerate(orders):
                        if i == 0:
                            self.stdout.write(f"  ✓ Keeping ID {order.id}")
                        else:
                            if not dry_run:
                                # Move items from duplicate to first order if needed
                                if order.items.exists():
                                    for item in order.items.all():
                                        item.order = first_order
                                        item.save()
                                
                                # Copy useful data if needed
                                if not first_order.shipping_notes and order.shipping_notes:
                                    first_order.shipping_notes = order.shipping_notes
                                    first_order.save()
                                
                                order.delete()
                            
                            self.stdout.write(f"  {'✗' if not dry_run else '∼'} Merging and deleting ID {order.id}")
                            deleted_count += 1
        
        # Summary
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write("SUMMARY")
        self.stdout.write(f"{'='*60}")
        
        if method == 'rename':
            self.stdout.write(f"Orders renamed: {fixed_count}")
        elif method in ['delete', 'keep_first']:
            self.stdout.write(f"Orders deleted: {deleted_count}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN COMPLETE - No changes were made"))
            self.stdout.write("Run without --dry-run to apply changes")
        else:
            self.stdout.write(self.style.SUCCESS("\nDUPLICATE FIX COMPLETE!"))
            
            # Verify fix
            remaining_duplicates = Order.objects.values('order_number').annotate(
                count=Count('id')
            ).filter(count__gt=1).count()
            
            if remaining_duplicates == 0:
                self.stdout.write(self.style.SUCCESS("✓ All duplicates have been fixed!"))
            else:
                self.stdout.write(self.style.WARNING(f"⚠ Warning: {remaining_duplicates} duplicate order numbers still exist"))
    
    def generate_unique_order_number(self, date):
        """Generate a unique order number based on date"""
        date_str = date.strftime("%Y%m%d")
        unique_id = uuid.uuid4().hex[:6].upper()
        new_number = f"ORD-{date_str}-{unique_id}"
        
        # Ensure uniqueness
        while Order.objects.filter(order_number=new_number).exists():
            unique_id = uuid.uuid4().hex[:6].upper()
            new_number = f"ORD-{date_str}-{unique_id}"
        
        return new_number