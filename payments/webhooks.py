import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import AllowAny
# from rest_framework.parsers import RawPostParser
from rest_framework.response import Response
from .parsers import RawPostParser

from .services import StripeWebhookService

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(['POST'])
@api_view(['POST'])
@permission_classes([AllowAny])
@parser_classes([RawPostParser])
def stripe_webhook_handler(request):
    """
    Stripe webhook endpoint for handling payment events.
    
    CSRF is exempted because Stripe cannot send CSRF tokens.
    Security is enforced by Stripe signature verification in the gateway.
     
    Handles events:
    - payment_intent.succeeded
    - payment_intent.payment_failed
    - payment_intent.canceled
    - charge.refunded
    
    Request:
        - Raw JSON payload from Stripe
        - HTTP_STRIPE_SIGNATURE header with signature
    
    Response:
        - 200 OK if successfully processed or already processed (idempotent)
        - 400 BAD_REQUEST if signature invalid or processing fails
    """
    signature = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    if not signature:
        logger.warning('Webhook received without Stripe signature header')
        return Response(
            {'error': 'Missing Stripe signature header'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        event_record = StripeWebhookService.process_event(
            raw_body=request.body,
            signature_header=signature,
        )
        
        return Response(
            {
                'success': True,
                'event_id': event_record.stripe_event_id,
                'event_type': event_record.event_type,
            },
            status=status.HTTP_200_OK
        )
    
    except Exception as e:
        logger.error(f'Webhook processing failed: {e}')
        return Response(
            {'error': 'Webhook processing failed'},
            status=status.HTTP_400_BAD_REQUEST
        )
