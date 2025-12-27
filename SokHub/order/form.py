# orders/forms.py
import re
from django import forms
from django.core.validators import MinValueValidator
from .models import Order, CartItem, OrderNotification
from django.core.exceptions import ValidationError

class CheckoutForm(forms.ModelForm):
    """Form for checkout process"""
    save_shipping_address = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Save this shipping address for future orders"
    )
    
    payment_method = forms.ChoiceField(
        choices=Order.PAYMENT_METHOD_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        initial='momo'
    )
    
    momo_number = forms.CharField(
        required=False,
        max_length=15,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '078xxxxxxx or 072xxxxxxx'
        }),
        label="Your Mobile Money Number",
        help_text="Enter your 9-digit Mobile Money number"
    )
    
    customer_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Special instructions for your order...'
        })
    )
    
    class Meta:
        model = Order
        fields = ['shipping_address', 'shipping_city', 'shipping_phone', 'shipping_notes']
        widgets = {
            'shipping_address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter your complete shipping address'
            }),
            'shipping_city': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'City/Town'
            }),
            'shipping_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '078xxxxxxx or 072xxxxxxx'
            }),
            'shipping_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Delivery instructions (optional)'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.customer = kwargs.pop('customer', None)
        super().__init__(*args, **kwargs)
        
        # Pre-fill with customer's default shipping address if available
        if self.customer and hasattr(self.customer, 'customerprofile'):
            try:
                profile = self.customer.customerprofile
                
                # Check if profile has shipping_address field
                if hasattr(profile, 'shipping_address'):
                    self.fields['shipping_address'].initial = profile.shipping_address
                
                # Check if profile has any city-related field
                # Try different possible field names
                if hasattr(profile, 'city'):
                    self.fields['shipping_city'].initial = profile.city
                elif hasattr(profile, 'town'):
                    self.fields['shipping_city'].initial = profile.town
                elif hasattr(profile, 'location'):
                    self.fields['shipping_city'].initial = profile.location
                
                # Format phone to local format if it's in +250 format
                if self.customer.phone:
                    phone = self.customer.phone
                    if phone.startswith('+250'):
                        phone = '0' + phone[4:]  # Convert +25078xxxxxxx to 078xxxxxxx
                    self.fields['shipping_phone'].initial = phone
            except AttributeError:
                # If any attribute doesn't exist, just skip it
                pass

    def clean_shipping_phone(self):
        phone = self.cleaned_data.get('shipping_phone')
        if phone:
            # Clean the phone number - remove spaces, dashes
            phone = phone.strip().replace(' ', '').replace('-', '')
            
            if phone.startswith('0'):
                if not phone.startswith(('078', '072')):
                    raise forms.ValidationError("Phone number must start with 078 or 072")
                if len(phone) != 10:
                    raise forms.ValidationError("Phone number must be 10 digits (including the leading 0)")
                # Remove 0, add +250
                return f'+250{phone[1:]}'
            elif phone.startswith('+250'):
                if len(phone) != 13:  # +250 plus 9 digits
                    raise forms.ValidationError("Invalid phone number format")
                return phone
            else:
                raise forms.ValidationError("Phone number must start with 078, 072, or +250")
        return phone

    def clean_momo_number(self):
        momo = self.cleaned_data.get('momo_number')
        payment_method = self.cleaned_data.get('payment_method')
        
        if payment_method == 'momo' and momo:
            # Clean the momo number - remove spaces, dashes
            momo = momo.strip().replace(' ', '').replace('-', '')
            
            if momo.startswith('0'):
                if not momo.startswith(('078', '072')):
                    raise forms.ValidationError("Mobile Money number must start with 078 or 072")
                if len(momo) != 10:
                    raise forms.ValidationError("Mobile Money number must be 10 digits (including the leading 0)")
                # Remove 0, add +250
                return f'+250{momo[1:]}'
            elif momo.startswith('+250'):
                if len(momo) != 13:  # +250 plus 9 digits
                    raise forms.ValidationError("Invalid Mobile Money number format")
                return momo
            else:
                raise forms.ValidationError("Mobile Money number must start with 078, 072, or +250")
        
        return momo
        
    def clean(self):
        cleaned_data = super().clean()
        payment_method = cleaned_data.get('payment_method')
        momo_number = cleaned_data.get('momo_number')
        
        # Validate payment method specific requirements
        if payment_method == 'momo' and not momo_number:
            self.add_error('momo_number', 'Mobile Money number is required for Mobile Money payments.')
        
        return cleaned_data
    
class CartItemForm(forms.ModelForm):
    """Form for updating cart item quantity"""
    class Meta:
        model = CartItem
        fields = ['quantity']
        widgets = {
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'style': 'width: 80px;'
            })
        }
    
    def __init__(self, *args, **kwargs):
        self.product = kwargs.pop('product', None)
        super().__init__(*args, **kwargs)
        
        if self.product and self.product.is_track_inventory:
            max_quantity = self.product.get_available_quantity()
            if max_quantity > 0:
                self.fields['quantity'].widget.attrs['max'] = max_quantity
    
    def clean_quantity(self):
        quantity = self.cleaned_data['quantity']
        
        if self.product and self.product.is_track_inventory:
            available = self.product.get_available_quantity()
            if quantity > available:
                raise forms.ValidationError(
                    f"Only {available} items available in stock."
                )
        
        return quantity

class OrderStatusUpdateForm(forms.ModelForm):
    """Form for vendors to update order status"""
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Add notes about this status update (optional)'
        })
    )
    
    class Meta:
        model = Order
        fields = ['status']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'})
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Limit status choices based on current status
        current_status = self.instance.status if self.instance else 'pending'
        
        if current_status == 'pending':
            self.fields['status'].choices = [
                ('confirmed', 'Confirmed'),
                ('processing', 'Processing'),
                ('cancelled', 'Cancelled'),
            ]
        elif current_status == 'confirmed':
            self.fields['status'].choices = [
                ('processing', 'Processing'),
                ('shipped', 'Shipped'),
                ('cancelled', 'Cancelled'),
            ]
        elif current_status == 'processing':
            self.fields['status'].choices = [
                ('shipped', 'Shipped'),
                ('cancelled', 'Cancelled'),
            ]
        elif current_status == 'shipped':
            self.fields['status'].choices = [
                ('delivered', 'Delivered'),
            ]
        elif current_status == 'delivered':
            self.fields['status'].choices = []
        elif current_status == 'cancelled':
            self.fields['status'].choices = []

class OrderDeletionRequestForm(forms.Form):
    """Form for customers to request order deletion"""
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Please explain why you want to delete this order...'
        }),
        label="Reason for deletion request"
    )
    
    def clean_reason(self):
        reason = self.cleaned_data.get('reason')
        if len(reason.strip()) < 10:
            raise forms.ValidationError("Please provide a detailed reason (at least 10 characters).")
        return reason

class OrderPaymentForm(forms.Form):
    """Form for payment confirmation"""
    momo_number = forms.CharField(
        max_length=15,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'MTN Momo number used for payment'
        }),
        label="MTN Momo Number Used"
    )
    
    transaction_id = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Transaction ID from Momo (optional)'
        }),
        label="Transaction ID (Optional)"
    )
    
    def clean_momo_number(self):
        momo_number = self.cleaned_data.get('momo_number')
        if not momo_number.startswith(('67', '68', '69', '65', '66')):
            raise forms.ValidationError("Please enter a valid MTN Momo number.")
        return momo_number

class OrderFilterForm(forms.Form):
    """Form for filtering orders in dashboard"""
    STATUS_CHOICES = [
        ('', 'All Status'),
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('', 'All Payment Status'),
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    payment_status = forms.ChoiceField(
        choices=PAYMENT_STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by order number or customer...'
        })
    )

class VendorOrderFilterForm(OrderFilterForm):
    """Vendor-specific order filter form"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add product filter for vendors
        self.fields['product'] = forms.CharField(
            required=False,
            widget=forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Filter by product name...'
            })
        )

class BulkOrderUpdateForm(forms.Form):
    """Form for bulk order updates (for vendors)"""
    ACTION_CHOICES = [
        ('confirm', 'Confirm Selected'),
        ('process', 'Mark as Processing'),
        ('ship', 'Mark as Shipped'),
        ('cancel', 'Cancel Selected'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    order_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Notes for this bulk update (optional)'
        })
    )