from decimal import Decimal
from rest_framework import serializers
from .models import Payment, WalletTransaction, UserWallet
from rest_framework.exceptions import ValidationError

class InitiatePaymentSerializer(serializers.Serializer):
    appointment_id = serializers.UUIDField()
    Payment_method = serializers.ChoiceField(choices=['card', 'paypal', 
                    'wallet', 'insurance'])
    paypal_email = serializers.EmailField(required = False, allow_blank = True)
    insurance_provider = serializers.CharField(max_length = 255, required = False, allow_blank = True)
   
    insurance_number = serializers.CharField(max_length = 255, required = False, allow_blank = True)
     
    def validate(self, data):
        payment_method = data.get('payment_method')
        if payment_method == 'card':
            pass 
        elif payment_method == 'paypal':
            if not data.get('paypal_email'):
                raise ValidationError({'paypal_email': "paypal email is required "})
        
        elif payment_method == 'insurance':
            if not data.get('insurance_provider') or not data.get("insurance_number"):
                raise ValidationError("Insurance provider and number is required ")
            
        return data

class PaymentSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source = 'patient.full_name', read_only = True)
    appointment_id = serializers.CharField(source = 'appointment.id', read_only = True)
    
    class Meta:
        model = Payment
        fields = [
            'id',
            'appointment_id',
            'patient_name', 
            'amount', 
           # 'payment_method', 
            'status',
            'transaction_id', 
            'card_last_four',
            'card_brand',
            'refund_amount',
            'refund_reason',
            'refunded_at',
            'created_at',
            'completed_at',
            'meta_data'
        ]
        
        read_onlhy =[
            
            'id', 
            'status',
            'transaction_id', 
            'card_last_four',
            'card_brand',
            'refund_amount',
            'refund_reason',
            'refunded_at',
            'created_at',
            'completed_at',
        ]
        
    def to_representation(self, instance):
        data =  super().to_representation(instance)
        nullable_string_fields = [
            'appointment_id', 
            'transaction_id', 
            'card_four', 
            'card_brand', 
            'refund_reason'
        ]     
        
        for field in nullable_string_fields:
            if field in data and data[field] == '':
                data[field] = None
                
            return data

class CompletePaymentResponseSerializer(serializers.Serializer):
    Payment = PaymentSerializer()
    client_secret = serializers.CharField(required = False, allow_null = True)

    message = serializers.CharField(required = False)
    status = serializers.CharField(required = False)


class PaymentSummarySerializer(serializers.Serializer):
        
    appointment_id = serializers.UUIDField()
    consultant_name = serializers.CharField()
    scheduled_date = serializers.DateField()
    scheduled_time = serializers.CharField()
    consultation_fee = serializers.DecimalField(max_digits=10, 
                            decimal_places=2)
    payment_method = serializers.CharField(required = False, 
                            allow_null = True)
    wallet_balance = serializers.DecimalField(max_digits= 10, 
                            decimal_places= 2, required = False)
        
class WalletTransactionSeriaizer(serializers.ModelSerializer):
    user_name = serializers.CharField(source = 'wallet.user.full_name', 
                read_only = True)
    
    class Meta:
        model = WalletTransaction
        fields = [
            'id',
            'user_name',
            'transaction_type',
            'amount',
            'balance_after',
            'description',
            'reference',
            'created_at',        
            
        ]
        read_only_fields =[
            "id",
            "balance_after",
            "created_at",
        ]
    
class UserWalletSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source = "wallet.user.full_name", read_only = True)
    recent_transactions = WalletTransactionSeriaizer(source = 'transactions', many = True, read_only = True)
    
    class Meta:
        model = UserWallet
        fields = ['user_name', 'balance', 'created_at', 
                  'updated_at', 'recent_transactions']
        
        read_only_fields = ['balance', 'created_at', 'updated_at']
        
class AddFundsSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=10,decimal_places=2,
        min_value=Decimal('1.00'), max_value=Decimal('20000.00')
    )
    
    payment_method = serializers.ChoiceField(choices=['card', 'paypal'])
    
    def validate(self, data):
        if data['payment_method'] == 'paypal':
            if not data.get('paypal_email'):
                raise ValidationError({"paypal_email":"Paypal email id required"})
        
        return data


class AddWalletFundsResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    wallet = UserWalletSerializer()
    client_secret = serializers.CharField(required = False, allow_null = True)
    payment_intent_id = serializers.CharField(required = False, allow_null = True)
    status = serializers.CharField(required = True, allow_null = True)
    transaction_id = serializers.CharField(required = False, allow_null = True)
    
class RefundPaymentSerializer(serializers.Serializer):
    payment = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required = False)
    reason = serializers.CharField(max_length = 500)
    
    
        
        
      
                