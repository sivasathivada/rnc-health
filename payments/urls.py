"""
Payment application URLs configuration.
All payment endpoints with proper authentication and CSRF protection.
Webhook endpoint is exempt from CSRF (Stripe cannot send CSRF tokens).
"""
from django.urls import path
from .import views
from .import webhooks

app_name = 'payments'

urlpatterns = [
    # Payment endpoints
    path('initiate/', views.initiate_payment_view, name='initiate_payment'),
    path('confirm/', views.confirm_payment_view, name='confirm_payment'),
    path('<uuid:payment_id>/status/', views.payment_status_view, name='payment_status'),
    path('history/', views.payment_history_view, name='payment_history'),
    path('refund/', views.refund_payment_view, name='refund_payment'),
    path('summary/<uuid:appointment_id>/', views.payment_summary_view, name='payment_summary'),
    
    # Wallet endpoints
    path('wallet/balance/', views.wallet_balance_view, name='wallet_balance'),
    path('wallet/add-funds/', views.add_wallet_funds_view, name='add_wallet_funds'),
    path('wallet/confirm-funds/', views.confirm_wallet_fund_view, name='confirm_wallet_funds'),
    path('wallet/transactions/', views.wallet_transactions_view, name='wallet_transactions'),
    
    # Stripe webhook
    path('stripe/webhook/', webhooks.stripe_webhook_handler, name='stripe_webhook'),
]
