# customer/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.forms import AuthenticationForm
from .models import User, VendorProfile, CustomerProfile

class UserRegistrationForm(UserCreationForm):
    USER_TYPE_CHOICES = (
        ('vendor', 'Vendor'),
        ('customer', 'Customer'),
    )
    
    user_type = forms.ChoiceField(
        choices=USER_TYPE_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Account Type"
    )
    phone = forms.CharField(
        max_length=15, 
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label="Phone Number"
    )
    location = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        label="Address/Location"
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    
    # Vendor-specific fields
    business_name = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control vendor-field'}),
        label="Business Name"
    )
    tax_id = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control vendor-field'}),
        label="Tax ID (Optional)"
    )
    momo_number = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control vendor-field'}),
        label="MTN Momo Number"
    )
    business_description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control vendor-field', 'rows': 3}),
        label="Business Description"
    )
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'user_type', 'phone', 'location']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        user_type = cleaned_data.get('user_type')
        
        # Validate vendor-specific fields
        if user_type == 'vendor':
            business_name = cleaned_data.get('business_name')
            momo_number = cleaned_data.get('momo_number')
            
            if not business_name:
                self.add_error('business_name', 'Business name is required for vendors.')
            
            if not momo_number:
                self.add_error('momo_number', 'Momo number is required for vendors.')
            
            # Validate Momo number format
            if momo_number and not momo_number.startswith(('67', '68', '69', '65', '66')):
                self.add_error('momo_number', 'Please enter a valid MTN Momo number (starts with 67, 68, 69, 65, or 66).')
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user_type = self.cleaned_data.get('user_type')
        
        if commit:
            user.save()
            
            if user_type == 'vendor':
                VendorProfile.objects.create(
                    user=user,
                    business_name=self.cleaned_data.get('business_name'),
                    business_address=self.cleaned_data.get('location'),
                    tax_id=self.cleaned_data.get('tax_id', ''),
                    default_momo_number=self.cleaned_data.get('momo_number'),
                    business_description=self.cleaned_data.get('business_description', ''),
                    is_approved=False
                )
            elif user_type == 'customer':
                CustomerProfile.objects.create(
                    user=user,
                    shipping_address=self.cleaned_data.get('location')
                )
        
        return user

class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username or Email'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'})
    )
    remember_me = forms.BooleanField(
        required=False, 
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Remember me"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        
        try:
            user = User.objects.get(username=username)
            if user.user_type == 'vendor' and hasattr(user, 'vendorprofile'):
                if not user.vendorprofile.is_approved:
                    raise forms.ValidationError(
                        'Your vendor account is pending admin approval. '
                        'You will be notified once approved.'
                    )
        except User.DoesNotExist:
            pass
        
        return cleaned_data

# ============ ADMIN FORMS ============

class AdminUserCreationForm(UserCreationForm):
    """Form for admin to create users"""
    class Meta:
        model = User
        fields = ('username', 'email', 'user_type', 'phone', 'location', 'is_staff', 'is_active')
        widgets = {
            'user_type': forms.Select(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class AdminUserChangeForm(UserChangeForm):
    """Form for admin to edit users"""
    class Meta:
        model = User
        fields = ('username', 'email', 'user_type', 'phone', 'location', 
                 'is_staff', 'is_active', 'is_superuser', 'groups', 'user_permissions')
        widgets = {
            'user_type': forms.Select(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class VendorApprovalForm(forms.ModelForm):
    """Admin form for approving vendors"""
    class Meta:
        model = VendorProfile
        fields = ['is_approved', 'admin_override_momo', 'is_active', 'rating']
        widgets = {
            'is_approved': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'admin_override_momo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Override vendor momo number'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'rating': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0', 'max': '5'}),
        }
        labels = {
            'admin_override_momo': 'Custom Momo Number',
            'is_approved': 'Approve Vendor',
            'is_active': 'Active Status',
        }
    
    def clean_admin_override_momo(self):
        momo_number = self.cleaned_data.get('admin_override_momo')
        if momo_number and not momo_number.startswith(('67', '68', '69', '65', '66')):
            raise forms.ValidationError('Please enter a valid MTN Momo number.')
        return momo_number

class BulkVendorApprovalForm(forms.Form):
    """Form for approving multiple vendors at once"""
    vendor_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
    action = forms.ChoiceField(
        choices=[('approve', 'Approve Selected'), ('reject', 'Reject Selected')],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        initial='approve'
    )
    send_email = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Send notification email to vendors"
    )

class AdminDashboardFilterForm(forms.Form):
    """Form for filtering in admin dashboard"""
    STATUS_CHOICES = [
        ('', 'All Status'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search vendors...'})
    )

class CustomerProfileForm(forms.ModelForm):
    """Form for customers to edit their profile"""
    class Meta:
        model = CustomerProfile
        fields = ['shipping_address', 'preferred_payment', 'default_momo_number', 
                 'receive_promotions', 'newsletter_subscription']
        widgets = {
            'shipping_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'preferred_payment': forms.Select(attrs={'class': 'form-control'}),
            'default_momo_number': forms.TextInput(attrs={'class': 'form-control'}),
            'receive_promotions': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'newsletter_subscription': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class VendorProfileForm(forms.ModelForm):
    """Form for vendors to edit their profile"""
    class Meta:
        model = VendorProfile
        fields = ['business_name', 'business_address', 'tax_id', 'default_momo_number',
                 'business_description', 'website', 'business_logo']
        widgets = {
            'business_name': forms.TextInput(attrs={'class': 'form-control'}),
            'business_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'tax_id': forms.TextInput(attrs={'class': 'form-control'}),
            'default_momo_number': forms.TextInput(attrs={'class': 'form-control'}),
            'business_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'website': forms.URLInput(attrs={'class': 'form-control'}),
            'business_logo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
    
    def clean_default_momo_number(self):
        momo_number = self.cleaned_data.get('default_momo_number')
        if momo_number and not momo_number.startswith(('67', '68', '69', '65', '66')):
            raise forms.ValidationError('Please enter a valid MTN Momo number.')
        return momo_number
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username or Email'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'})
    )
    remember_me = forms.BooleanField(
        required=False, 
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Remember me"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        
        # Check if user exists and is vendor (for redirect logic)
        try:
            user = User.objects.get(username=username)
            if user.user_type == 'vendor' and hasattr(user, 'vendorprofile'):
                if not user.vendorprofile.is_approved:
                    self.add_error(None, 'Your vendor account is pending admin approval.')
        except User.DoesNotExist:
            pass
        
        return cleaned_data