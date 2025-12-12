# products/forms.py
from django import forms
from django.core.validators import MinValueValidator
from django.utils.text import slugify
from .models import Product, ProductImage, ProductVariant, Category, ProductReview

class ProductForm(forms.ModelForm):
    """Form for vendors to add/edit products"""
    class Meta:
        model = Product
        fields = [
            'name', 'description', 'short_description', 'price', 
            'compare_at_price', 'category', 'tags', 'quantity',
            'low_stock_threshold', 'is_track_inventory', 'allow_backorder',
            'requires_shipping', 'main_image'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'short_description': forms.Textarea(attrs={'rows': 2}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'tags': forms.SelectMultiple(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.vendor = kwargs.pop('vendor', None)
        super().__init__(*args, **kwargs)
        
        # Set initial vendor if creating new product
        if self.instance.pk is None and self.vendor:
            self.instance.vendor = self.vendor
        
        # Limit categories to active ones
        self.fields['category'].queryset = Category.objects.filter(is_active=True)
        
        # Make price required
        self.fields['price'].required = True
        self.fields['price'].widget.attrs['min'] = '0.01'

         # This connects to database categories
        self.fields['category'].queryset = Category.objects.filter(is_active=True)
        self.fields['category'].empty_label = "--- Select Category ---"

        #
        
        # Add bootstrap classes
        for field in self.fields:
            if field not in ['is_track_inventory', 'allow_backorder', 'requires_shipping']:
                self.fields[field].widget.attrs['class'] = 'form-control'
    
    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price and price <= 0:
            raise forms.ValidationError('Price must be greater than 0.')
        return price
    
    def clean_compare_at_price(self):
        compare_price = self.cleaned_data.get('compare_at_price')
        price = self.cleaned_data.get('price')
        
        if compare_price and price and compare_price <= price:
            raise forms.ValidationError('Compare price must be greater than regular price.')
        return compare_price
    
    def save(self, commit=True):
        # Generate slug from name if not provided
        if not self.instance.slug:
            base_slug = slugify(self.instance.name)
            slug = base_slug
            counter = 1
            while Product.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.instance.slug = slug
        
        # Set status to pending review for new products
        if self.instance.pk is None:
            self.instance.status = 'pending_review'
        
        return super().save(commit)

class ProductImageForm(forms.ModelForm):
    """Form for product images"""
    class Meta:
        model = ProductImage
        fields = ['image', 'alt_text', 'display_order', 'is_main']
        widgets = {
            'alt_text': forms.TextInput(attrs={'class': 'form-control'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_main': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class ProductVariantForm(forms.ModelForm):
    """Form for product variants"""
    class Meta:
        model = ProductVariant
        fields = ['name', 'value', 'sku', 'price', 'quantity', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'value': forms.TextInput(attrs={'class': 'form-control'}),
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is not None and price <= 0:
            raise forms.ValidationError('Price must be greater than 0.')
        return price

class BulkProductUploadForm(forms.Form):
    """Form for bulk product upload via CSV"""
    csv_file = forms.FileField(
        label='CSV File',
        help_text='Upload a CSV file with product details'
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        help_text='Assign all products to this category'
    )
    
    def clean_csv_file(self):
        csv_file = self.cleaned_data.get('csv_file')
        if csv_file:
            if not csv_file.name.endswith('.csv'):
                raise forms.ValidationError('Only CSV files are allowed.')
        return csv_file

class ProductSearchForm(forms.Form):
    """Form for product search"""
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search products...',
            'aria-label': 'Search'
        })
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        empty_label='All Categories',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    min_price = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Min price',
            'step': '0.01'
        })
    )
    max_price = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Max price',
            'step': '0.01'
        })
    )
    in_stock = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    sort_by = forms.ChoiceField(
        required=False,
        choices=[
            ('newest', 'Newest'),
            ('price_low', 'Price: Low to High'),
            ('price_high', 'Price: High to Low'),
            ('popular', 'Most Popular'),
            ('rating', 'Highest Rated'),
        ],
        initial='newest',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

class ProductReviewForm(forms.ModelForm):
    """Form for customers to review products"""
    class Meta:
        model = ProductReview
        fields = ['rating', 'title', 'comment']
        widgets = {
            'rating': forms.RadioSelect(choices=ProductReview.RATING_CHOICES),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Review title'}),
            'comment': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 4,
                'placeholder': 'Share your experience with this product...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.product = kwargs.pop('product', None)
        self.customer = kwargs.pop('customer', None)
        super().__init__(*args, **kwargs)
        
        # Style the rating radio buttons
        self.fields['rating'].widget.attrs['class'] = 'form-check-input'
    
    def save(self, commit=True):
        review = super().save(commit=False)
        if self.product:
            review.product = self.product
        if self.customer:
            review.customer = self.customer
        
        # Mark as verified purchase if customer has bought the product
        # This would be checked against order history
        review.is_verified_purchase = False
        
        if commit:
            review.save()
        return review

class StockAdjustmentForm(forms.Form):
    """Form for adjusting product stock"""
    ADJUSTMENT_TYPES = (
        ('add', 'Add Stock'),
        ('remove', 'Remove Stock'),
        ('set', 'Set Stock'),
    )
    
    adjustment_type = forms.ChoiceField(
        choices=ADJUSTMENT_TYPES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
    )