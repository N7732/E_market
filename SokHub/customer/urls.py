# customer/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Authentication
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    
    # Password Reset
    path('password-reset/', 
         views.CustomPasswordResetView.as_view(), 
         name='password_reset'),
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name='customer/password_reset_done.html'
         ), 
         name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', 
         views.CustomPasswordResetConfirmView.as_view(), 
         name='password_reset_confirm'),
    path('password-reset-complete/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name='customer/password_reset_complete.html'
         ), 
         name='password_reset_complete'),
    
    # Password Change
    path('password-change/', 
         views.CustomPasswordChangeView.as_view(), 
         name='password_change'),
    path('password-change/done/', 
         views.CustomPasswordChangeDoneView.as_view(), 
         name='password_change_done'),
    
    # Profile Management
    path('profile/', views.profile_view, name='profile'),
    path('profile/vendor/', views.vendor_profile, name='vendor_profile'),
    path('profile/customer/', views.customer_profile, name='customer_profile'),
    path('settings/', views.account_settings, name='account_settings'),
    
    # Vendor Approval
    path('vendor/pending/', views.vendor_pending, name='vendor_pending'),
    
    # Static Pages
    path('home/', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),

    # Dashboards
    path("customer_dashboard/", views.customer_dashboard, name="customer_dashboard"),
    path("vendor_dashboard/", views.vendor_dashboard, name="vendor_dashboard"),
]