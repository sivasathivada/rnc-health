from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .import  views

urlpatterns = [

    # AUTHENTICATION ENDPOINTS
    path('register/', views.register, name = 'register'),
    path('login/', views.login, name ='login'),
    path('logout/', views.logout, name = 'logout'),

     # Token management
    path('token/refresh/', TokenRefreshView.as_view(), name = 'token_refresh'),
    path('token/refresh/custom/', views.token_refresh_custom, name = 'token_refresh_token'),
    path('validate/', views.validate_token, name = 'validated_token'),

    #User Profile
    path('profile/', views.user_profile, name = 'user_profile'),

    #Email verification endpoints
    path('verify-email-page/<str:token>/', views.verify_email_page, name = "verify_email_page"),
    path('verify-email/<str:token>/', views.verify_email, name = "verify_email"),
    path('verify-email-details/<str:token>/', views.verify_email_details, name = "verify_email_details"),
    path(
        "resend_verification/",
        views.resend_verification_email,
        name = "resend_verification_email"
    ),
    path("send-verification/",
         views.send_verification_email_authenticated,
         name='send_verification_email_authenticated'
         ),




]