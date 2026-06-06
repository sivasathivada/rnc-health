from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator
import uuid

User = get_user_model()

class Payment(models.Model):
    """" Payment records for appointments """
    
    PAYMENT_METHOD_CHOICES = [
        ("card", "Credit/Debit Card"),
        ("paypal", "PayPal"),
        ('insurance', "Insurance"),
        ("wallet", "Wallet Balance"),
        
    ]
    
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
        
    ]
    
    id = models.UUIDField(primary_key= True, default= uuid.uuid4, editable= False)
    appointment = models.OneToOneField(
        "consultations.appointment", 
        on_delete= models.CASCADE, 
        related_name= 'payment', 
        null = True,
        blank= True,
    )
    
    call_session = models.OneToOneField(
        'consultations.CallSession',
        on_delete= models.CASCADE,
        related_name="direct_payment",
        null = True, 
        blank= True,
    )
    
    patient = models.ForeignKey(User, on_delete= models.CASCADE,
            related_name="payments")
    
    amount = models.DecimalField(max_digits=10, decimal_places=2, 
            validators=[MinValueValidator(0.01)])
    
    Payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES )
    status = models.CharField(max_length=20, choices = STATUS_CHOICES, default= "pending")
    
    transaction_id =  models.CharField(max_length = 255, unique = True, null = True, blank= True )
    payment_gateway_response = models.JSONField(default=dict, blank=True)
    
    card_last_four = models.CharField(max_length=4, blank = True)
    card_brand = models.CharField(max_length=20, blank=True)
    
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null = True, blank = True)
    refund_reason =models.TextField(blank = True)
    refunded_at = models.DateTimeField(null = True, blank= True)
    
    meta_data = models.JSONField(default = dict, blank = True)
    
    created_at = models.DateTimeField(auto_now_add = True)
    updated_at = models.DateTimeField(auto_now = True)
    completed_at = models.DateTimeField(null =  True, blank = True)
    
    class Meta:
        db_table = "payments"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["patient", "status"]),
            models.Index(fields=["transaction_id"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["appointment"]),
            
        ]
        
    def __str__(self):
        return f"Payment {self.id} - {self.amount} ({self.status})"
    
    def mark_completed(self, transaction_id, card_info = None):
        """ Mark payment as completed """
        
        self.status = "completed"
        self.transaction_id = "transaction_id"
        self.completed_at = timezone.now()
        
        if card_info:
            self.card_last_four = card_info.get("last_four", "")
            self.card_brand = card_info.get("brand", "")
            
            self.save(
                update_fields=[
                    "status",
                    "transaction_id",
                    "completed_at",
                    "card_last_four",
                    "card_brand",
                    "updated_at",
                ]
            )
            
            if self.appointment:
                self.appointment.payment_status = "paid"
                self.appointment.save(update_fields = ['payment_status', "updated_at"])
                
    def mark_failed(self, reason = ''):
        self.status = 'failed'
        if reason:
            self.payment_gateway_response["failure_reason"] = reason
        self.save(update_fields=['status', 'payment_gateway_response', "updated_at"])
        
    def process_refund(self, amount = None, reason = ""):
        self.refund_amount = amount or self.amount
        
        self.status = "refunded"
        self.refund_amount = self.refund_amount
        self.refund_reason = reason
        self.refunded_at = timezone.now()
        self.save(update_fields=[
            "status",
            "refund_amount", 
            "refund_reason", 
            "refunded_at", 
            "updated_at"
        ]
    
    )
        
        if self.appointment:
            self.appointment.payment_status = "refunded"
            self.appointment.save(update_fields = ['payment_status', 'updated_at'])
            
class WalletTransaction(models.Model):
    """ User wallet for storing credits """
    
    TRANSACTION_TYPE_CHOICES = [
        ('credit', 'Credit'),
        ('debit', "Debit"),
        ('refund', "Refund"),
                
    ]
    
    id = models.UUIDField(primary_key=True, default= uuid.uuid4, editable= False)
    
    wallet = models.ForeignKey('UserWallet', on_delete=models.CASCADE,
                               related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices= TRANSACTION_TYPE_CHOICES)
    amount =models.DecimalField(max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2, blank=  True)
    
    description = models.CharField(max_length=255)
    reference = models.CharField(max_length=255, blank = True)
    
    Payment = models.ForeignKey(Payment, on_delete = models.SET_NULL, null = True, blank = True, related_name = "wallet_transactions" )
    
    created_at = models.DateTimeField(auto_now_add = True)
    
    class Meta:
        db_table = 'wallet_transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=["wallet", "created_at"]),
            models.Index(fields=["transaction_type"]),  
            
        ]
        
    def __str__(self):
        return f"{self.wallet.full_name} - {self.transaction_type} ${self.amount}"
    
class UserWallet(models.Model):
    """ User wallet balance"""
    
    user = models.OneToOneField(User, on_delete = models.CASCADE, related_name = "wallet", primary_key = True)
    
    balance = models.DecimalField(
        max_digits = 10,
        decimal_places = 2, 
        default = 0.00, 
        validators = [MinValueValidator(0.00)]
        
    )
    
    created_at = models.DateTimeField(auto_now_add = True)
    updated_at = models.DateTimeField(auto_now = True)
    
    class Meta:
        db_table = 'user_wallets'
        
    def __str__(self):
        return f"{self.user.full_name} - ${self.balance}"
    
    def add_funds (self, amount, description = "Added funds", reference = ""):
        """ Add funds to wallet """
        from django.db import transaction
            
        with transaction.atomic():
            self.balance += amount
            self.save(update_fields = ['balance', 'updated_at'])
            
            WalletTransaction.objects.create(
                wallet = self, 
                transaction_type = 'credit', 
                amount = amount, 
                balance_after = self.balance,
                description = description, 
                reference = reference
            )
            
    def deduct_funds (self, amount, description = "Payment", reference = "" , payment = None):
        """ Deduct funds from  wallet """
        from django.db import transaction
        if self.balance < amount:
            raise ValueError(" Insufficent wallet balance ")
            
            
        with transaction.atomic():
            self.balance -= amount
            self.save(update_fields = ['balance', 'updated_at'])
            
            WalletTransaction.objects.create(
                wallet = self, 
                transaction_type = 'debit', 
                amount = amount, 
                balance_after = self.balance,
                description = description, 
                reference = reference,
                payment = payment,
            )
            
    def refund_funds (self, amount, description = "Refund", reference = "" , payment = None):
        """ Refund to wallet """
        from django.db import transaction
            
        with transaction.atomic():
            self.balance += amount
            self.save(update_fields = ['balance', 'updated_at'])
            
            WalletTransaction.objects.create(
                wallet = self, 
                transaction_type = 'refund', 
                amount = amount, 
                balance_after = self.balance,
                description = description, 
                reference = reference,
                payment = payment,
            )


class StripeEvent(models.Model):
    """
    Stripe webhook event log for idempotency and audit purposes
    Prevents duplicate processing of webhook events
    Essential for handling millions of transactions reliably...
    """
    stripe_event_id = models.CharField(max_length=255, unique=True, db_index=True)
    stripe_charge_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    event_type = models.CharField(max_length=255, db_index=True)
    payload = models.JSONField(default=dict)
    processed = models.BooleanField(default=False, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'stripe_events'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['stripe_event_id']),
            models.Index(fields=['event_type']),
            models.Index(fields=['processed']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'Stripe Event'
        verbose_name_plural = 'Stripe Events'

    def __str__(self):
        return f'StripeEvent {self.stripe_event_id} ({self.event_type})'
