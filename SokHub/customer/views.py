# customer/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    PasswordResetView, 
    PasswordResetDoneView, 
    PasswordResetConfirmView, 
    PasswordResetCompleteView,
    PasswordChangeView,
    PasswordChangeDoneView
)
from django.contrib import messages
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.urls import reverse_lazy, reverse
from django.http import HttpResponseRedirect
from django.db import transaction
from django.utils import timezone
import logging

from .form import UserRegistrationForm, LoginForm, VendorProfileForm, CustomerProfileForm
from .Decorator import vendor_required, customer_required, vendor_approved_required
from .models import User, VendorProfile, CustomerProfile

logger = logging.getLogger(__name__)

# ============ EMAIL UTILITY FUNCTIONS ============

def send_welcome_email(user, request):
    """Send welcome email after registration"""
    subject = 'Welcome to SokHub!'
    
    # Determine template based on user type
    if user.user_type == 'vendor':
        template_name = 'emails/welcome_vendor.html'
        context = {
            'user': user,
            'business_name': user.vendorprofile.business_name if hasattr(user, 'vendorprofile') else '',
            'approval_status': 'pending' if hasattr(user, 'vendorprofile') and not user.vendorprofile.is_approved else 'approved',
            'settings': settings
        }
    else:
        template_name = 'emails/welcome_customer.html'
        context = {
            'user': user,
            'settings': settings
        }
    
    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)
    
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email]
    )
    email.attach_alternative(html_content, "text/html")
    email.send()

def send_vendor_approval_email(vendor_user, request):
    """Send email when vendor is approved by admin"""
    subject = 'Your SokHub Vendor Account Has Been Approved!'
    template_name = 'emails/vendor_approved.html'
    
    context = {
        'vendor': vendor_user,
        'business_name': vendor_user.vendorprofile.business_name,
        'login_url': request.build_absolute_uri(reverse('login')),
        'settings': settings
    }
    
    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)
    
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[vendor_user.email]
    )
    email.attach_alternative(html_content, "text/html")
    email.send()

def send_password_reset_email(user, request, token, uid):
    """Custom password reset email with HTML"""
    subject = 'Reset Your SokHub Password'
    template_name = 'emails/password_reset.html'
    
    reset_url = request.build_absolute_uri(
        reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
    )
    
    context = {
        'user': user,
        'reset_url': reset_url,
        'expiry_hours': 24,
        'settings': settings
    }
    
    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)
    
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email]
    )
    email.attach_alternative(html_content, "text/html")
    email.send()

def send_security_notification_email(user, request, event_type):
    """Send security notification emails"""
    event_templates = {
        'password_reset_requested': 'Authentication/password_reset_requested.html',
        'password_changed': 'Authentication/password_changed.html',
        'new_device_login': 'Authentication/new_device_login.html',
    }
    
    if event_type in event_templates:
        subject = f'SokHub Security Notification: {event_type.replace("_", " ").title()}'
        template_name = event_templates[event_type]
        
        context = {
            'user': user,
            'event_type': event_type,
            'ip_address': request.META.get('REMOTE_ADDR', 'Unknown'),
            'user_agent': request.META.get('HTTP_USER_AGENT', 'Unknown'),
            'timestamp': timezone.now(),
            'settings': settings
        }
        
        html_content = render_to_string(template_name, context)
        text_content = strip_tags(html_content)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()

# ============ AUTHENTICATION VIEWS ============

def register(request):
    """Enhanced registration with email verification"""
    if request.user.is_authenticated:
        return redirect_user_by_role(request.user)
    
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
                    
                    # Send welcome email
                    send_welcome_email(user, request)
                    
                    # Auto-login after registration
                    login(request, user)
                    
                    # Different messages based on user type
                    if user.user_type == 'vendor':
                        messages.info(request, 
                            'Vendor account created successfully! '
                            'Please wait for admin approval. You will receive an email when approved.'
                        )
                        logger.info(f'New vendor registered: {user.username}')
                    else:
                        messages.success(request, 'Account created successfully! Welcome to SokHub!')
                    
                    return redirect_user_by_role(user)
                    
            except Exception as e:
                logger.error(f"Registration error: {str(e)}")
                messages.error(request, 'An error occurred during registration. Please try again.')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'Register&login/register.html', {'form': form})

def user_login(request):
    """Enhanced login view with email notifications"""
    if request.user.is_authenticated:
        return redirect_user_by_role(request.user)
    
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            
            # Log login activity
            logger.info(f"User {user.username} logged in from IP: {request.META.get('REMOTE_ADDR')}")
            
            # Send security notification for new device login
            # (In production, you'd check if this is a new device)
            send_security_notification_email(user, request, 'new_device_login')
            
            # Check if vendor needs approval
            if user.user_type == 'vendor' and hasattr(user, 'vendorprofile'):
                if not user.vendorprofile.is_approved:
                    messages.info(request, 
                        'Your vendor account is pending admin approval. '
                        'You will receive an email when approved.'
                    )
            
            return redirect_user_by_role(user)
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()
    
    return render(request, 'Register&login/login.html', {'form': form})

@login_required
def user_logout(request):
    """Logout view"""
    user = request.user
    logout(request)
    
    logger.info(f"User {user.username} logged out")
    messages.success(request, 'You have been logged out successfully.')
    return redirect('home')

# ============ PASSWORD MANAGEMENT ============

class CustomPasswordResetView(PasswordResetView):
    """Custom password reset view with HTML email"""
    template_name = 'Register&login/password_reset.html'
    email_template_name = 'Authentication/password_reset_email.html'  # Plain text
    html_email_template_name = 'emails/password_reset.html'  # HTML version
    success_url = reverse_lazy('password_reset_done')
    
    def form_valid(self, form):
        # Get the user's email
        email = form.cleaned_data['email']
        
        try:
            # Get the user
            user = User.objects.get(email=email)
            
            # Generate token and uid
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Send custom HTML email
            send_password_reset_email(user, self.request, token, uid)
            
            # Also send security notification
            send_security_notification_email(user, self.request, 'password_reset_requested')
            
            logger.info(f"Password reset requested for email: {email}")
            
        except User.DoesNotExist:
            # Still show success message (security: don't reveal if user exists)
            pass
        
        return super().form_valid(form)

class CustomPasswordResetDoneView(PasswordResetDoneView):
    """Custom password reset done view"""
    template_name = 'Register&login/password_reset_done.html'

class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    """Custom password reset confirmation"""
    template_name = 'Register&login/password_reset_confirm.html'
    success_url = reverse_lazy('password_reset_complete')
    
    def form_valid(self, form):
        user = form.save()
        
        # Send security notification
        send_security_notification_email(user, self.request, 'password_changed')
        
        logger.info(f"Password reset completed for user: {user.username}")
        messages.success(self.request, 'Your password has been reset successfully. Please login with your new password.')
        
        return super().form_valid(form)

class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    """Custom password reset complete view"""
    template_name = 'Register&login/password_reset_complete.html'

class CustomPasswordChangeView(PasswordChangeView):
    """Custom password change view"""
    template_name = 'Register&login/password_change.html'
    success_url = reverse_lazy('password_change_done')
    
    def form_valid(self, form):
        user = self.request.user
        
        # Send security notification
        send_security_notification_email(user, self.request, 'password_changed')
        
        logger.info(f"Password changed for user: {user.username}")
        messages.success(self.request, 'Your password has been changed successfully.')
        
        return super().form_valid(form)

class CustomPasswordChangeDoneView(PasswordChangeDoneView):
    """Custom password change done view"""
    template_name = 'Register&login/password_change_done.html'

# ============ PROFILE VIEWS ============

@login_required
def profile_view(request):
    """User profile view"""
    user = request.user
    
    if user.user_type == 'vendor':
        return vendor_profile(request)
    elif user.user_type == 'customer':
        return customer_profile(request)
    else:
        return redirect('home')

@login_required
@vendor_required
def vendor_profile(request):
    """Vendor profile management"""
    vendor_profile = get_object_or_404(VendorProfile, user=request.user)
    
    if request.method == 'POST':
        form = VendorProfileForm(request.POST, request.FILES, instance=vendor_profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('vendor_profile')
    else:
        form = VendorProfileForm(instance=vendor_profile)
    
    context = {
        'form': form,
        'vendor': vendor_profile,
        'is_approved': vendor_profile.is_approved,
        'approval_status': 'Approved' if vendor_profile.is_approved else 'Pending Approval'
    }
    
    return render(request, 'customer/vendor_profile.html', context)

@login_required
@customer_required
def customer_profile(request):
    """Customer profile management"""
    customer_profile = get_object_or_404(CustomerProfile, user=request.user)
    
    if request.method == 'POST':
        form = CustomerProfileForm(request.POST, instance=customer_profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('customer_profile')
    else:
        form = CustomerProfileForm(instance=customer_profile)
    
    context = {
        'form': form,
        'customer': customer_profile
    }
    
    return render(request, 'customer/customer_profile.html', context)

@login_required
def account_settings(request):
    """Account settings page"""
    user = request.user
    
    if request.method == 'POST':
        # Handle email preferences update
        if user.user_type == 'customer' and hasattr(user, 'customerprofile'):
            user.customerprofile.receive_promotions = request.POST.get('receive_promotions') == 'on'
            user.customerprofile.newsletter_subscription = request.POST.get('newsletter_subscription') == 'on'
            user.customerprofile.save()
            messages.success(request, 'Preferences updated successfully!')
    
    context = {
        'user': user,
        'is_vendor': user.user_type == 'vendor',
        'is_customer': user.user_type == 'customer',
    }
    
    return render(request, 'customer/account_settings.html', context)

# ============ UTILITY FUNCTIONS ============

def redirect_user_by_role(user):
    """Redirect user to appropriate dashboard based on role"""
    if user.user_type == 'vendor':
        if hasattr(user, 'vendorprofile') and user.vendorprofile.is_approved:
            return redirect('vendor_dashboard')
        else:
            return redirect('vendor_pending')
    elif user.user_type == 'customer':
        return redirect('customer_dashboard')
    elif user.is_staff:
        return redirect('/admin/')
    else:
        return redirect('home')

# ============ VENDOR APPROVAL STATUS VIEW ============

@login_required
@vendor_required
def vendor_pending(request):
    """View for vendors waiting for approval"""
    vendor_profile = get_object_or_404(VendorProfile, user=request.user)
    
    context = {
        'vendor': vendor_profile,
        'is_approved': vendor_profile.is_approved,
        'business_name': vendor_profile.business_name,
        'applied_date': vendor_profile.created_at
    }
    
    return render(request, 'consumer/vendor_pending.html', context)

# ============ HOME & LANDING PAGES ============

def home(request):
    """Home page with role-based redirect for logged in users"""
    if request.user.is_authenticated:
        return redirect_user_by_role(request.user)
    
    return render(request, 'consumer/home.html')

def about(request):
    """About page"""
    return render(request, 'consumer/about.html')

def contact(request):
    """Contact page"""
    return render(request, 'consumer/contact.html')

# ============ DASHBOARD VIEWS ============

@login_required
@customer_required
def customer_dashboard(request):
    """Customer dashboard with black/magenta theme"""
    user = request.user
    # Get customer's orders (will be implemented in orders app)
    # orders = Order.objects.filter(customer=user).order_by('-created_at')[:5]
    
    context = {
        'user': user,
        'customer_profile': user.customerprofile,
        # 'recent_orders': orders,
        'theme': {
            'primary': '#000000',
            'accent': '#FF00FF',
            'background': '#0a0a0a',
            'text': '#ffffff'
        }
    }
    
    return render(request, 'consumer/dashboard.html', context)

@login_required
@vendor_approved_required
def vendor_dashboard(request):
    """Vendor dashboard with green/red theme"""
    vendor_profile = get_object_or_404(VendorProfile, user=request.user)
    
    # Get vendor stats (will be implemented with orders)
    # total_orders = Order.objects.filter(vendor=request.user).count()
    # pending_orders = Order.objects.filter(vendor=request.user, status='pending').count()
    # completed_orders = Order.objects.filter(vendor=request.user, status='completed').count()
    
    context = {
        'vendor': vendor_profile,
        'is_approved': vendor_profile.is_approved,
        # 'total_orders': total_orders,
        # 'pending_orders': pending_orders,
        # 'completed_orders': completed_orders,
        'theme': {
            'success': '#00FF00',  # Green
            'warning': '#FFA500',  # Orange
            'danger': '#FF0000',   # Red
            'info': '#006400',     # Dark Green
            'background': '#f0f8f0',  # Light green background
            'text': '#1a1a1a'
        }
    }
    
    return render(request, 'vendor/dashboard.html', context)