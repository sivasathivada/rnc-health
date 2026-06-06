from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from datetime import datetime, timedelta, time, date
import uuid
import json

from .models import CallSession, Prescription, Appointment, AppointmentSlot
from .serializers import (
    CallSessionSerializer, CallInitiateRequestSerializer,
    AppointmentCreateSerializer, AppointmentSlotSerializer
)
from .services import AppointmentService, CallSessionService, NotificationService
from consultants.models import ConsultantProfile

User = get_user_model()


#   writing Fixers and Helper Functions using unit test framework

class ConsultationTestBase(TestCase):
    """Base test class with common setup for consultation tests"""

    def setUp(self):
        """Set up test data before each test"""
        # Create test users
        self.patient_user = self._create_user(
            email='patient@test.com',
            first_name='John',
            last_name='Doe',
            role='patient'
        )
        
        self.consultant_user = self._create_user(
            email='consultant@test.com',
            first_name='Dr',
            last_name='Smith',
            role='consultant'
        )

        self.admin_user = self._create_user(
            email='admin@test.com',
            first_name='Admin',
            last_name='User',
            role='admin',
            is_staff=True,
            is_superuser=True
        )

    def _create_user(self, email, first_name, last_name, role, 
                     is_staff=False, is_superuser=False, password='testpass123'):
        """Helper to create test users"""
        return User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_staff=is_staff,
            is_superuser=is_superuser
        )

    def _create_consultant_profile(self, user, specialization='General Practice'):
        """Helper to create consultant profile"""
        from consultants.models import Speciality
        spec, _ = Speciality.objects.get_or_create(name=specialization)
        return ConsultantProfile.objects.create(
            user=user,
            speciality=spec,
            is_verified=True,
            is_available=True
        )

    def _create_call_session(self, consultant=None, patient=None, 
                            call_type='video', status='scheduled'):
        """Helper to create call session"""
        if not consultant:
            consultant = self.consultant_user
        if not patient:
            patient = self.patient_user
            
        return CallSession.objects.create(
            session_id=str(uuid.uuid4()),
            consultant=consultant,
            patient=patient,
            call_type=call_type,
            status=status,
            scheduled_at=timezone.now() + timedelta(hours=1),
            consultation_fee=50.00
        )

    def _create_appointment(self, consultant_profile=None, patient=None,
                           status='pending', scheduled_date=None, 
                           scheduled_time=None):
        """Helper to create appointment"""
        if not consultant_profile:
            consultant_profile = self._create_consultant_profile(self.consultant_user)
        if not patient:
            patient = self.patient_user
        if not scheduled_date:
            scheduled_date = date.today() + timedelta(days=1)
        if not scheduled_time:
            scheduled_time = time(14, 0)

        return Appointment.objects.create(
            consultant=consultant_profile,
            patient=patient,
            Appointment_type='video',
            status=status,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            duration_minutes=30,
            reason_for_visit='General consultation',
            consultation_fee=50.00
        )


# writing unit tests for models

class CallSessionModelTests(ConsultationTestBase):
    """Test CallSession model methods and properties"""

    def test_callsession_creation(self):
        """Test creating a CallSession"""
        call_session = self._create_call_session()
        
        self.assertIsNotNone(call_session.id)
        self.assertEqual(call_session.consultant, self.consultant_user)
        self.assertEqual(call_session.patient, self.patient_user)
        self.assertEqual(call_session.status, 'scheduled')
        self.assertEqual(call_session.call_type, 'video')

    def test_callsession_string_representation(self):
        """Test CallSession __str__ method"""
        call_session = self._create_call_session()
        expected = f" call: {self.patient_user.full_name} -> Dr. {self.consultant_user.full_name} (scheduled)"
        
        self.assertEqual(str(call_session), expected)

    def test_duration_formatted_hours_and_minutes(self):
        """Test duration_formatted property with hours and minutes"""
        call_session = self._create_call_session()
        call_session.duration_minutes = 90
        
        self.assertEqual(call_session.duration_formatted, " 1h 30m ")

    def test_duration_formatted_only_minutes(self):
        """Test duration_formatted property with only minutes"""
        call_session = self._create_call_session()
        call_session.duration_minutes = 45
        
        self.assertEqual(call_session.duration_formatted, "45m")

    def test_duration_formatted_zero(self):
        """Test duration_formatted with zero duration"""
        call_session = self._create_call_session()
        call_session.duration_minutes = 0
        
        self.assertEqual(call_session.duration_formatted, "0 minutes")

    def test_start_call(self):
        """Test starting a call session"""
        call_session = self._create_call_session()
        self.assertEqual(call_session.status, 'scheduled')
        
        call_session.start_call()
        
        self.assertEqual(call_session.status, 'ongoing')
        self.assertIsNotNone(call_session.started_at)

    def test_end_call_with_started_time(self):
        """Test ending a call and duration calculation"""
        call_session = self._create_call_session()
        started_time = timezone.now()
        call_session.started_at = started_time
        call_session.status = 'ongoing'
        call_session.save()
        
        # Simulate call duration
        call_session.end_call()
        
        self.assertEqual(call_session.status, 'completed')
        self.assertIsNotNone(call_session.ended_at)
        self.assertGreaterEqual(call_session.duration_minutes, 0)

    def test_end_call_without_started_time(self):
        """Test ending a call without start time"""
        call_session = self._create_call_session()
        call_session.status = 'ongoing'
        call_session.save()
        
        call_session.end_call()
        
        self.assertEqual(call_session.status, 'completed')
        self.assertEqual(call_session.duration_minutes, 0)

    def test_record_offer_exchanged(self):
        """Test recording WebRTC offer exchange"""
        call_session = self._create_call_session()
        
        call_session.record_offer_exchanged()
        call_session.refresh_from_db()
        
        self.assertTrue(call_session.offer_exchanged)
        self.assertIsNotNone(call_session.connection_initiated_at)

    def test_record_answer_exchanged(self):
        """Test recording WebRTC answer exchange"""
        call_session = self._create_call_session()
        
        call_session.record_answer_exchanged()
        call_session.refresh_from_db()
        
        self.assertTrue(call_session.answer_exchanged)

    def test_record_connection_established(self):
        """Test recording connection establishment"""
        call_session = self._create_call_session()
        
        call_session.record_connection_established()
        call_session.refresh_from_db()
        
        self.assertIsNotNone(call_session.connection_established_at)

    def test_add_ice_candidate(self):
        """Test incrementing ICE candidate count"""
        call_session = self._create_call_session()
        initial_count = call_session.ice_candidates_count
        
        call_session.add_ice_candidate()
        call_session.refresh_from_db()
        
        self.assertEqual(call_session.ice_candidates_count, initial_count + 1)

    def test_record_reconnection_attempt(self):
        """Test recording reconnection attempts"""
        call_session = self._create_call_session()
        
        call_session.record_reconnection_attempt()
        call_session.refresh_from_db()
        
        self.assertEqual(call_session.reconnection_attempts, 1)

    def test_update_webrtc_stats(self):
        """Test updating WebRTC statistics"""
        call_session = self._create_call_session()
        stats = {'bandwidth': '2.5Mbps', 'bitrate': '1000kbps'}
        
        call_session.update_webrtc_stats(stats)
        call_session.refresh_from_db()
        
        self.assertIn('bandwidth', call_session.webrtc_stats)
        self.assertEqual(call_session.webrtc_stats['bandwidth'], '2.5Mbps')

    def test_connection_health_healthy(self):
        """Test connection health status - Healthy"""
        call_session = self._create_call_session()
        call_session.connection_quality = 'excellent'
        call_session.reconnection_attempts = 0
        
        self.assertEqual(call_session.connection_health, 'Healthy')

    def test_connection_health_critical(self):
        """Test connection health status - Critical"""
        call_session = self._create_call_session()
        call_session.connection_quality = 'poor'
        
        self.assertEqual(call_session.connection_health, 'Critical')

    def test_connection_health_warning(self):
        """Test connection health status - Warning"""
        call_session = self._create_call_session()
        call_session.connection_quality = 'fair'
        call_session.reconnection_attempts = 3
        
        self.assertEqual(call_session.connection_health, 'Warning')

    def test_connection_health_normal(self):
        """Test connection health status - Normal"""
        call_session = self._create_call_session()
        call_session.connection_quality = 'good'
        call_session.reconnection_attempts = 1
        
        self.assertEqual(call_session.connection_health, 'Normal')

    def test_callsession_session_id_unique(self):
        """Test that session_id is unique"""
        session_id = str(uuid.uuid4())
        
        CallSession.objects.create(
            session_id=session_id,
            consultant=self.consultant_user,
            patient=self.patient_user,
            call_type='video'
        )
        
        with self.assertRaises(Exception):
            CallSession.objects.create(
                session_id=session_id,
                consultant=self.consultant_user,
                patient=self.patient_user,
                call_type='video'
            )


class PrescriptionModelTests(ConsultationTestBase):
    """Test Prescription model"""

    def _create_prescription(self, call_session=None, status='active'):
        """Helper to create prescription"""
        if not call_session:
            call_session = self._create_call_session()
            call_session.status = 'completed'
            call_session.save()
        
        valid_until = timezone.now() + timedelta(days=30)
        
        return Prescription.objects.create(
            call_seesion=call_session,
            consultant=self.consultant_user,
            patient=self.patient_user,
            medications=[
                {'name': 'Aspirin', 'dosage': '500mg', 'frequency': 'twice daily'},
                {'name': 'Vitamin C', 'dosage': '1000mg', 'frequency': 'daily'}
            ],
            instructions='Take with food. Avoid alcohol.',
            status=status,
            valid_until=valid_until
        )

    def test_prescription_creation(self):
        """Test creating a Prescription"""
        call_session = self._create_call_session()
        call_session.status = 'completed'
        call_session.save()
        
        prescription = self._create_prescription(call_session)
        
        self.assertIsNotNone(prescription.id)
        self.assertEqual(prescription.consultant, self.consultant_user)
        self.assertEqual(prescription.patient, self.patient_user)
        self.assertEqual(len(prescription.medications), 2)

    def test_prescription_string_representation(self):
        """Test Prescription __str__ method"""
        prescription = self._create_prescription()
        expected = f"Prescription for {self.patient_user.full_name} by Dr. {self.consultant_user.full_name}"
        
        self.assertEqual(str(prescription), expected)

    def test_prescription_medications_jsonfield(self):
        """Test that medications are stored correctly as JSON"""
        call_session = self._create_call_session()
        call_session.status = 'completed'
        call_session.save()
        
        medications = [
            {'name': 'Metformin', 'dosage': '500mg', 'frequency': '3 times daily'},
        ]
        
        prescription = Prescription.objects.create(
            call_seesion=call_session,
            consultant=self.consultant_user,
            patient=self.patient_user,
            medications=medications,
            instructions='Monitor blood sugar levels',
            status='active',
            valid_until=timezone.now() + timedelta(days=30)
        )
        
        prescription.refresh_from_db()
        self.assertEqual(len(prescription.medications), 1)
        self.assertEqual(prescription.medications[0]['name'], 'Metformin')

    def test_prescription_status_choices(self):
        """Test prescription status choices"""
        valid_statuses = ['active', 'completed', 'cancelled']
        
        for status in valid_statuses:
            prescription = self._create_prescription(status=status)
            self.assertEqual(prescription.status, status)


class AppointmentModelTests(ConsultationTestBase):
    """Test Appointment model"""

    def test_appointment_creation(self):
        """Test creating an Appointment"""
        consultant_profile = self._create_consultant_profile(self.consultant_user)
        appointment = self._create_appointment(consultant_profile)
        
        self.assertIsNotNone(appointment.id)
        self.assertEqual(appointment.consultant, consultant_profile)
        self.assertEqual(appointment.patient, self.patient_user)
        self.assertEqual(appointment.status, 'pending')

    def test_appointment_string_representation(self):
        """Test Appointment __str__ method - if implemented"""
        appointment = self._create_appointment()
        # Add test based on model's __str__ implementation
        self.assertIsNotNone(str(appointment))

    def test_appointment_duration_validation(self):
        """Test that appointment duration has minimum validator"""
        consultant_profile = self._create_consultant_profile(self.consultant_user)
        
        # Try to create appointment with invalid duration
        appointment = Appointment(
            consultant=consultant_profile,
            patient=self.patient_user,
            Appointment_type='video',
            status='pending',
            scheduled_date=date.today() + timedelta(days=1),
            scheduled_time=time(14, 0),
            duration_minutes=10,  # Less than 15 - invalid
            reason_for_visit='Test'
        )
        
        with self.assertRaises(ValidationError):
            appointment.full_clean()

    def test_appointment_payment_status_choices(self):
        """Test appointment payment status choices"""
        appointment = self._create_appointment()
        valid_statuses = ['pending', 'paid', 'refunded']
        
        for status in valid_statuses:
            appointment.payment_status = status
            appointment.full_clean()  # Should not raise

    def test_appointment_type_choices(self):
        """Test appointment type choices"""
        consultant_profile = self._create_consultant_profile(self.consultant_user)
        valid_types = ['video', 'audio', 'in_person']
        
        for appt_type in valid_types:
            appointment = Appointment.objects.create(
                consultant=consultant_profile,
                patient=self.patient_user,
                Appointment_type=appt_type,
                status='pending',
                scheduled_date=date.today() + timedelta(days=1),
                scheduled_time=time(14, 0),
                duration_minutes=30,
                reason_for_visit='Test'
            )
            self.assertEqual(appointment.Appointment_type, appt_type)


# Writing unit tests for service layer

class AppointmentServiceTests(ConsultationTestBase):
    """Test AppointmentService business logic"""

    def setUp(self):
        """Set up test data"""
        super().setUp()
        self.consultant_profile = self._create_consultant_profile(self.consultant_user)

    def test_create_appointment_success(self):
        """Test successfully creating an appointment"""
        data = {
            'scheduled_date': date.today() + timedelta(days=1),
            'scheduled_time': time(14, 0),
            'Appointment_type': 'video',
            'duration_minutes': 30,
            'reason_for_visit': 'General consultation',
            'consultation_fee': 50.00
        }
        
        appointment = AppointmentService.create_appointment(
            self.consultant_profile.id,
            self.patient_user,
            data
        )
        
        self.assertIsNotNone(appointment.id)
        self.assertEqual(appointment.status, 'pending')
        self.assertEqual(appointment.consultant, self.consultant_profile)

    def test_create_appointment_with_unavailable_consultant(self):
        """Test creating appointment with unavailable consultant"""
        self.consultant_profile.is_available = False
        self.consultant_profile.save()
        
        data = {
            'scheduled_date': date.today() + timedelta(days=1),
            'scheduled_time': time(14, 0),
            'Appointment_type': 'video',
            'duration_minutes': 30,
            'reason_for_visit': 'Test'
        }
        
        with self.assertRaises(ValidationError):
            AppointmentService.create_appointment(
                self.consultant_profile.id,
                self.patient_user,
                data
            )

    def test_create_appointment_in_past(self):
        """Test creating appointment in the past"""
        data = {
            'scheduled_date': date.today() - timedelta(days=1),
            'scheduled_time': time(14, 0),
            'Appointment_type': 'video',
            'duration_minutes': 30,
            'reason_for_visit': 'Test'
        }
        
        with self.assertRaises(ValidationError) as context:
            AppointmentService.create_appointment(
                self.consultant_profile.id,
                self.patient_user,
                data
            )
        
        self.assertIn('past', str(context.exception))

    def test_create_appointment_with_conflicting_slot(self):
        """Test creating appointment when time slot is already booked"""
        scheduled_date = date.today() + timedelta(days=1)
        scheduled_time = time(14, 0)
        
        # Create first appointment
        self._create_appointment(
            consultant_profile=self.consultant_profile,
            status='confirmed',
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time
        )
        
        # Try to create conflicting appointment
        data = {
            'scheduled_date': scheduled_date,
            'scheduled_time': scheduled_time,
            'Appointment_type': 'video',
            'duration_minutes': 30,
            'reason_for_visit': 'Test'
        }
        
        with self.assertRaises(ValidationError) as context:
            AppointmentService.create_appointment(
                self.consultant_profile.id,
                self.patient_user,
                data
            )
        
        self.assertIn('already booked', str(context.exception))

    def test_update_appointment_success(self):
        """Test updating an appointment"""
        appointment = self._create_appointment(self.consultant_profile)
        
        update_data = {'reason_for_visit': 'Updated reason'}
        
        updated_appointment = AppointmentService.update_appointment(
            appointment, update_data, self.consultant_user
        )
        
        self.assertEqual(updated_appointment.reason_for_visit, 'Updated reason')

    def test_update_completed_appointment_fails(self):
        """Test that updating a completed appointment fails"""
        appointment = self._create_appointment(
            self.consultant_profile,
            status='completed'
        )
        
        with self.assertRaises(ValidationError) as context:
            AppointmentService.update_appointment(
                appointment, {'reason_for_visit': 'New'}, self.consultant_user
            )
        
        self.assertIn('completed', str(context.exception))

    def test_cancel_appointment_success(self):
        """Test cancelling an appointment"""
        appointment = self._create_appointment(self.consultant_profile)
        
        cancelled = AppointmentService.cancel_appointment(
            appointment, self.consultant_user, 'Scheduling conflict'
        )
        
        self.assertEqual(cancelled.status, 'cancelled')

    def test_confirm_appointment_success(self):
        """Test confirming a pending appointment"""
        appointment = self._create_appointment(
            self.consultant_profile,
            status='pending'
        )
        
        confirmed = AppointmentService.confirm_appointment(appointment)
        
        self.assertEqual(confirmed.status, 'confirmed')

    def test_get_consultant_appointments(self):
        """Test filtering consultant appointments"""
        consultant2_user = self._create_user(
            email='consultant2@test.com',
            first_name='Dr',
            last_name='Jones',
            role='consultant'
        )
        consultant2_profile = self._create_consultant_profile(consultant2_user)
        
        # Create appointments
        appt1 = self._create_appointment(self.consultant_profile)
        appt2 = self._create_appointment(self.consultant_profile)
        appt3 = self._create_appointment(consultant2_profile)
        
        appointments = AppointmentService.get_consultant_appointments(
            self.consultant_profile
        )
        
        self.assertEqual(len(list(appointments)), 2)
        self.assertIn(appt1, appointments)
        self.assertNotIn(appt3, appointments)

    def test_get_consultant_appointments_by_status(self):
        """Test filtering appointments by status"""
        self._create_appointment(self.consultant_profile, status='pending')
        self._create_appointment(self.consultant_profile, status='confirmed')
        self._create_appointment(self.consultant_profile, status='pending')
        
        appointments = AppointmentService.get_consultant_appointments(
            self.consultant_profile,
            status='pending'
        )
        
        for appt in appointments:
            self.assertEqual(appt.status, 'pending')


class CallSessionServiceTests(ConsultationTestBase):
    """Test CallSessionService business logic"""

    def test_create_call_session_for_appointment(self):
        """Test creating a call session for an appointment"""
        consultant_profile = self._create_consultant_profile(self.consultant_user)
        appointment = self._create_appointment(consultant_profile)
        
        call_session = CallSessionService.create_call_session(appointment)
        
        self.assertIsNotNone(call_session.id)
        self.assertEqual(call_session.consultant, self.consultant_user)
        self.assertEqual(call_session.patient, self.patient_user)
        self.assertEqual(call_session.status, 'scheduled')

    def test_create_call_session_returns_existing(self):
        """Test that creating call_session twice returns the same session"""
        consultant_profile = self._create_consultant_profile(self.consultant_user)
        appointment = self._create_appointment(consultant_profile)
        
        session1 = CallSessionService.create_call_session(appointment)
        session2 = CallSessionService.create_call_session(appointment)
        
        self.assertEqual(session1.id, session2.id)


#  SERIALIZER  UNIT TESTS 

class CallSessionSerializerTests(ConsultationTestBase):
    """Test CallSessionSerializer"""

    def test_callsession_serializer_valid_data(self):
        """Test serializing valid call session"""
        call_session = self._create_call_session()
        serializer = CallSessionSerializer(call_session)
        
        data = serializer.data
        self.assertIn('id', data)
        self.assertIn('consultant_name', data)
        self.assertIn('status', data)

    def test_callsession_serializer_consultation_fee(self):
        """Test that consultation fee is converted to float"""
        call_session = self._create_call_session()
        call_session.consultation_fee = 50.00
        call_session.save()
        
        serializer = CallSessionSerializer(call_session)
        
        self.assertIsInstance(serializer.data['consultation_fee'], float)


class CallInitiateRequestSerializerTests(ConsultationTestBase):
    """Test CallInitiateRequestSerializer"""

    def test_valid_call_initiate_request(self):
        """Test valid call initiation request"""
        data = {
            'consultant_id': str(self.consultant_user.id),
            'call_type': 'video'
        }
        
        serializer = CallInitiateRequestSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_invalid_call_type(self):
        """Test invalid call type"""
        data = {
            'consultant_id': str(self.consultant_user.id),
            'call_type': 'invalid_type'
        }
        
        serializer = CallInitiateRequestSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_missing_consultant_id(self):
        """Test missing consultant_id"""
        data = {
            'call_type': 'video'
        }
        
        serializer = CallInitiateRequestSerializer(data=data)
        self.assertFalse(serializer.is_valid())


# Define unit test for api endpoints

class ConsultantAppointmentAPITests(APITestCase):
    """Test API views for consultant appointments"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        
        # Create users
        self.consultant_user = User.objects.create_user(
            email='consultant@test.com',
            password='testpass123',
            first_name='Dr',
            last_name='Smith',
            role='consultant'
        )
        
        self.patient_user = User.objects.create_user(
            email='patient@test.com',
            password='testpass123',
            first_name='John',
            last_name='Doe',
            role='patient'
        )
        
        from consultants.models import Speciality
        spec, _ = Speciality.objects.get_or_create(name='General Practice')
        self.consultant_profile = ConsultantProfile.objects.create(
            user=self.consultant_user,
            speciality=spec,
            is_verified=True,
            is_available=True
        )

    def test_list_appointments_requires_authentication(self):
        """Test that listing appointments requires authentication"""
        response = self.client.get('/api/consultations/appointments/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_appointments_requires_consultant_role(self):
        """Test that listing appointments requires consultant role"""
        self.client.force_authenticate(user=self.patient_user)
        response = self.client.get('/api/consultations/appointments/')
        # Should return 403 Forbidden or 404 depending on permission implementation
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_list_appointments_as_consultant(self):
        """Test listing appointments as consultant"""
        # Create an appointment
        appointment = Appointment.objects.create(
            consultant=self.consultant_profile,
            patient=self.patient_user,
            Appointment_type='video',
            status='pending',
            scheduled_date=date.today() + timedelta(days=1),
            scheduled_time=time(14, 0),
            duration_minutes=30,
            reason_for_visit='Test consultation'
        )
        
        self.client.force_authenticate(user=self.consultant_user)
        response = self.client.get('/api/consultations/appointments/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# EDGE CASE AND INTEGRATION TESTS 

class ConsultationEdgeCasesTests(ConsultationTestBase):
    """Test edge cases and integration scenarios"""

    def test_callsession_with_null_started_time(self):
        """Test ending call without tracking started time"""
        call_session = self._create_call_session()
        
        call_session.end_call()
        call_session.refresh_from_db()
        
        self.assertEqual(call_session.status, 'completed')
        self.assertEqual(call_session.duration_minutes, 0)

    def test_multiple_appointments_same_consultant_different_times(self):
        """Test creating multiple appointments for same consultant"""
        consultant_profile = self._create_consultant_profile(self.consultant_user)
        
        data1 = {
            'scheduled_date': date.today() + timedelta(days=1),
            'scheduled_time': time(10, 0),
            'Appointment_type': 'video',
            'duration_minutes': 30,
            'reason_for_visit': 'Test 1'
        }
        
        data2 = {
            'scheduled_date': date.today() + timedelta(days=1),
            'scheduled_time': time(14, 0),
            'Appointment_type': 'video',
            'duration_minutes': 30,
            'reason_for_visit': 'Test 2'
        }
        
        appt1 = AppointmentService.create_appointment(
            consultant_profile.id, self.patient_user, data1
        )
        appt2 = AppointmentService.create_appointment(
            consultant_profile.id, self.patient_user, data2
        )
        
        self.assertNotEqual(appt1.id, appt2.id)
        self.assertEqual(appt1.scheduled_time, time(10, 0))
        self.assertEqual(appt2.scheduled_time, time(14, 0))

    def test_prescription_after_completed_call(self):
        """Test creating prescription after call is completed"""
        call_session = self._create_call_session()
        call_session.start_call()
        call_session.end_call()
        
        prescription = Prescription.objects.create(
            call_seesion=call_session,
            consultant=self.consultant_user,
            patient=self.patient_user,
            medications=[{'name': 'Drug', 'dosage': '500mg'}],
            instructions='Take daily',
            status='active',
            valid_until=timezone.now() + timedelta(days=30)
        )
        
        self.assertEqual(prescription.call_seesion.status, 'completed')
        self.assertIsNotNone(prescription.id)

    def test_webrtc_stats_incremental_updates(self):
        """Test incrementally updating WebRTC stats"""
        call_session = self._create_call_session()
        
        call_session.update_webrtc_stats({'bandwidth': '2.5Mbps'})
        call_session.update_webrtc_stats({'bitrate': '1000kbps'})
        call_session.refresh_from_db()
        
        self.assertEqual(call_session.webrtc_stats['bandwidth'], '2.5Mbps')
        self.assertEqual(call_session.webrtc_stats['bitrate'], '1000kbps')
