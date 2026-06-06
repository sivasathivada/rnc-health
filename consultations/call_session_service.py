"""
Enterprise call session management service.
Handles call lifecycle, state management, and business logic.
"""

import logging
import uuid
from typing import Dict, Optional, Tuple
from datetime import timedelta, datetime
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import CallSession, Appointment
from .notification_service import NotificationService, NotificationPriority
from consultants.models import ConsultantProfile 


logger = logging.getLogger(__name__)
User = get_user_model()


class CallSessionService:
    """
    Enterprise service for managing video/audio call sessions.
    Handles the complete lifecycle of calls with proper error handling.
    """
    
    # Call state machine
    VALID_STATE_TRANSITIONS = {
        'scheduled': ['initiated', 'cancelled'],
        'initiated': ['ongoing', 'no_show', 'cancelled'],
        'ongoing': ['completed', 'cancelled'],
        'completed': [],
        'cancelled': [],
        'no_show': [],
    }
    
    # Call duration limits (in minutes)
    MAX_CALL_DURATION = 120
    MIN_CALL_DURATION = 1
    
    @staticmethod
    def create_call_session(
        appointment: Optional[Appointment] = None,
        consultant_id: int = None,
        patient_id: int = None,
        call_type: str = 'video',
        scheduled_at: Optional[datetime] = None,
        consultation_fee: float = 0.00
    ) -> Tuple[CallSession, Optional[str]]:
        """
        Create a new call session.
        
        Args:
            appointment: Related appointment object
            consultant_id: Consultant user ID
            patient_id: Patient user ID
            call_type: 'video' or 'audio'
            scheduled_at: Scheduled call time
            consultation_fee: Fee for consultation
            
        Returns:
            Tuple[CallSession, Optional[str]]: (call_session, error_message)
        """
        try:
            # Validate inputs
            if not appointment and (not consultant_id or not patient_id):
                return None, "Either appointment or consultant_id + patient_id required"
            
            if call_type not in ['video', 'audio']:
                return None, "Invalid call_type. Must be 'video' or 'audio'"
            
            # Get users
            if appointment:
                consultant_id = appointment.consultant.user_id
                patient_id = appointment.patient_id
                call_type = appointment.appointment_type or 'video'
                scheduled_at = appointment.scheduled_datetime
                consultation_fee = appointment.consultation_fee
            
            try:
                consultant = User.objects.get(id=consultant_id, role='consultant')
                patient = User.objects.get(id=patient_id, role='patient')
            except User.DoesNotExist as e:
                return None, f"User not found: {str(e)}"
            
            # Check consultant availability
            try:
                consultant_profile = consultant.consultant_profile
                if not consultant_profile.is_available:
                    return None, "Consultant is not available"
            except:
                pass
            
            # Create session
            with transaction.atomic():
                session_id = f"call_{uuid.uuid4().hex[:16]}"
                
                call_session = CallSession.objects.create(
                    session_id=session_id,
                    consultant=consultant,
                    patient=patient,
                    call_type=call_type,
                    status='scheduled' if scheduled_at else 'initiated',
                    scheduled_at=scheduled_at or timezone.now(),
                    consultation_fee=consultation_fee,
                )
                
                # Cache session for quick access
                cache_key = f"call_session_{session_id}"
                cache.set(cache_key, call_session.id, timeout=3600)
                
                logger.info(
                    f"Call session created: {session_id} | "
                    f"Consultant: {consultant_id} | "
                    f"Patient: {patient_id} | "
                    f"Type: {call_type}"
                )
                
                return call_session, None
        
        except Exception as e:
            logger.error(f"Error creating call session: {str(e)}", exc_info=True)
            return None, f"Failed to create call session: {str(e)}"
    
    @staticmethod
    def initiate_call(
        consultant_id: int,
        patient_id: int,
        call_type: str = 'video'
    ) -> Tuple[Optional[CallSession], Optional[str]]:
        """
        Initiate an immediate call (not scheduled).
        
        Args:
            consultant_id: Consultant user ID
            patient_id: Patient user ID
            call_type: 'video' or 'audio'
            
        Returns:
            Tuple[CallSession, Optional[str]]: (call_session, error)
        """
        try:
            # Check if consultant is online
            try:
                consultant = User.objects.select_related('consultant_profile').get(
                    id=consultant_id,
                    role='consultant'
                )
                
                if not consultant.consultant_profile.is_available:
                    return None, "Consultant is currently offline"
            except User.DoesNotExist:
                return None, "Consultant not found"
            
            try:
                patient = User.objects.get(id=patient_id, role='patient')
            except User.DoesNotExist:
                return None, "Patient not found"
            
            # Check for ongoing calls between same participants
            ongoing = CallSession.objects.filter(
                consultant=consultant,
                patient=patient,
                status='ongoing'
            ).exists()
            
            if ongoing:
                return None, "You already have an ongoing call with this consultant"
            
            # Create call session
            with transaction.atomic():
                session_id = f"call_{uuid.uuid4().hex[:16]}"
                
                call_session = CallSession.objects.create(
                    session_id=session_id,
                    consultant=consultant,
                    patient=patient,
                    call_type=call_type,
                    status='initiated',
                    scheduled_at=timezone.now(),
                    consultation_fee=consultant.consultant_profile.consultation_fee,
                )
                
                # Send incoming call notification
                NotificationService.send_incoming_call(
                    consultant_id=consultant_id,
                    patient_id=patient_id,
                    patient_name=patient.full_name,
                    session_id=session_id,
                    call_type=call_type,
                )
                
                logger.info(f"Call initiated: {session_id}")
                
                return call_session, None
        
        except Exception as e:
            logger.error(f"Error initiating call: {str(e)}", exc_info=True)
            return None, f"Failed to initiate call: {str(e)}"
    
    @staticmethod
    def start_call(
        session_id: str,
        started_by_id: int = None,
    ) -> Tuple[Optional[CallSession], Optional[str]]:
        """
        Start or accept a call.

        Flow:
        - If status is 'scheduled' AND started_by is the consultant
          → transition to 'initiated' and send incoming_call to the PATIENT (ring them).
        - If status is 'initiated' (patient accepting OR consultant re-joining)
          → transition to 'ongoing' and send call_accepted to both parties.

        Args:
            session_id: Call session ID
            started_by_id: User ID of the person clicking "Start" / "Accept"

        Returns:
            Tuple[CallSession, Optional[str]]: (call_session, error)
        """
        try:
            call_session = CallSession.objects.select_related(
                'consultant', 'patient'
            ).get(session_id=session_id)

            # Already ongoing — idempotent, just return it
            if call_session.status == 'ongoing':
                return call_session, None

            # Validate state transition
            if call_session.status not in ['scheduled', 'initiated']:
                return None, f"Cannot start call in '{call_session.status}' status"

            with transaction.atomic():
                # ── CONSULTANT starts the call: scheduled → initiated ──
                # Ring the patient so they see the incoming-call overlay
                if (
                    call_session.status == 'scheduled'
                    and started_by_id is not None
                    and started_by_id == call_session.consultant_id
                ):
                    # Check scheduled time: only allow starting call up to 5 minutes before scheduled time
                    if call_session.scheduled_at:
                        now = timezone.now()
                        if now < call_session.scheduled_at - timedelta(minutes=5):
                            return None, "You can only start the call up to 5 minutes before the scheduled time."

                    call_session.status = 'initiated'
                    call_session.save(update_fields=['status'])

                    # Send incoming_call notification to PATIENT via WebSocket
                    consultant_name = getattr(
                        call_session.consultant, 'full_name', str(call_session.consultant)
                    )
                    try:
                        from channels.layers import get_channel_layer
                        from asgiref.sync import async_to_sync
                        channel_layer = get_channel_layer()
                        if channel_layer:
                            async_to_sync(channel_layer.group_send)(
                                f"user_{call_session.patient_id}",
                                {
                                    "type": "notification_message",
                                    "notification_type": "incoming_call",
                                    "data": {
                                        "session_id": session_id,
                                        "caller_name": consultant_name,
                                        "caller_role": "consultant",
                                        "call_type": call_session.call_type,
                                        "timeout_seconds": 45,
                                    },
                                }
                            )
                    except Exception as ws_err:
                        logger.warning(
                            f"Could not send incoming_call WS notification to patient: {ws_err}"
                        )

                    # Schedule no-answer timeout
                    try:
                        from .tasks import handle_call_no_answer
                        handle_call_no_answer.apply_async(args=[session_id], countdown=45)
                    except Exception as e:
                        logger.warning(f"Could not schedule no-answer task: {e}")

                    logger.info(
                        f"Consultant started call {session_id} — patient notified (ringing)"
                    )
                    return call_session, None

                # ── PATIENT accepts (initiated → ongoing) ──
                call_session.status = 'ongoing'
                call_session.started_at = timezone.now()
                call_session.save(update_fields=['status', 'started_at'])

                # Notify both parties the call is live
                NotificationService.send_call_accepted(
                    patient_id=call_session.patient_id,
                    consultant_id=call_session.consultant_id,
                    session_id=session_id,
                )

                # Schedule call-duration timeout
                try:
                    from .tasks import handle_call_timeout
                    handle_call_timeout.apply_async(
                        args=[session_id],
                        countdown=CallSessionService.MAX_CALL_DURATION * 60
                    )
                except Exception as e:
                    logger.warning(
                        f"Could not schedule call timeout task. "
                        f"Ensure Celery is running. Error: {e}"
                    )

                logger.info(f"Call is now ongoing: {session_id}")
                return call_session, None

        except CallSession.DoesNotExist:
            return None, "Call session not found"
        except Exception as e:
            logger.error(f"Error starting call: {str(e)}", exc_info=True)
            return None, f"Failed to start call: {str(e)}"
    
    @staticmethod
    def end_call(
        session_id: str,
        ended_by_id: int,
        notes: str = ""
    ) -> Tuple[Optional[CallSession], Optional[str]]:
        """
        End an ongoing call.
        
        Args:
            session_id: Call session ID
            ended_by_id: User ID of person ending call
            notes: Optional notes from consultant
            
        Returns:
            Tuple[CallSession, Optional[str]]: (call_session, error)
        """
        try:
            call_session = CallSession.objects.select_related(
                'consultant', 'patient'
            ).get(session_id=session_id)
            
            # Validate authorization
            if ended_by_id not in [call_session.consultant_id, call_session.patient_id]:
                return None, "Unauthorized to end this call"
            
            if call_session.status != 'ongoing':
                return None, f"Call is not ongoing (status: {call_session.status})"
            
            with transaction.atomic():
                call_session.end_call()
                
                if notes and ended_by_id == call_session.consultant_id:
                    call_session.consultant_notes = notes
                    call_session.save(update_fields=['consultant_notes'])
                
                # Send notifications
                NotificationService.send_call_ended(
                    patient_id=call_session.patient_id,
                    consultant_id=call_session.consultant_id,
                    session_id=session_id,
                    duration_minutes=call_session.duration_minutes,
                )
                
                # Generate analytics
                try:
                    from .tasks import generate_call_analytics
                    generate_call_analytics.delay(session_id)
                except Exception as e:
                    logger.warning(f"Could not schedule analytics: {str(e)}")
                
                logger.info(
                    f"Call ended: {session_id} | "
                    f"Duration: {call_session.duration_minutes}m | "
                    f"Ended by: {ended_by_id}"
                )
                
                return call_session, None
        
        except CallSession.DoesNotExist:
            return None, "Call session not found"
        except Exception as e:
            logger.error(f"Error ending call: {str(e)}", exc_info=True)
            return None, f"Failed to end call: {str(e)}"
    
    @staticmethod
    def decline_call(
        session_id: str,
        declined_by_id: int,
        reason: str = "user_declined"
    ) -> Tuple[Optional[CallSession], Optional[str]]:
        """
        Decline an incoming call.
        
        Args:
            session_id: Call session ID
            declined_by_id: User ID declining call
            reason: Reason for declining
            
        Returns:
            Tuple[CallSession, Optional[str]]: (call_session, error)
        """
        try:
            call_session = CallSession.objects.get(session_id=session_id)
            
            if call_session.status not in ['initiated', 'scheduled']:
                return None, f"Cannot decline call in {call_session.status} status"
            
            # Validate authorization
            if declined_by_id not in [call_session.consultant_id, call_session.patient_id]:
                return None, "Unauthorized to decline this call"
            
            with transaction.atomic():
                call_session.status = 'cancelled'
                call_session.save(update_fields=['status'])
                
                # Notify both parties
                NotificationService.send_call_declined(
                    patient_id=call_session.patient_id,
                    consultant_id=call_session.consultant_id,
                    session_id=session_id,
                    reason=reason,
                )
                
                logger.info(
                    f"Call declined: {session_id} | "
                    f"Declined by: {declined_by_id} | "
                    f"Reason: {reason}"
                )
                
                return call_session, None
        
        except CallSession.DoesNotExist:
            return None, "Call session not found"
        except Exception as e:
            logger.error(f"Error declining call: {str(e)}", exc_info=True)
            return None, f"Failed to decline call: {str(e)}"
    
    @staticmethod
    def record_ice_candidate(session_id: str) -> Tuple[bool, Optional[str]]:
        """Record ICE candidate exchange"""
        try:
            call_session = CallSession.objects.get(session_id=session_id)
            call_session.add_ice_candidate()
            return True, None
        except CallSession.DoesNotExist:
            return False, "Call session not found"
        except Exception as e:
            logger.error(f"Error recording ICE candidate: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def record_offer_exchanged(session_id: str) -> Tuple[bool, Optional[str]]:
        """Record WebRTC offer exchange"""
        try:
            call_session = CallSession.objects.get(session_id=session_id)
            call_session.record_offer_exchanged()
            return True, None
        except CallSession.DoesNotExist:
            return False, "Call session not found"
        except Exception as e:
            logger.error(f"Error recording offer: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def record_answer_exchanged(session_id: str) -> Tuple[bool, Optional[str]]:
        """Record WebRTC answer exchange"""
        try:
            call_session = CallSession.objects.get(session_id=session_id)
            call_session.record_answer_exchanged()
            return True, None
        except CallSession.DoesNotExist:
            return False, "Call session not found"
        except Exception as e:
            logger.error(f"Error recording answer: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def record_connection_established(
        session_id: str,
        connection_type: str = 'unknown'
    ) -> Tuple[bool, Optional[str]]:
        """Record WebRTC connection established"""
        try:
            call_session = CallSession.objects.get(session_id=session_id)
            call_session.connection_type = connection_type
            call_session.record_connection_established()
            
            # Send notification
            NotificationService.send_connection_established(
                patient_id=call_session.patient_id,
                consultant_id=call_session.consultant_id,
                session_id=session_id,
                connection_type=connection_type,
            )
            
            return True, None
        except CallSession.DoesNotExist:
            return False, "Call session not found"
        except Exception as e:
            logger.error(f"Error recording connection established: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def record_reconnection_attempt(session_id: str) -> Tuple[bool, Optional[str]]:
        """Record reconnection attempt"""
        try:
            call_session = CallSession.objects.get(session_id=session_id)
            call_session.record_reconnection_attempt()
            
            # Alert if too many reconnections
            if call_session.reconnection_attempts > 3:
                try:
                    from .tasks import send_reconnection_alert
                    send_reconnection_alert.delay(session_id, call_session.reconnection_attempts)
                except Exception as e:
                    logger.warning(f"Could not send reconnection alert: {str(e)}")
            
            return True, None
        except CallSession.DoesNotExist:
            return False, "Call session not found"
        except Exception as e:
            logger.error(f"Error recording reconnection: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def update_connection_quality(
        session_id: str,
        quality: str,
        stats: Dict = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Update connection quality and stats.
        
        Args:
            session_id: Call session ID
            quality: Quality level (excellent, good, fair, poor, failed)
            stats: Connection statistics (bandwidth, latency, packet_loss, etc.)
            
        Returns:
            Tuple[bool, Optional[str]]: (success, error)
        """
        try:
            if quality not in ['excellent', 'good', 'fair', 'poor', 'failed']:
                return False, f"Invalid quality level: {quality}"
            
            call_session = CallSession.objects.get(session_id=session_id)
            
            call_session.connection_quality = quality
            if stats:
                call_session.update_webrtc_stats(stats)
            else:
                call_session.save(update_fields=['connection_quality'])
            
            # Alert on poor connection
            if quality in ['poor', 'failed']:
                try:
                    from .tasks import send_connection_quality_alert
                    send_connection_quality_alert.delay(session_id, quality, stats or {})
                except Exception as e:
                    logger.warning(f"Could not send quality alert: {str(e)}")
            
            return True, None
        except CallSession.DoesNotExist:
            return False, "Call session not found"
        except Exception as e:
            logger.error(f"Error updating connection quality: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def get_call_session(session_id: str) -> Optional[CallSession]:
        """Get call session by ID"""
        try:
            return CallSession.objects.select_related(
                'consultant', 'patient'
            ).get(session_id=session_id)
        except CallSession.DoesNotExist:
            logger.warning(f"Call session not found: {session_id}")
            return None
    
    @staticmethod
    def get_user_call_history(
        user_id: int,
        role: str = None,
        status: str = None,
        limit: int = 50
    ):
        """
        Get call history for a user.
        
        Args:
            user_id: User ID
            role: 'consultant' or 'patient'
            status: Optional status filter
            limit: Max results
            
        Returns:
            QuerySet of CallSession objects
        """
        try:
           
            if role == 'consultant':
                queryset = CallSession.objects.filter(consultant_id=user_id)
            elif role == 'patient':
                queryset = CallSession.objects.filter(patient_id=user_id)
            else:

                queryset = CallSession.objects.filter(
                    models.Q(consultant_id=user_id) | models.Q(patient_id=user_id)
                )
            
            if status:
                queryset = queryset.filter(status=status)
            
            return queryset.select_related('consultant', 'patient').order_by(
                '-created_at'
            )[:limit]
        
        except Exception as e:
            logger.error(f"Error getting call history: {str(e)}")
            return CallSession.objects.none()


# Import Q for queryset operations

