import stripe
import logging
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class StripeGateway:
    """
    Stripe payment gateway wrapper for handling payment operations.
    Isolates Stripe API interactions for maintainability and testability.
    """

    def __init__(self):
        secret_key = getattr(settings, 'STRIPE_SECRET_KEY', None)
        if not secret_key:
            raise ImproperlyConfigured('STRIPE_SECRET_KEY is required in settings')
        
        stripe.api_key = secret_key
        self.webhook_secret = getattr(settings, 'STRIP_WEBHOOK_SECRET', None)
        if not self.webhook_secret:
            raise ImproperlyConfigured('STRIP_WEBHOOK_SECRET is required in settings')

    def create_payment_intent(self, amount_cents, currency='usd', metadata=None, description=None):
        """
        Create a Stripe PaymentIntent for card processing.
        Amount is in cents.
        """
        try:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency.lower(),
                payment_method_types=['card'],
                metadata=metadata or {},
                description=description or '',
            )
            logger.info(f'Created PaymentIntent: {intent.id}')
            return intent
        except stripe.error.CardError as e:
            logger.error(f'Card error: {e.user_message}')
            raise
        except stripe.error.RateLimitError as e:
            logger.error(f'Stripe rate limit: {e}')
            raise
        except stripe.error.AuthenticationError as e:
            logger.error(f'Stripe authentication error: {e}')
            raise
        except stripe.error.APIConnectionError as e:
            logger.error(f'Stripe connection error: {e}')
            raise
        except Exception as e:
            logger.exception(f'Stripe PaymentIntent creation failed: {e}')
            raise

    def retrieve_payment_intent(self, intent_id):
        """Retrieve existing PaymentIntent details."""
        try:
            intent = stripe.PaymentIntent.retrieve(intent_id)
            return intent
        except Exception as e:
            logger.exception(f'Failed to retrieve PaymentIntent {intent_id}: {e}')
            raise

    def construct_event(self, payload, sig_header):
        """
        Construct and verify Stripe webhook event.
        Validates webhook signature for security.
        """
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=self.webhook_secret,
            )
            logger.info(f'Verified webhook event: {event.id}')
            return event
        except stripe.error.SignatureVerificationError as e:
            logger.warning(f'Invalid Stripe webhook signature: {e}')
            raise
        except Exception as e:
            logger.exception(f'Webhook event construction failed: {e}')
            raise

    def refund_payment(self, stripe_charge_id, amount_cents=None, reason=None):
        """
        Refund a charge. If amount not specified, full refund is processed.
        """
        try:
            refund_params = {'charge': stripe_charge_id}
            if amount_cents:
                refund_params['amount'] = amount_cents
            if reason:
                refund_params['reason'] = reason
            
            refund = stripe.Refund.create(**refund_params)
            logger.info(f'Created refund: {refund.id} for charge {stripe_charge_id}')
            return refund
        except Exception as e:
            logger.exception(f'Refund failed for charge {stripe_charge_id}: {e}')
            raise
