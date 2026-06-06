import logging
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Payment, UserWallet, WalletTransaction, StripeEvent
from .payment_gateway import StripeGateway

logger = logging.getLogger(__name__)


class PaymentService:
    """
    Core payment service handling all payment operations.
    Ensures atomicity, idempotency, and proper error handling.
    """
    gateway = StripeGateway()

    @classmethod
    def _validate_amount(cls, amount):
        """Validate amount is within configured limits."""
        try:
            amount = Decimal(str(amount))
        except:
            raise ValidationError('Invalid amount format.')
        
        if amount <= 0:
            raise ValidationError('Amount must be greater than zero.')
        
        min_amt = Decimal(str(settings.PAYMENT_MIN_AMOUNT))
        max_amt = Decimal(str(settings.PAYMENT_MAX_AMOUNT))
        
        if amount < min_amt or amount > max_amt:
            raise ValidationError(f'Amount must be between {min_amt} and {max_amt}.')
        
        return amount

    @classmethod
    def _check_daily_limits(cls, user):
        """Check if user has exceeded daily transaction limits."""
        today = timezone.localdate()
        
        # Check transaction count
        daily_txn_count = Payment.objects.filter(
            patient=user,
            created_at__date=today,
            status__in=['completed', 'processing']
        ).count()
        
        if daily_txn_count >= settings.PAYMENT_DAILY_LIMIT_TRANSACTIONS:
            raise ValidationError('Daily transaction limit exceeded.')
        
        # Check total amount
        daily_total = Payment.objects.filter(
            patient=user,
            created_at__date=today,
            status__in=['completed', 'processing']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        return daily_total

    @classmethod
    def initiate_payment(cls, user, appointment, amount, payment_method='card', **kwargs):
        """
        Initiate a payment for an appointment.
        Only handles CARD payment method for Stripe integration here.
        """
        amount = cls._validate_amount(amount)
        daily_total = cls._check_daily_limits(user)
        
        limit_amt = Decimal(str(settings.PAYMENT_LIMIT_AMOUNT))
        if daily_total + amount > limit_amt:
            raise ValidationError(f'Daily payment limit exceeded. Current: {daily_total}, Limit: {limit_amt}.')
        
        if payment_method not in ['card', 'paypal', 'wallet', 'insurance']:
            raise ValidationError('Invalid payment method.')
        
        # For CARD method, create Stripe PaymentIntent
        if payment_method == 'card':
            return cls._create_stripe_payment(user, appointment, amount, payment_method)
        
        # For WALLET method, deduct from user wallet
        elif payment_method == 'wallet':
            return cls._process_wallet_payment(user, appointment, amount, payment_method)
        
        else:
            raise ValidationError(f'Payment method {payment_method} not yet implemented for direct processing.')

    @classmethod
    def _create_stripe_payment(cls, user, appointment, amount, payment_method):
        """Create Stripe PaymentIntent and Payment record."""
        with transaction.atomic():
            # Check if a Payment record already exists for this appointment
            payment = Payment.objects.filter(appointment=appointment).first()
            if payment:
                if payment.status == 'completed':
                    raise ValidationError('Payment already completed for this appointment.')
                
                # Reuse and update the existing payment record
                payment.patient = user
                payment.amount = amount
                payment.Payment_method = payment_method
                payment.status = 'pending'
                # Reset transaction_id to avoid unique constraints if creation of Stripe PaymentIntent fails
                payment.transaction_id = None
                payment.save(update_fields=['patient', 'amount', 'Payment_method', 'status', 'transaction_id'])
            else:
                # Create local Payment record
                payment = Payment.objects.create(
                    patient=user,
                    appointment=appointment,
                    amount=amount,
                    Payment_method=payment_method,
                    status='pending',
                    meta_data={
                        'user_id': str(user.id),
                        'appointment_id': str(appointment.id),
                    },
                )
            
            try:
                # Create Stripe PaymentIntent
                amount_cents = int(amount * 100)
                intent = cls.gateway.create_payment_intent(
                    amount_cents=amount_cents,
                    currency='usd',
                    metadata={
                        'payment_id': str(payment.id),
                        'user_id': str(user.id),
                        'appointment_id': str(appointment.id),
                    },
                    description=f'Payment for appointment with Dr. {appointment.consultant.user.first_name}',
                )
                
                # Update payment record with Stripe details
                payment.transaction_id = intent.id  # Store PaymentIntent ID
                payment.payment_gateway_response = intent.to_dict()
                payment.status = 'processing'
                payment.save(update_fields=['transaction_id', 'payment_gateway_response', 'status'])
                
                return {
                    'payment_id': str(payment.id),
                    'client_secret': intent.client_secret,
                    'stripe_payment_intent_id': intent.id,
                    'status': 'processing',
                    'amount': str(amount),
                }
            except Exception as e:
                payment.status = 'failed'
                payment.payment_gateway_response = {'error': str(e)}
                payment.save(update_fields=['status', 'payment_gateway_response'])
                logger.exception(f'Stripe payment creation failed for payment {payment.id}')
                raise ValidationError('Payment initiation failed. Please try again.')

    @classmethod
    def _process_wallet_payment(cls, user, appointment, amount, payment_method):
        """Process payment directly from user wallet."""
        with transaction.atomic():
            wallet = cls._get_or_create_wallet(user)
            
            if wallet.balance < amount:
                raise ValidationError(f'Insufficient wallet balance. Available: {wallet.balance}')
            
            # Check if a Payment record already exists for this appointment
            payment = Payment.objects.filter(appointment=appointment).first()
            if payment:
                if payment.status == 'completed':
                    raise ValidationError('Payment already completed for this appointment.')
                
                # Reuse and update the existing payment record
                payment.patient = user
                payment.amount = amount
                payment.Payment_method = payment_method
                payment.status = 'completed'
                payment.completed_at = timezone.now()
                payment.transaction_id = f'WALLET-{user.id}-{timezone.now().timestamp()}'
                payment.save(update_fields=[
                    'patient', 'amount', 'Payment_method', 'status', 'completed_at', 'transaction_id', 'updated_at'
                ])
            else:
                payment = Payment.objects.create(
                    patient=user,
                    appointment=appointment,
                    amount=amount,
                    Payment_method=payment_method,
                    status='completed',
                    completed_at=timezone.now(),
                    transaction_id=f'WALLET-{user.id}-{timezone.now().timestamp()}',
                )
            
            # Deduct from wallet
            wallet.balance -= amount
            wallet.save(update_fields=['balance', 'updated_at'])
            
            # Log transaction
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='debit',
                amount=amount,
                balance_after=wallet.balance,
                description=f'Payment for appointment',
                reference=str(payment.id),
                Payment=payment,
            )
            
            # Update appointment and initiate Call Session
            appointment.payment_status = 'paid'
            appointment.save(update_fields=['payment_status'])
            try:
                appointment.create_call_session()
            except Exception as e:
                logger.error(f"Failed to create call session for wallet payment {payment.id}: {e}")
            
            return {
                'payment_id': str(payment.id),
                'status': 'completed',
                'amount': str(amount),
                'message': 'Payment processed from wallet balance.',
            }

    @classmethod
    def complete_payment(cls, payment_id, stripe_response):
        """
        Complete payment after Stripe charge verification.
        Called from webhook or frontend confirmation.
        """
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(id=payment_id)
            
            if payment.status == 'completed':
                logger.info(f'Payment {payment_id} already completed.')
                return payment
            
            charge_id = stripe_response.get('charges', {}).get('data', [{}])[0].get('id')
            card_brand = stripe_response.get('charges', {}).get('data', [{}])[0].get('payment_method_details', {}).get('card', {}).get('brand', '')
            card_last4 = stripe_response.get('charges', {}).get('data', [{}])[0].get('payment_method_details', {}).get('card', {}).get('last4', '')
            
            payment.stripe_charge_id = charge_id
            payment.card_brand = card_brand
            payment.card_last_four = card_last4
            payment.status = 'completed'
            payment.completed_at = timezone.now()
            payment.payment_gateway_response = stripe_response
            payment.save(update_fields=[
                'card_brand', 'card_last_four',
                'status', 'completed_at', 'payment_gateway_response', 'updated_at'
            ])
            
            # Update appointment and initiate Call Session
            if payment.appointment:
                payment.appointment.payment_status = 'paid'
                payment.appointment.save(update_fields=['payment_status',])
                try:
                    payment.appointment.create_call_session()
                except Exception as e:
                    logger.error(f"Failed to create call session for stripe payment {payment.id}: {e}")
            
            logger.info(f'Payment {payment_id} completed.')
            return payment

    @classmethod
    def fail_payment(cls, payment_id, error_message):
        """Mark payment as failed."""
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(id=payment_id)
            payment.status = 'failed'
            payment.payment_gateway_response = {'error': error_message}
            payment.save(update_fields=['status', 'payment_gateway_response', 'updated_at'])
            logger.warning(f'Payment {payment_id} marked as failed: {error_message}')
            return payment

    @classmethod
    def process_refund(cls, payment_id, amount=None, reason=''):
        """
        Process refund for a payment.
        Handles both full and partial refunds.
        """
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(id=payment_id)
            
            if payment.status != 'completed':
                raise ValidationError('Only completed payments can be refunded.')
            
            if payment.status == 'refunded':
                raise ValidationError('Payment already refunded.')
            
            refund_amount = Decimal(str(amount)) if amount else payment.amount
            
            if refund_amount > payment.amount:
                raise ValidationError('Refund amount cannot exceed payment amount.')
            
            if not payment.stripe_charge_id:
                raise ValidationError('Cannot refund payment without Stripe charge ID.')
            
            try:
                # Process Stripe refund
                refund_amount_cents = int(refund_amount * 100)
                stripe_refund = cls.gateway.refund_payment(
                    stripe_charge_id=payment.stripe_charge_id,
                    amount_cents=refund_amount_cents if refund_amount < payment.amount else None,
                    reason=reason,
                )
                
                # Update payment record
                payment.refund_amount = refund_amount
                payment.refund_reason = reason or 'Refund requested'
                payment.refunded_at = timezone.now()
                payment.status = 'refunded'
                payment.payment_gateway_response['refund_id'] = stripe_refund.id
                payment.save(update_fields=[
                    'refund_amount', 'refund_reason', 'refunded_at',
                    'status', 'payment_gateway_response', 'updated_at'
                ])
                
                # Add refund to user wallet
                cls._add_wallet_credit(payment.patient, refund_amount, f'Refund for payment {payment_id}', str(payment_id))
                
                # Update appointment status
                if payment.appointment:
                    payment.appointment.payment_status = 'refunded'
                    payment.appointment.save(update_fields=['payment_status'])
                
                logger.info(f'Refund processed for payment {payment_id}: {refund_amount}')
                return payment
            
            except Exception as e:
                logger.exception(f'Refund failed for payment {payment_id}: {e}')
                raise ValidationError(f'Refund processing failed: {str(e)}')

    @classmethod
    def _get_or_create_wallet(cls, user):
        """Get or create user wallet."""
        wallet, _ = UserWallet.objects.get_or_create(user=user, defaults={'balance': Decimal('0.00')})
        return wallet

    @classmethod
    def _add_wallet_credit(cls, user, amount, description, reference):
        """Add credit to user wallet."""
        with transaction.atomic():
            wallet = cls._get_or_create_wallet(user)
            amount = Decimal(str(amount))
            
            wallet.balance += amount
            wallet.updated_at = timezone.now()
            wallet.save(update_fields=['balance', 'updated_at'])
            
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='credit',
                amount=amount,
                balance_after=wallet.balance,
                description=description,
                reference=reference,
            )
            logger.info(f'Wallet credit added for user {user.id}: {amount}')

    @classmethod
    def add_wallet_funds(cls, user, amount, payment_method):
        """
        Add funds to user wallet via payment method.
        Creates a Payment record for the fund addition.
        """
        amount = cls._validate_amount(amount)
        
        with transaction.atomic():
            if payment_method == 'card':
                # Create Payment record for fund addition
                payment = Payment.objects.create(
                    patient=user,
                    amount=amount,
                    Payment_method=payment_method,
                    status='pending',
                    meta_data={'fund_addition': True, 'user_id': str(user.id)},
                )
                
                try:
                    amount_cents = int(amount * 100)
                    intent = cls.gateway.create_payment_intent(
                        amount_cents=amount_cents,
                        currency='usd',
                        metadata={
                            'payment_id': str(payment.id),
                            'user_id': str(user.id),
                            'fund_addition': 'true',
                        },
                        description=f'Add funds to wallet account',
                    )
                    
                    payment.transaction_id = intent.id
                    payment.payment_gateway_response = intent.to_dict()
                    payment.status = 'processing'
                    payment.save(update_fields=['transaction_id', 'payment_gateway_response', 'status'])
                    
                    return {
                        'payment_id': str(payment.id),
                        'client_secret': intent.client_secret,
                        'stripe_payment_intent_id': intent.id,
                        'status': 'processing',
                    }
                except Exception as e:
                    payment.status = 'failed'
                    payment.payment_gateway_response = {'error': str(e)}
                    payment.save(update_fields=['status', 'payment_gateway_response'])
                    logger.exception(f'Wallet fund payment creation failed: {e}')
                    raise ValidationError('Fund addition failed. Please try again.')
            else:
                raise ValidationError(f'Payment method {payment_method} not supported for wallet funding.')

    @classmethod
    def complete_wallet_fund_addition(cls, payment_id):
        """Complete wallet fund addition after payment confirmation."""
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(id=payment_id)
            
            if payment.status == 'completed':
                return payment
            
            payment.status = 'completed'
            payment.completed_at = timezone.now()
            payment.save(update_fields=['status', 'completed_at', 'updated_at'])
            
            # Add funds to wallet
            cls._add_wallet_credit(
                payment.patient,
                payment.amount,
                'Wallet fund addition',
                str(payment.id)
            )
            
            logger.info(f'Wallet fund addition completed for payment {payment_id}')
            return payment


class StripeWebhookService:
    """
    Service for processing Stripe webhook events.
    Ensures idempotency and proper payment status updates.
    """
    
    @classmethod
    def process_event(cls, raw_body, signature_header):
        """
        Process Stripe webhook event with idempotency.
        """
        gateway = StripeGateway()
        event = gateway.construct_event(raw_body, signature_header)
        
        event_id = event.get('id')
        if not event_id:
            raise ValidationError('Event ID missing from Stripe webhook.')
        
        # Idempotency: check if event already processed
        stripe_event, created = StripeEvent.objects.get_or_create(
            stripe_event_id=event_id,
            defaults={
                'event_type': event.get('type', ''),
                'payload': event,
            }
        )
        
        if stripe_event.processed:
            logger.info(f'Stripe event {event_id} already processed.')
            return stripe_event
        
        event_type = event.get('type')
        event_data = event.get('data', {}).get('object', {})
        
        with transaction.atomic():
            try:
                if event_type == 'payment_intent.succeeded':
                    cls._handle_payment_succeeded(event_data)
                
                elif event_type == 'payment_intent.payment_failed':
                    cls._handle_payment_failed(event_data)
                
                elif event_type == 'payment_intent.canceled':
                    cls._handle_payment_canceled(event_data)
                
                elif event_type == 'charge.refunded':
                    cls._handle_charge_refunded(event_data)
                
                else:
                    logger.info(f'Unhandled Stripe event type: {event_type}')
                
                stripe_event.processed = True
                stripe_event.processed_at = timezone.now()
                stripe_event.save(update_fields=['processed', 'processed_at'])
                
            except Exception as e:
                logger.exception(f'Error processing webhook event {event_id}: {e}')
                raise
        
        return stripe_event

    @classmethod
    def _handle_payment_succeeded(cls, event_data):
        """Handle successful payment."""
        intent_id = event_data.get('id')
        payment = Payment.objects.filter(transaction_id=intent_id).select_for_update().first()
        
        if not payment:
            logger.warning(f'Payment not found for intent {intent_id}')
            return
        
        payment.status = 'completed'
        payment.completed_at = timezone.now()
        payment.payment_gateway_response = event_data
        
        # Extract card details
        charges = event_data.get('charges', {}).get('data', [])
        if charges:
            charge = charges[0]
            payment.stripe_charge_id = charge.get('id')
            card = charge.get('payment_method_details', {}).get('card', {})
            payment.card_last_four = card.get('last4')
            payment.card_brand = card.get('brand')
        
        payment.save(update_fields=[
            'status', 'completed_at', 'payment_gateway_response',
            'stripe_charge_id', 'card_last_four', 'card_brand', 'updated_at'
        ])
        
        # If this is a wallet fund addition, credit the wallet
        if payment.meta_data.get('fund_addition'):
            PaymentService._add_wallet_credit(
                payment.patient,
                payment.amount,
                'Wallet fund addition',
                str(payment.id)
            )
        
        # Update appointment if exists
        if payment.appointment:
            payment.appointment.payment_status = 'paid'
            payment.appointment.save(update_fields=['payment_status'])
        
        logger.info(f'Payment {payment.id} marked as completed via webhook')

    @classmethod
    def _handle_payment_failed(cls, event_data):
        """Handle failed payment."""
        intent_id = event_data.get('id')
        payment = Payment.objects.filter(transaction_id=intent_id).select_for_update().first()
        
        if not payment:
            logger.warning(f'Payment not found for failed intent {intent_id}')
            return
        
        error_msg = event_data.get('last_payment_error', {}).get('message', 'Payment failed')
        payment.status = 'failed'
        payment.payment_gateway_response = {'error': error_msg, 'event_data': event_data}
        payment.save(update_fields=['status', 'payment_gateway_response', 'updated_at'])
        
        logger.warning(f'Payment {payment.id} marked as failed via webhook: {error_msg}')

    @classmethod
    def _handle_payment_canceled(cls, event_data):
        """Handle canceled payment."""
        intent_id = event_data.get('id')
        payment = Payment.objects.filter(transaction_id=intent_id).select_for_update().first()
        
        if not payment:
            logger.warning(f'Payment not found for canceled intent {intent_id}')
            return
        
        payment.status = 'failed'
        payment.payment_gateway_response = {'status': 'canceled', 'event_data': event_data}
        payment.save(update_fields=['status', 'payment_gateway_response', 'updated_at'])
        
        logger.info(f'Payment {payment.id} marked as canceled via webhook')

    @classmethod
    def _handle_charge_refunded(cls, event_data):
        """Handle refunded charge."""
        charge_id = event_data.get('id')
        payment = Payment.objects.filter(stripe_charge_id=charge_id).select_for_update().first()
        
        if not payment:
            logger.warning(f'Payment not found for refunded charge {charge_id}')
            return
        
        # Stripe refund amount is in cents
        refund_amount = Decimal(str(event_data.get('amount_refunded', 0))) / 100
        
        payment.status = 'refunded'
        payment.refund_amount = refund_amount
        payment.refunded_at = timezone.now()
        payment.payment_gateway_response['refund_event'] = event_data
        payment.save(update_fields=['status', 'refund_amount', 'refunded_at', 'payment_gateway_response', 'updated_at'])
        
        # Credit user wallet with refund amount if not already credited
        existing_credit = WalletTransaction.objects.filter(
            reference=str(payment.id),
            transaction_type='refund'
        ).exists()
        
        if not existing_credit:
            PaymentService._add_wallet_credit(
                payment.patient,
                refund_amount,
                'Payment refund',
                str(payment.id)
            )
        
        logger.info(f'Payment {payment.id} refunded via webhook: {refund_amount}')
