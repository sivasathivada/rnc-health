from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from datetime import date, time, timedelta
from unittest.mock import patch, MagicMock

from consultations.models import Appointment
from consultants.models import ConsultantProfile
from payments.models import Payment, UserWallet
from payments.services import PaymentService

User = get_user_model()

class PaymentRetryTestCase(TestCase):
    def setUp(self):
        # Create users
        self.patient = User.objects.create_user(
            email='patient_test@example.com',
            password='password123',
            first_name='Patient',
            last_name='Test',
            role='patient'
        )
        self.consultant_user = User.objects.create_user(
            email='consultant_test@example.com',
            password='password123',
            first_name='Consultant',
            last_name='Test',
            role='consultant'
        )
        self.consultant_profile = ConsultantProfile.objects.create(
            user=self.consultant_user,
            speciality=None,
            is_verified=True,
            is_available=True
        )
        
        # Create appointment
        self.appointment = Appointment.objects.create(
            consultant=self.consultant_profile,
            patient=self.patient,
            Appointment_type='video',
            status='pending',
            scheduled_date=date.today() + timedelta(days=1),
            scheduled_time=time(14, 0),
            duration_minutes=30,
            reason_for_visit='Heart checkup',
            consultation_fee=50.00
        )

    @patch('payments.payment_gateway.StripeGateway.create_payment_intent')
    def test_initiate_stripe_payment_first_time(self, mock_create_intent):
        # Mock Stripe intent creation
        mock_intent = MagicMock()
        mock_intent.id = 'pi_test_123'
        mock_intent.client_secret = 'secret_123'
        mock_intent.to_dict.return_value = {'id': 'pi_test_123'}
        mock_create_intent.return_value = mock_intent

        result = PaymentService.initiate_payment(
            user=self.patient,
            appointment=self.appointment,
            amount=50.00,
            payment_method='card'
        )

        self.assertEqual(result['status'], 'processing')
        self.assertEqual(result['stripe_payment_intent_id'], 'pi_test_123')
        
        # Verify Payment record created in DB
        payment = Payment.objects.get(appointment=self.appointment)
        self.assertEqual(payment.status, 'processing')
        self.assertEqual(payment.transaction_id, 'pi_test_123')
        self.assertEqual(payment.amount, 50.00)

    @patch('payments.payment_gateway.StripeGateway.create_payment_intent')
    def test_initiate_stripe_payment_retry_after_failure(self, mock_create_intent):
        # 1. Create a failed payment first
        failed_payment = Payment.objects.create(
            patient=self.patient,
            appointment=self.appointment,
            amount=50.00,
            Payment_method='card',
            status='failed',
            transaction_id='pi_failed_abc',
            payment_gateway_response={'error': 'Card declined'}
        )

        # 2. Mock next Stripe intent creation for retry
        mock_intent = MagicMock()
        mock_intent.id = 'pi_success_xyz'
        mock_intent.client_secret = 'secret_success'
        mock_intent.to_dict.return_value = {'id': 'pi_success_xyz'}
        mock_create_intent.return_value = mock_intent

        # 3. Initiate payment again (retry)
        result = PaymentService.initiate_payment(
            user=self.patient,
            appointment=self.appointment,
            amount=50.00,
            payment_method='card'
        )

        self.assertEqual(result['status'], 'processing')
        self.assertEqual(result['stripe_payment_intent_id'], 'pi_success_xyz')
        
        # 4. Verify that existing Payment record was updated, not duplicated
        payment_count = Payment.objects.filter(appointment=self.appointment).count()
        self.assertEqual(payment_count, 1)

        failed_payment.refresh_from_db()
        self.assertEqual(failed_payment.status, 'processing')
        self.assertEqual(failed_payment.transaction_id, 'pi_success_xyz')

    def test_initiate_payment_when_already_completed(self):
        # Create a completed payment first
        Payment.objects.create(
            patient=self.patient,
            appointment=self.appointment,
            amount=50.00,
            Payment_method='card',
            status='completed',
            transaction_id='pi_completed_123',
            completed_at=timezone.now()
        )

        # Retrying should raise ValidationError
        with self.assertRaises(ValidationError) as context:
            PaymentService.initiate_payment(
                user=self.patient,
                appointment=self.appointment,
                amount=50.00,
                payment_method='card'
            )
        self.assertIn('Payment already completed', str(context.exception))

    def test_initiate_wallet_payment_retry_after_failure(self):
        # 1. Create a failed payment first
        Payment.objects.create(
            patient=self.patient,
            appointment=self.appointment,
            amount=50.00,
            Payment_method='card',
            status='failed',
            transaction_id='pi_failed_abc',
            payment_gateway_response={'error': 'Card declined'}
        )

        # 2. Setup wallet with enough balance
        wallet = UserWallet.objects.create(user=self.patient, balance=100.00)

        # 3. Initiate wallet payment (retry via wallet)
        result = PaymentService.initiate_payment(
            user=self.patient,
            appointment=self.appointment,
            amount=50.00,
            payment_method='wallet'
        )

        self.assertEqual(result['status'], 'completed')
        
        # 4. Verify existing record was updated
        payment_count = Payment.objects.filter(appointment=self.appointment).count()
        self.assertEqual(payment_count, 1)

        payment = Payment.objects.get(appointment=self.appointment)
        self.assertEqual(payment.status, 'completed')
        self.assertEqual(payment.Payment_method, 'wallet')
        self.assertTrue(payment.transaction_id.startswith('WALLET-'))
