import logging
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from consultations.models import Appointment
from .models import Payment, UserWallet, WalletTransaction
from .serializers import (
    InitiatePaymentSerializer, PaymentSerializer,
    PaymentSummarySerializer, UserWalletSerializer,
    AddFundsSerializer, RefundPaymentSerializer,
    WalletTransactionSeriaizer, CompletePaymentResponseSerializer,
    AddWalletFundsResponseSerializer
)
from .services import PaymentService

logger = logging.getLogger(__name__)


class PaymentPagination(PageNumberPagination):
    """Custom pagination for payment listings."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_payment_view(request):
    """
    Initiate a payment for an appointment.
    Supports card, wallet, paypal, and insurance payment methods.
    
    Request:
    {
        "appointment_id": "uuid",
        "payment_method": "card",
        "paypal_email": "optional",
        "insurance_provider": "optional",
        "insurance_number": "optional"
    }
    
    Response:
    {
        "payment_id": "uuid",
        "client_secret": "string (for card payments)",
        "stripe_payment_intent_id": "string",
        "status": "processing",
        "amount": "decimal"
    }
    """
    serializer = InitiatePaymentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    try:
        appointment = Appointment.objects.get(id=serializer.validated_data['appointment_id'])
        
        # Verify user is the patient
        if appointment.patient != request.user:
            return Response(
                {'detail': 'Unauthorized: You can only pay for your own appointments.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get appointment fee
        amount = appointment.consultation_fee
        payment_method = serializer.validated_data['Payment_method']
        
        result = PaymentService.initiate_payment(
            user=request.user,
            appointment=appointment,
            amount=amount,
            payment_method=payment_method,
        )
        
        return Response(result, status=status.HTTP_201_CREATED)
    
    except Appointment.DoesNotExist:
        return Response({'detail': 'Appointment not found.'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f'Payment initiation error: {e}')
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirm_payment_view(request):
    """
    Confirm payment after Stripe card confirmation.
    Called after frontend confirms card payment with Stripe.
    
    Request:
    {
        "payment_id": "uuid",
        "stripe_payment_intent_id": "string"
    }
    """
    try:
        payment_id = request.data.get('payment_id')
        if not payment_id:
            return Response({'detail': 'payment_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        payment = get_object_or_404(Payment, id=payment_id, patient=request.user)
        
        if payment.status == 'completed':
            return Response(
                {'detail': 'Payment already completed.', 'payment': PaymentSerializer(payment).data},
                status=status.HTTP_200_OK
            )
        
        # Retrieve PaymentIntent from Stripe to verify
        stripe_intent_id = payment.transaction_id
        if not stripe_intent_id:
            return Response({'detail': 'Invalid payment record.'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            stripe_intent = PaymentService.gateway.retrieve_payment_intent(stripe_intent_id)
            
            if stripe_intent.status == 'succeeded':
                PaymentService.complete_payment(payment_id, stripe_intent.to_dict())
                payment.refresh_from_db()
                return Response(
                    {'detail': 'Payment confirmed successfully.', 'payment': PaymentSerializer(payment).data},
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {'detail': f'Payment status: {stripe_intent.status}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            logger.exception(f'Payment confirmation error: {e}')
            return Response({'detail': 'Payment verification failed.'}, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.exception(f'Confirm payment error: {e}')
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_status_view(request, payment_id):
    """
    Get payment status and details.
    
    Response:
    {
        "id": "uuid",
        "appointment_id": "uuid",
        "amount": "decimal",
        "status": "pending|processing|completed|failed|refunded",
        "payment_method": "card",
        "card_last_four": "1234",
        "card_brand": "visa",
        ...
    }
    """
    try:
        payment = get_object_or_404(Payment, id=payment_id, patient=request.user)
        serializer = PaymentSerializer(payment)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception(f'Payment status error: {e}')
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_history_view(request):
    """
    Get user's payment history with pagination.
    
    Query Parameters:
    - page: Page number (default 1)
    - page_size: Items per page (default 20, max 100)
    - status: Filter by status (pending, completed, failed, refunded)
    
    Response: Paginated list of payments
    """
    try:
        queryset = Payment.objects.filter(patient=request.user).order_by('-created_at')
        
        # Filter by status if provided
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        paginator = PaymentPagination()
        page = paginator.paginate_queryset(queryset, request)
        
        if page is not None:
            serializer = PaymentSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        serializer = PaymentSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception(f'Payment history error: {e}')
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def refund_payment_view(request):
    """
    Request refund for a completed payment.
    
    Request:
    {
        "payment": "uuid",
        "amount": "decimal (optional for partial refund)",
        "reason": "string"
    }
    """
    serializer = RefundPaymentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    try:
        payment = get_object_or_404(Payment, id=serializer.validated_data['payment'], patient=request.user)
        
        result = PaymentService.process_refund(
            payment_id=payment.id,
            amount=serializer.validated_data.get('amount'),
            reason=serializer.validated_data.get('reason', ''),
        )
        
        return Response(
            {'detail': 'Refund processed successfully.', 'payment': PaymentSerializer(result).data},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        logger.exception(f'Refund error: {e}')
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ============= WALLET ENDPOINTS =============

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def wallet_balance_view(request):
    """
    Get user's wallet balance and recent transactions.
    
    Response:
    {
        "user_name": "John Doe",
        "balance": "1500.50",
        "created_at": "2024-01-01T10:00:00Z",
        "updated_at": "2024-01-02T15:30:00Z",
        "recent_transactions": [...]
    }
    """
    try:
        wallet, _ = UserWallet.objects.get_or_create(user=request.user, defaults={'balance': 0})
        serializer = UserWalletSerializer(wallet)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception(f'Wallet balance error: {e}')
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_wallet_funds_view(request):
    """
    Add funds to wallet via card payment.
    
    Request:
    {
        "amount": "decimal",
        "payment_method": "card|paypal"
    }
    
    Response:
    {
        "message": "string",
        "payment_intent_id": "string",
        "client_secret": "string",
        "status": "processing"
    }
    """
    serializer = AddFundsSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    try:
        result = PaymentService.add_wallet_funds(
            user=request.user,
            amount=serializer.validated_data['amount'],
            payment_method=serializer.validated_data['payment_method'],
        )
        
        return Response(result, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.exception(f'Add wallet funds error: {e}')
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirm_wallet_fund_view(request):
    """
    Confirm wallet fund addition after payment verification.
    
    Request:
    {
        "payment_id": "uuid"
    }
    """
    try:
        payment_id = request.data.get('payment_id')
        if not payment_id:
            return Response({'detail': 'payment_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        payment = get_object_or_404(Payment, id=payment_id, patient=request.user)
        
        if payment.status == 'completed':
            wallet = UserWallet.objects.get(user=request.user)
            return Response(
                {'detail': 'Funds added successfully.', 'wallet': UserWalletSerializer(wallet).data},
                status=status.HTTP_200_OK
            )
        
        # Verify Stripe payment
        stripe_intent = PaymentService.gateway.retrieve_payment_intent(payment.transaction_id)
        if stripe_intent.status == 'succeeded':
            PaymentService.complete_wallet_fund_addition(payment_id)
            wallet = UserWallet.objects.get(user=request.user)
            return Response(
                {'detail': 'Funds added successfully.', 'wallet': UserWalletSerializer(wallet).data},
                status=status.HTTP_200_OK
            )
        else:
            return Response({'detail': 'Payment not yet confirmed.'}, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.exception(f'Confirm wallet fund error: {e}')
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def wallet_transactions_view(request):
    """
    Get wallet transaction history.
    
    Query Parameters:
    - page: Page number
    - page_size: Items per page
    - transaction_type: credit|debit|refund
    
    Response: Paginated list of transactions
    """
    try:
        wallet = get_object_or_404(UserWallet, user=request.user)
        queryset = WalletTransaction.objects.filter(wallet=wallet).order_by('-created_at')
        
        txn_type = request.query_params.get('transaction_type')
        if txn_type:
            queryset = queryset.filter(transaction_type=txn_type)
        
        paginator = PaymentPagination()
        page = paginator.paginate_queryset(queryset, request)
        
        if page is not None:
            serializer = WalletTransactionSeriaizer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        serializer = WalletTransactionSeriaizer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception(f'Wallet transactions error: {e}')
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_summary_view(request, appointment_id):
    """
    Get payment summary for an appointment before initiating payment.
    
    Response:
    {
        "appointment_id": "uuid",
        "consultant_name": "string",
        "scheduled_date": "date",
        "consultation_fee": "decimal",
        "wallet_balance": "decimal"
    }
    """
    try:
        appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.user)
        wallet, _ = UserWallet.objects.get_or_create(user=request.user, defaults={'balance': 0})
        
        data = {
            'appointment_id': appointment.id,
            'consultant_name': appointment.consultant.user.get_full_name(),
            'scheduled_date': appointment.scheduled_date,
            'scheduled_time': appointment.scheduled_time.strftime('%H:%M') if appointment.scheduled_time else '',
            'consultation_fee': appointment.consultation_fee,
            'wallet_balance': wallet.balance,
        }
        
        serializer = PaymentSummarySerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception(f'Payment summary error: {e}')
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

