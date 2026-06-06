import stripe
import logging
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class StripeGateway:
    """
    Stripe payment gateway wrapper for handling payment operations.
    Isolates Stripe API interactions for maintainability and testability.
    Handles all communication with Stripe API securely.
    """

    def __init__(self):
        # Support both STRIPE_SECRET_KEY and STRIP_SECRET_KEY (legacy naming)
        secret_key = (
            getattr(settings, 'STRIPE_SECRET_KEY', None)
            or getattr(settings, 'STRIP_SECRET_KEY', None)
        )
        if not secret_key:
            raise ImproperlyConfigured(
                'STRIPE_SECRET_KEY is required in settings'
            )
        
        stripe.api_key = secret_key
        
        # Support both STRIPE_WEBHOOK_SECRET and STRIP_WEBHOOK_SECRET
        self.webhook_secret = (
            getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)
            or getattr(settings, 'STRIP_WEBHOOK_SECRET', None)
        )
        if not self.webhook_secret:
            raise ImproperlyConfigured(
                'STRIPE_WEBHOOK_SECRET is required in settings'
            )

    def create_payment_intent(self, amount_cents, currency='usd', metadata=None, description=None):
        """
        Create a Stripe PaymentIntent for card processing.
        Amount parameter should be in cents (e.g., $100.00 = 10000 cents).
        
        Args:
            amount_cents (int): Amount in cents
            currency (str): Currency code (default: usd)
            metadata (dict): Additional metadata to attach
            description (str): Description for the PaymentIntent
            
        Returns:
            stripe.PaymentIntent: The created PaymentIntent object
        """
        try:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency.lower(),
                payment_method_types=['card'],
                metadata=metadata or {},
                description=description or '',
            )
            logger.info(f'Created PaymentIntent: {intent.id} for amount {amount_cents} {currency}')
            return intent
        except stripe.error.CardError as e:
            logger.error(f'Card error in PaymentIntent creation: {e.user_message}')
            raise
        except stripe.error.RateLimitError as e:
            logger.error(f'Stripe rate limit exceeded: {e}')
            raise
        except stripe.error.AuthenticationError as e:
            logger.error(f'Stripe authentication failed: {e}')
            raise
        except stripe.error.APIConnectionError as e:
            logger.error(f'Stripe API connection error: {e}')
            raise
        except Exception as e:
            logger.exception(f'Unexpected error creating PaymentIntent: {e}')
            raise

    def retrieve_payment_intent(self, intent_id):
        """
        Retrieve an existing PaymentIntent by ID.
        
        Args:
            intent_id (str): Stripe PaymentIntent ID
            
        Returns:
            stripe.PaymentIntent: The PaymentIntent object
        """
        try:
            intent = stripe.PaymentIntent.retrieve(intent_id)
            logger.info(f'Retrieved PaymentIntent: {intent_id}')
            return intent
        except stripe.error.InvalidRequestError as e:
            logger.error(f'Invalid PaymentIntent ID: {intent_id} - {e}')
            raise
        except Exception as e:
            logger.exception(f'Error retrieving PaymentIntent {intent_id}: {e}')
            raise

    def construct_event(self, payload, sig_header):
        """
        Construct and verify Stripe webhook event.
        Validates webhook signature to ensure authenticity.
        
        Args:
            payload (bytes): Raw request body from Stripe
            sig_header (str): Stripe-Signature header value
            
        Returns:
            dict: The verified webhook event
            
        Raises:
            stripe.error.SignatureVerificationError: If signature is invalid
        """
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=self.webhook_secret,
            )
            logger.info(f'Verified webhook event: {event.id} (type: {event.get("type")})')
            return event
        except stripe.error.SignatureVerificationError as e:
            logger.warning(f'Invalid webhook signature: {e}')
            raise
        except Exception as e:
            logger.exception(f'Error constructing webhook event: {e}')
            raise

    def refund_payment(self, stripe_charge_id, amount_cents=None, reason=None):
        """
        Create a refund for a charge or PaymentIntent.
        
        Args:
            stripe_charge_id (str): Stripe Charge ID
            amount_cents (int): Amount to refund in cents (None for full refund)
            reason (str): Reason for refund
            
        Returns:
            stripe.Refund: The refund object
        """
        try:
            refund_params = {'charge': stripe_charge_id}
            if amount_cents:
                refund_params['amount'] = amount_cents
            if reason:
                refund_params['reason'] = reason
            
            refund = stripe.Refund.create(**refund_params)
            logger.info(
                f'Created refund {refund.id} for charge {stripe_charge_id} '
                f'(amount: {amount_cents or "full"} cents)'
            )
            return refund
        except stripe.error.InvalidRequestError as e:
            logger.error(f'Invalid refund request for charge {stripe_charge_id}: {e}')
            raise
        except Exception as e:
            logger.exception(f'Error processing refund for charge {stripe_charge_id}: {e}')
            raise

