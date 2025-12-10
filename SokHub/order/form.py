# orders/forms.py
from django import forms
from django.core.validators import MinValueValidator
from .models import Order, CartItem, OrderNotification

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
            'placeholder': '0788123456'
        }),
        label="Your MTN Momo Number"
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
                'placeholder': 'Phone number for delivery'
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
            profile = self.customer.customerprofile
            self.fields['shipping_address'].initial = profile.shipping_address
            self.fields['shipping_phone'].initial = self.customer.phone
    
    def clean_momo_number(self):
        momo_number = self.cleaned_data.get('momo_number')
        payment_method = self.cleaned_data.get('payment_method')
        
        if payment_method == 'momo' and not momo_number:
            raise forms.ValidationError("MTN Momo number is required for Momo payments.")
        
        if momo_number and not momo_number.startswith(('67', '68', '69', '65', '66')):
            raise forms.ValidationError("Please enter a valid MTN Momo number.")
        
        return momo_number
    
    def clean(self):
        cleaned_data = super().clean()
        payment_method = cleaned_data.get('payment_method')
        momo_number = cleaned_data.get('momo_number')
        
        # Validate payment method specific requirements
        if payment_method == 'momo' and not momo_number:
            self.add_error('momo_number', 'MTN Momo number is required for Momo payments.')
        
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