from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from .models import Appointment, CallSession, Prescription, AppointmentSlot
from consultants.models import ConsultantProfile
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import uuid
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
# NOTE: Do NOT import from videoaudio_views here — circular import
from .call_session_service import CallSessionService
from .notification_service import NotificationService
import logging

User = get_user_model()

logger = logging.getLogger(__name__)


# ─── Local WebSocket helper (replaces the old local NotificationService class) ──
# Uses the REAL NotificationService from notification_service.py.
# This avoids the naming clash that was shadowing the full implementation.

def _ws_send(user_id, notification_type, data):
    """Send a WebSocket notification to a single user (sync-safe)."""
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.error("Channel layer not available")
            return
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            {
                "type": "notification_message",
                "notification_type": notification_type,
                "data": data,
            }
        )
    except Exception as e:
        logger.error(f"_ws_send error for user {user_id}: {e}")


def _ws_send_appointment_notification(appointment, action):
    """Send appointment update notification to both patient and consultant."""
    # Notify patient
    _ws_send(
        appointment.patient.id,
        "appointment_update",
        {
            "appointment_id": str(appointment.id),
            "action": action,
            "consultant_name": appointment.consultant.user.full_name,
            "scheduled_datetime": appointment.scheduled_datetime.isoformat(),
        }
    )
    # Notify consultant
    _ws_send(
        appointment.consultant.user.id,
        "appointment_update",
        {
            "appointment_id": str(appointment.id),
            "action": action,
            "patient_name": appointment.patient.full_name,
            "scheduled_datetime": appointment.scheduled_datetime.isoformat(),
        }
    )


def generate_appointment_slots_from_availability(consultant_profile, days_ahead=60):
    """
    Generate actual AppointmentSlot entries from ConsultantAvailability (recurring weekly slots).
    
    This bridges the gap between:
    - ConsultantAvailability (weekly recurring pattern with day_of_week)
    - AppointmentSlot (actual calendar dates)
    
    Args:
        consultant_profile: ConsultantProfile instance
        days_ahead: Generate slots for next N days (default: 60)
    
    Returns:
        int: Number of slots created
    """
    try:
        # Get consultant's weekly availability
        availabilities = consultant_profile.availability_slots.filter(is_active=True)
        
        if not availabilities.exists():
            logger.warning(f"No active availability slots found for consultant {consultant_profile.id}")
            return 0
        
        # Generate dates for the next N days
        today = timezone.now().date()
        start_date = today
        end_date = today + timedelta(days=days_ahead)
        
        slots_created = 0
        slots_to_create = []
        
        # Iterate through each day
        current_date = start_date
        while current_date <= end_date:
            day_of_week = current_date.weekday()  # 0=Monday, 6=Sunday
            
            # Find availability for this day of week
            for availability in availabilities:
                if availability.day_of_week == day_of_week:
                    # Check if slot already exists for this date/time
                    exists = AppointmentSlot.objects.filter(
                        consultant=consultant_profile,
                        date=current_date,
                        start_time=availability.start_time,
                        is_available=True,
                        is_blocked=False
                    ).exists()
                    
                    if not exists:
                        slot = AppointmentSlot(
                            consultant=consultant_profile,
                            date=current_date,
                            start_time=availability.start_time,
                            end_time=availability.end_time,
                            is_available=True,
                            is_blocked=False
                        )
                        slots_to_create.append(slot)
            
            current_date += timedelta(days=1)
        
        # Bulk create new slots
        if slots_to_create:
            AppointmentSlot.objects.bulk_create(slots_to_create, ignore_conflicts=True)
            slots_created = len(slots_to_create)
            logger.info(f"Generated {slots_created} appointment slots for consultant {consultant_profile.id}")
        
        return slots_created
        
    except Exception as e:
        logger.error(f"Error generating appointment slots: {str(e)}", exc_info=True)
        return 0


class AppointmentService:
    """Business logic for appointment management"""

    @staticmethod
    def create_appointment(consultant_id, patient, data):
        """Create a new appointment"""
        try:
            consultant = ConsultantProfile.objects.get(
                id=consultant_id,
                is_verified=True,
                is_available=True
            )
        except ConsultantProfile.DoesNotExist:
            raise ValidationError("Consultant not found or unavailable")

        scheduled_datetime = timezone.datetime.combine(
            data['scheduled_date'],
            data['scheduled_time'],
            tzinfo=timezone.get_current_timezone()
        )

        if scheduled_datetime < timezone.now():
            raise ValidationError("Cannot schedule appointments in the past")

        # Check for conflicts
        conflicts = Appointment.objects.filter(
            consultant=consultant,
            scheduled_date=data['scheduled_date'],
            scheduled_time=data['scheduled_time'],
            status__in=['pending', 'confirmed']
        )

        if conflicts.exists():
            raise ValidationError("Time slot is already booked")

        with transaction.atomic():
            appointment = Appointment.objects.create(
                consultant=consultant,
                patient=patient,
                **data
            )

            # Send notification
            _ws_send_appointment_notification(appointment, "created")

            return appointment

    @staticmethod
    def update_appointment(appointment, data, updated_by):
        """Update an existing appointment"""
        if appointment.status in ['completed', 'cancelled']:
            raise ValidationError(f"Cannot update {appointment.status} appointments")

        with transaction.atomic():
            for field, value in data.items():
                setattr(appointment, field, value)
            appointment.save()

            # Send notification
            _ws_send_appointment_notification(appointment, "updated")

            return appointment

    @staticmethod
    def cancel_appointment(appointment, cancelled_by, reason=""):
        """Cancel an appointment"""
        with transaction.atomic():
            appointment.cancel(cancelled_by, reason)

            # Send notification
            _ws_send_appointment_notification(appointment, "cancelled")

            return appointment

    @staticmethod
    def confirm_appointment(appointment):
        """Confirm a pending appointment"""
        with transaction.atomic():
            appointment.confirm()

            # Send notification
            _ws_send_appointment_notification(appointment, "confirmed")

            return appointment

    @staticmethod
    def get_consultant_appointments(consultant, status=None, date_from=None, date_to=None):
        """Get appointments for a consultant with optional filters"""
        queryset = Appointment.objects.filter(consultant=consultant)

        if status:
            queryset = queryset.filter(status=status)

        if date_from:
            queryset = queryset.filter(scheduled_date__gte=date_from)

        if date_to:
            queryset = queryset.filter(scheduled_date__lte=date_to)

        return queryset.order_by('scheduled_date', 'scheduled_time')

    @staticmethod
    def get_available_slots(consultant, date):
        """Get available time slots for a consultant on a specific date"""
        # Check if any slots exist for this consultant on this date
        exists = AppointmentSlot.objects.filter(
            consultant=consultant,
            date=date
        ).exists()
        
        if not exists:
            # Generate slots for this specific date on the fly from ConsultantAvailability weekly slots
            day_of_week = date.weekday()  # 0=Monday, 6=Sunday
            availabilities = consultant.availability_slots.filter(day_of_week=day_of_week, is_active=True)
            slots_to_create = []
            for availability in availabilities:
                slot = AppointmentSlot(
                    consultant=consultant,
                    date=date,
                    start_time=availability.start_time,
                    end_time=availability.end_time,
                    is_available=True,
                    is_blocked=False
                )
                slots_to_create.append(slot)
            
            if slots_to_create:
                AppointmentSlot.objects.bulk_create(slots_to_create, ignore_conflicts=True)
                logger.info(f"Generated {len(slots_to_create)} slots on the fly for consultant {consultant.id} on date {date}")

        # Get all unblocked, available slots for the consultant on the specified date
        all_slots = AppointmentSlot.objects.filter(
            consultant=consultant,
            date=date,
            is_available=True,
            is_blocked=False
        ).order_by('start_time')
        
        # Filter out slots that have confirmed/pending appointments
        booked_times = Appointment.objects.filter(
            consultant=consultant,
            scheduled_date=date,
            status__in=['pending', 'confirmed']
        ).values_list('scheduled_time', flat=True)
        
        # Return only slots that don't have appointments at that time
        available = all_slots.exclude(start_time__in=booked_times)
        
        logger.debug(f"Total slots: {all_slots.count()}, Booked times: {len(list(booked_times))}, Available: {available.count()}")
        return available


class PrescriptionService:
    """Business logic for prescription management"""

    @staticmethod
    def create_prescription(call_session, consultant, data):
        """Create a prescription for a call session"""
        if call_session.consultant != consultant:
            raise ValidationError("Unauthorized to create prescription for this session")

        if call_session.status != 'completed':
            raise ValidationError("Can only create prescriptions for completed calls")

        with transaction.atomic():
            prescription = Prescription.objects.create(
                call_session=call_session,
                consultant=consultant,
                patient=call_session.patient,
                **data
            )

            # Send notification
            _ws_send(
                call_session.patient.id,
                "prescription_created",
                {
                    "prescription_id": str(prescription.id),
                    "session_id": call_session.session_id,
                }
            )

            return prescription

    @staticmethod
    def update_prescription(prescription, consultant, data):
        """Update a prescription"""
        if prescription.consultant != consultant:
            raise ValidationError("Unauthorized to update this prescription")

        with transaction.atomic():
            for field, value in data.items():
                setattr(prescription, field, value)
            prescription.save()

            # Send notification
            _ws_send(
                prescription.patient.id,
                "prescription_updated",
                {"prescription_id": str(prescription.id)}
            )

            return prescription

    @staticmethod
    def get_consultant_prescriptions(consultant, status=None):
        """Get prescriptions issued by a consultant"""
        queryset = Prescription.objects.filter(consultant=consultant)

        if status:
            queryset = queryset.filter(status=status)

        return queryset.order_by('-created_at')
    



# ==================== ENTERPRISE-GRADE CONSULTATION SERVICE ====================

class ConsultationService:
    """
    Enterprise service for real-time audio/video consultations.
    Manages call lifecycle, notifications, and WebRTC connections.
    """
    
    @staticmethod
    def initiate_call(
        consultant_id: int,
        patient_user,
        call_type: str = 'video',
        appointment_id: Optional[str] = None,
        initiated_by_role: str = 'patient'
    ) -> Tuple[Optional[CallSession], Optional[str]]:
        """
        Initiate an immediate call from patient to consultant.
        
        Args:
            consultant_id: ID of consultant to call
            patient_user: Patient user object
            call_type: 'video' or 'audio'
            appointment_id: Optional related appointment ID
            initiated_by_role: Role of the user initiating the call
            
        Returns:
            Tuple[CallSession, Optional[str]]: (call_session, error)
        """
        try:
            # Validate consultant
            try:
                consultant_profile = ConsultantProfile.objects.select_related('user').get(
                    id=consultant_id,
                    user__role='consultant',
                    user__is_active=True,
                    is_verified=True
                )
            except ConsultantProfile.DoesNotExist:
                return None, "Consultant not found or not verified"
            
            if not consultant_profile.is_available:
                return None, "Consultant is currently offline"
            
            # Resolve patient_user if passed as ID (consultant-initiated calls)
            if isinstance(patient_user, (int, str, uuid.UUID)):
                try:
                    patient_user_obj = User.objects.get(id=patient_user, role='patient')
                except User.DoesNotExist:
                    return None, "Patient not found"
            else:
                patient_user_obj = patient_user
            
            # Use CallSessionService for creation
            call_session, error = CallSessionService.create_call_session(
                consultant_id=consultant_profile.user_id,
                patient_id=patient_user_obj.id,
                call_type=call_type,
                consultation_fee=consultant_profile.consultation_fee
            )
            
            if not call_session:
                return None, error
            
            # Send incoming call notification via the real NotificationService
            if initiated_by_role == 'consultant':
                NotificationService.send_incoming_call(
                    consultant_id=consultant_profile.user_id,
                    patient_id=patient_user_obj.id,
                    patient_name=getattr(patient_user_obj, 'full_name', str(patient_user_obj)),
                    session_id=call_session.session_id,
                    call_type=call_type,
                    notify_user_id=patient_user_obj.id,
                    caller_name=consultant_profile.user.full_name,
                )
            else:
                NotificationService.send_incoming_call(
                    consultant_id=consultant_profile.user_id,
                    patient_id=patient_user_obj.id,
                    patient_name=getattr(patient_user_obj, 'full_name', str(patient_user_obj)),
                    session_id=call_session.session_id,
                    call_type=call_type,
                    notify_user_id=consultant_profile.user_id,
                    caller_name=getattr(patient_user_obj, 'full_name', str(patient_user_obj)),
                )

            logger.info(
                f"Call initiated: {call_session.session_id} | "
                f"Patient: {patient_user_obj.id} | "
                f"Consultant: {consultant_profile.user_id}"
            )

            return call_session, None
        
        except Exception as e:
            logger.error(f"Error initiating call: {str(e)}", exc_info=True)
            return None, f"Failed to initiate call: {str(e)}"
    
    @staticmethod
    def start_call(
        session_id: str,
        user
    ) -> Tuple[Optional[CallSession], Optional[str]]:
        """
        Start a call (accept incoming call or start scheduled call).
        
        Args:
            session_id: Session ID
            user: User accepting/starting the call
            
        Returns:
            Tuple[CallSession, Optional[str]]: (call_session, error)
        """
        try:
            call_session = CallSession.objects.get(session_id=session_id)
            
            # Verify authorization
            if user.id not in [call_session.consultant_id, call_session.patient_id]:
                return None, "Unauthorized: Not part of this call"
            
            # Pass the caller's ID so CallSessionService knows whether to ring patient or go ongoing
            result_session, error = CallSessionService.start_call(session_id, started_by_id=user.id)
            if not result_session:
                return None, error
            
            return result_session, None
        
        except CallSession.DoesNotExist:
            return None, "Call session not found"
        except Exception as e:
            logger.error(f"Error starting call: {str(e)}", exc_info=True)
            return None, f"Failed to start call: {str(e)}"
    
    @staticmethod
    def end_call(
        session_id: str,
        user,
        consultant_notes: str = "",
        patient_feedback: str = ""
    ) -> Tuple[Optional[CallSession], Optional[str]]:
        """
        End an ongoing call.
        
        Args:
            session_id: Session ID
            user: User ending the call
            consultant_notes: Optional notes from consultant
            patient_feedback: Optional feedback from patient
            
        Returns:
            Tuple[CallSession, Optional[str]]: (call_session, error)
        """
        try:
            call_session = CallSession.objects.get(session_id=session_id)
            
            # Verify authorization
            if user.id not in [call_session.consultant_id, call_session.patient_id]:
                return None, "Unauthorized: Not part of this call"
            
            # Use CallSessionService
            result_session, error = CallSessionService.end_call(
                session_id,
                user.id,
                consultant_notes
            )
            
            if not result_session:
                return None, error
            
            # Store additional feedback
            if user.role == 'patient' and patient_feedback:
                result_session.patient_feedback = patient_feedback
                result_session.save(update_fields=['patient_feedback'])
            
            return result_session, None
        
        except CallSession.DoesNotExist:
            return None, "Call session not found"
        except Exception as e:
            logger.error(f"Error ending call: {str(e)}", exc_info=True)
            return None, f"Failed to end call: {str(e)}"
    
    @staticmethod
    def decline_call(
        session_id: str,
        user,
        reason: str = "user_declined"
    ) -> Tuple[Optional[CallSession], Optional[str]]:
        """
        Decline an incoming call.
        
        Args:
            session_id: Session ID
            user: User declining the call
            reason: Reason for declining
            
        Returns:
            Tuple[CallSession, Optional[str]]: (call_session, error)
        """
        try:
            # Use CallSessionService
            result_session, error = CallSessionService.decline_call(
                session_id,
                user.id,
                reason
            )
            
            return result_session, error
        
        except Exception as e:
            logger.error(f"Error declining call: {str(e)}", exc_info=True)
            return None, f"Failed to decline call: {str(e)}"
    
    @staticmethod
    def get_consultant_call_sessions(
        consultant_profile,
        status: Optional[str] = None,
        limit: int = 50
    ):
        """
        Get call sessions for a consultant.
        
        Args:
            consultant_profile: ConsultantProfile object
            status: Optional status filter
            limit: Maximum results
            
        Returns:
            QuerySet of CallSession objects
        """
        try:
            queryset = CallSession.objects.filter(
                consultant_id=consultant_profile.user_id
            ).select_related('consultant', 'patient')
            
            if status:
                queryset = queryset.filter(status=status)
            
            return queryset.order_by('-created_at')[:limit]
        
        except Exception as e:
            logger.error(f"Error getting call sessions: {str(e)}")
            return CallSession.objects.none()
    
    @staticmethod
    def get_patient_call_sessions(
        patient_user,
        status: Optional[str] = None,
        limit: int = 50
    ):
        """
        Get call sessions for a patient.
        
        Args:
            patient_user: Patient user object
            status: Optional status filter
            limit: Maximum results
            
        Returns:
            QuerySet of CallSession objects
        """
        try:
            queryset = CallSession.objects.filter(
                patient_id=patient_user.id
            ).select_related('consultant', 'patient')
            
            if status:
                queryset = queryset.filter(status=status)
            
            return queryset.order_by('-created_at')[:limit]
        
        except Exception as e:
            logger.error(f"Error getting call sessions: {str(e)}")
            return CallSession.objects.none()
    
    @staticmethod
    def get_call_analytics(session_id: str) -> Dict:
        """
        Get call analytics and metrics.
        
        Args:
            session_id: Session ID
            
        Returns:
            Dict with call analytics
        """
        try:
            call_session = CallSession.objects.get(session_id=session_id)
            
            analytics = {
                'session_id': session_id,
                'duration_minutes': call_session.duration_minutes,
                'connection_quality': call_session.connection_quality,
                'connection_health': call_session.connection_health,
                'reconnection_attempts': call_session.reconnection_attempts,
                'ice_candidates_count': call_session.ice_candidates_count,
                'connection_type': call_session.connection_type,
                'webrtc_stats': call_session.webrtc_stats or {},
            }
            
            return analytics
        
        except CallSession.DoesNotExist:
            logger.warning(f"Call session not found: {session_id}")
            return {}
        except Exception as e:
            logger.error(f"Error getting call analytics: {str(e)}")
            return {}


# Add type hints
from typing import Tuple, Optional, Dict