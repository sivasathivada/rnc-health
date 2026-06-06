

from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum, Count, Q
from django.utils import timezone
from decimal import Decimal

from .models import Payment, UserWallet, WalletTransaction, StripeEvent


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """
    Admin interface for Payment management with comprehensive filtering and actions.
    Optimized for handling millions of payments with proper indexing awareness.
    """
    list_display = (
        'id',
        'patient_name',
        'appointment_id',
        'amount_display',
        'Payment_method',
        'status_badge',
        'transaction_id',
        'created_at',
    )
    list_filter = (
        'status',
        'Payment_method',
        'created_at',
        ('completed_at', admin.EmptyFieldListFilter),
    )
    search_fields = (
        'id',
        'transaction_id',
        'patient__email',
        'patient__first_name',
        'patient__last_name',
    )
    readonly_fields = (
        'id',
        'patient',
        'transaction_id',
        'payment_gateway_response',
        'created_at',
        'updated_at',
        'completed_at',
    )               
    fieldsets = (
        ('Payment Information', {
            'fields': ('id', 'patient', 'appointment', 'call_session', 'amount')  # , 'currency'
        }),
        ('Payment Method & Status', {
            'fields': ('Payment_method', 'status', 'transaction_id')
        }),
        ('Card Details', {
            'fields': ('card_last_four', 'card_brand'),
            'classes': ('collapse',),
        }),
        ('Refund Information', {
            'fields': ('refund_amount', 'refund_reason', 'refunded_at'),
            'classes': ('collapse',),
        }),
        ('Gateway Response', {
            'fields': ('payment_gateway_response',),
            'classes': ('collapse',),
        }),
        ('Metadata', {
            'fields': ('meta_data',),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'completed_at'),
            'classes': ('collapse',),
        }),
    )
    actions = ['mark_completed', 'mark_failed', 'export_transactions']
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    
    def patient_name(self, obj):
        return obj.patient.full_name or obj.patient.email
    patient_name.short_description = 'Patient'
    
    def amount_display(self, obj):
        return f"${obj.amount:,.2f}"
    amount_display.short_description = 'Amount'
    
    def status_badge(self, obj):
        """Display status with color-coded badges."""
        color_map = {
            'pending': '#FFC107',
            'processing': '#17A2B8',
            'completed': '#28A745',
            'failed': '#DC3545',
            'refunded': '#6F42C1',
        }
        color = color_map.get(obj.status, '#6C757D')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def mark_completed(self, request, queryset):
        """Mark selected payments as completed."""
        updated = queryset.filter(status='processing').update(
            status='completed',
            completed_at=timezone.now()
        )
        self.message_user(request, f'{updated} payments marked as completed.')
    mark_completed.short_description = 'Mark selected as Completed'
    
    def mark_failed(self, request, queryset):
        """Mark selected payments as failed."""
        updated = queryset.exclude(status='completed').update(status='failed')
        self.message_user(request, f'{updated} payments marked as failed.')
    mark_failed.short_description = 'Mark selected as Failed'
    
    def export_transactions(self, request, queryset):
        """Export selected payments as CSV (placeholder)."""
        self.message_user(request, 'Export feature to be implemented with django-import-export')
    export_transactions.short_description = 'Export selected payments to CSV'
    
    def get_queryset(self, request):
        """Optimize queryset with select_related for foreign keys."""
        qs = super().get_queryset(request)
        return qs.select_related('patient', 'appointment')


@admin.register(StripeEvent)
class StripeEventAdmin(admin.ModelAdmin):
    """
    Admin for Stripe webhook events.
    Useful for debugging and monitoring webhook delivery.
    """
    list_display = (
        'stripe_event_id',
        'event_type',
        'processed_badge',
        'created_at',
        'processed_at',
    )
    list_filter = (
        'event_type',
        'processed',
        'created_at',
    )
    search_fields = ('stripe_event_id', 'event_type')
    readonly_fields = ('stripe_event_id', 'stripe_charge_id','event_type', 'payload', 'created_at', 'processed_at')
    fieldsets = (
        ('Event Information', {
            'fields': ('stripe_event_id', 'event_type', 'processed')
        }),
        ('Payload', {
            'fields': ('payload',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'processed_at'),
        }),
    )
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    
    def processed_badge(self, obj):
        """Display processing status with badge."""
        if obj.processed:
            return format_html(
                '<span style="background-color: #28A745; color: white; padding: 3px 8px; border-radius: 3px;">Processed</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #FFC107; color: black; padding: 3px 8px; border-radius: 3px;">Pending</span>'
            )
    processed_badge.short_description = 'Status'
    
    def has_add_permission(self, request):
        """Prevent manual creation of webhook events."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of webhook events."""
        return False


@admin.register(UserWallet)
class UserWalletAdmin(admin.ModelAdmin):
    """
    Admin interface for user wallets with transaction summaries.
    """
    list_display = (
        'user_display',
        'balance_display',
        'transaction_count',
        'total_credited',
        'total_debited',
        'created_at',
    )
    search_fields = (
        'user__email',
        'user__first_name',
        'user__last_name',
    )
    readonly_fields = (
        'user',
        'created_at',
        'updated_at',
        'balance_display',
    )
    fieldsets = (
        ('Wallet Information', {
            'fields': ('user', 'balance')
        }),
        ('Statistics', {
            'fields': ('balance_display',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )
    ordering = ('-updated_at',)
    
    def user_display(self, obj):
        return obj.user.get_full_name() or obj.user.email
    user_display.short_description = 'User'
    
    def balance_display(self, obj):
        return format_html(
            '<span style="font-weight: bold; color: #28A745;">${:,.2f}</span>',
            obj.balance
        )
    balance_display.short_description = 'Current Balance'
    
    def transaction_count(self, obj):
        """Display total transaction count."""
        count = obj.transactions.count()
        return count
    transaction_count.short_description = 'Transactions'
    
    def total_credited(self, obj):
        """Display total credits."""
        total = obj.transactions.filter(transaction_type='credit').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        return f"${total:,.2f}"
    total_credited.short_description = 'Total Credits'
    
    def total_debited(self, obj):
        """Display total debits."""
        total = obj.transactions.filter(transaction_type='debit').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        return f"${total:,.2f}"
    total_debited.short_description = 'Total Debits'
    
    def has_add_permission(self, request):
        """Prevent manual wallet creation."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Prevent wallet deletion."""
        return False
    
    def get_queryset(self, request):
        """Optimize queryset."""
        qs = super().get_queryset(request)
        return qs.select_related('user').prefetch_related('transactions')


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    """
    Admin interface for wallet transactions with comprehensive filtering.
    """
    list_display = (
        'id',
        'user_display',
        'transaction_type_badge',
        'amount_display',
        'balance_after_display',
        'description',
        'created_at',
    )
    list_filter = (
        'transaction_type',
        'created_at',
        ('reference', admin.EmptyFieldListFilter),
    )
    search_fields = (
        'id',
        'wallet__user__email',
        'wallet__user__first_name',
        'wallet__user__last_name',
        'description',
        'reference',
    )
    readonly_fields = (
        'id',
        'wallet',
        'balance_after',
        'created_at',
    )
    fieldsets = (
        ('Transaction Information', {
            'fields': ('id', 'wallet', 'transaction_type', 'amount')
        }),
        ('Balance', {
            'fields': ('balance_after',),
        }),
        ('Description', {
            'fields': ('description', 'reference')
        }),
        ('Related Payment', {
            'fields': ('Payment',),
            'classes': ('collapse',),
        }),
        ('Timestamp', {
            'fields': ('created_at',),
        }),
    )
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    
    def user_display(self, obj):
        return obj.wallet.user.get_full_name() or obj.wallet.user.email
    user_display.short_description = 'User'
    
    def transaction_type_badge(self, obj):
        """Display transaction type with color-coded badge."""
        color_map = {
            'credit': '#28A745',
            'debit': '#DC3545',
            'refund': '#6F42C1',
        }
        color = color_map.get(obj.transaction_type, '#6C757D')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; text-transform: capitalize;">{}</span>',
            color,
            obj.transaction_type
        )
    transaction_type_badge.short_description = 'Type'
    
    def amount_display(self, obj):
        return f"${obj.amount:,.2f}"
    amount_display.short_description = 'Amount'
    
    def balance_after_display(self, obj):
        return f"${obj.balance_after:,.2f}"
    balance_after_display.short_description = 'Balance After'
    
    def has_add_permission(self, request):
        """Prevent manual transaction creation."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Prevent transaction deletion."""
        return False
    
    def get_queryset(self, request):
        """Optimize queryset."""
        qs = super().get_queryset(request)
        return qs.select_related('wallet__user', 'Payment')
