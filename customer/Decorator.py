# customer/decorators.py (enhanced version)
from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps

def vendor_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please login to access this page.')
            return redirect('login')
        
        if not hasattr(request.user, 'user_type'):
            messages.error(request, 'Invalid user account.')
            return redirect('home')
        
        if request.user.user_type != 'vendor':
            messages.error(request, 'Access denied. Vendor account required.')
            return redirect('home')
        
        # NEW: Check if vendor is approved by admin
        if hasattr(request.user, 'vendorprofile'):
            if not request.user.vendorprofile.is_approved:
                messages.warning(request, 'Your vendor account is pending admin approval.')
                return redirect('vendor_pending')
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def customer_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please login to access this page.')
            return redirect('login')
        
        if not hasattr(request.user, 'user_type'):
            messages.error(request, 'Invalid user account.')
            return redirect('home')
        
        if request.user.user_type != 'customer':
            messages.error(request, 'Access denied. Customer account required.')
            return redirect('home')
            
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def admin_required(view_func):
    """New decorator for admin approval dashboard"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please login to access this page.')
            return redirect('login')
        
        if not request.user.is_staff:
            messages.error(request, 'Access denied. Admin privileges required.')
            return redirect('home')
            
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def vendor_approved_required(view_func):
    """Stricter decorator for vendors who need approval"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please login to access this page.')
            return redirect('login')
        
        if not hasattr(request.user, 'user_type') or request.user.user_type != 'vendor':
            messages.error(request, 'Vendor account required.')
            return redirect('home')
        
        # Check vendor profile exists and is approved
        if not hasattr(request.user, 'vendorprofile'):
            messages.error(request, 'Vendor profile not found.')
            return redirect('vendor_setup')
        
        if not request.user.vendorprofile.is_approved:
            messages.warning(request, 'Your vendor account is pending admin approval.')
            return redirect('vendor_pending')
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view