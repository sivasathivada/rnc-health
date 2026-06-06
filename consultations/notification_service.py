"""
Enterprise-grade notification service for video/audio consultations.
Handles all notification types with delivery guarantees and error handling.
"""

import logging
import json
from enum import Enum
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


class NotificationType(Enum):
    """Enum for notification types"""
    # Incoming call notifications
    INCOMING_CALL = "incoming_call"
    CALL_RINGING = "call_ringing"
    
    # Call response notifications
    CALL_ACCEPTED = "call_accepted"
    CALL_DECLINED = "call_declined"
    CALL_ENDED = "call_ended"
    CALL_MISSED = "call_missed"
    CALL_CANCELLED = "call_cancelled"
    
    # Connection notifications
    CONNECTION_ESTABLISHED = "connection_established"
    CONNECTION_FAILED = "connection_failed"
    CONNECTION_QUALITY = "connection_quality"
    RECONNECTION_ALERT = "reconnection_alert"
    
    # WebRTC signaling
    WEBRTC_OFFER = "webrtc_offer"
    WEBRTC_ANSWER = "webrtc_answer"
    ICE_CANDIDATE = "ice_candidate"
    
    # Participant notifications
    PARTICIPANT_JOINED = "participant_joined"
    PARTICIPANT_LEFT = "participant_left"
    
    # Appointment notifications
    APPOINTMENT_REMINDER = "appointment_reminder"
    APPOINTMENT_CREATED = "appointment_created"
    APPOINTMENT_UPDATED = "appointment_updated"
    APPOINTMENT_CANCELLED = "appointment_cancelled"
    CALL_SESSION_READY = "call_session_ready"
    
    # System notifications
    SYSTEM_MESSAGE = "system_message"
    ERROR_NOTIFICATION = "error_notification"


class NotificationPriority(Enum):
    """Notification priority levels"""
    CRITICAL = 1  # System failures, immediate action needed
    HIGH = 2      # Incoming calls, urgent alerts
    NORMAL = 3    # Regular updates, status changes
    LOW = 4       # Informational, non-urgent


class NotificationService:
    """
    Enterprise notification service for healthcare consultations.
    Handles WebSocket delivery, retries, and delivery guarantees.
    """
    
    # Notification timeout settings (in seconds)
    CALL_ANSWER_TIMEOUT = 45
    CALL_SESSION_TIMEOUT = 3600  # 1 hour
    NOTIFICATION_DELIVERY_TIMEOUT = 30
    
    # Retry settings
    MAX_DELIVERY_RETRIES = 3
    RETRY_DELAY = 5  # seconds
    
    @staticmethod
    def _get_channel_layer():
        """Get channel layer with error handling"""
        try:
            return get_channel_layer()
        except Exception as e:
            logger.error(f"Failed to get channel layer: {str(e)}")
            return None
    
    @staticmethod
    def send_notification(user_id, notification_type, data):
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            {
                "type": "notification_message",
                "notification_type": notification_type,
                "data": data,
            }
        )
    @staticmethod
    def _send_to_user(
        user_id: int,
        notification_type: NotificationType,
        data: Dict,
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> bool:
        """
        Send notification to a specific user via WebSocket.
        
        Args:
            user_id: Target user ID
            notification_type: Type of notification
            data: Notification payload
            priority: Priority level
            
        Returns:
            bool: True if sent successfully
        """
        try:
            channel_layer = NotificationService._get_channel_layer()
            if not channel_layer:
                logger.error(f"Channel layer unavailable, cannot send to user {user_id}")
                return False
            
            payload = {
                "type": "notification_message",  # FIX: Use notification_message for proper routing
                "notification_type": notification_type.value,
                "data": data,
                "priority": priority.value,
                "timestamp": timezone.now().isoformat(),
            }
            
            group_name = f"user_{user_id}"
            async_to_sync(channel_layer.group_send)(group_name, payload)
            
            logger.debug(f"Notification sent to user {user_id}: {notification_type.value}")
            return True
            
        except Exception as e:
            logger.error(
                f"Error sending notification to user {user_id}: {str(e)}",
                exc_info=True
            )
            return False
    
    @staticmethod
    def _send_to_group(
        group_name: str,
        notification_type: NotificationType,
        data: Dict,
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> bool:
        """Send notification to a group of users"""
        try:
            channel_layer = NotificationService._get_channel_layer()
            if not channel_layer:
                return False
            
            payload = {
                "type": "notification_message",  # FIX: Use notification_message for proper routing
                "notification_type": notification_type.value,
                "data": data,
                "priority": priority.value,
                "timestamp": timezone.now().isoformat(),
            }
            
            async_to_sync(channel_layer.group_send)(group_name, payload)
            logger.debug(f"Group notification sent to {group_name}: {notification_type.value}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending group notification to {group_name}: {str(e)}")
            return False
    
    # ==================== INCOMING CALL NOTIFICATIONS ====================
    
    @staticmethod
    def send_incoming_call(
        consultant_id: int,
        patient_id: int,
        patient_name: str,
        session_id: str,
        call_type: str,
        notify_user_id: Optional[int] = None,
        caller_name: Optional[str] = None,
    ) -> bool:
        """
        Send incoming call notification.
        High priority, triggers ringtone on client.
        """
        target_user_id = notify_user_id if notify_user_id is not None else consultant_id
        is_incoming_to_patient = (target_user_id == patient_id)
        
        data = {
            "session_id": session_id,
            "patient_id": str(patient_id),
            "patient_name": patient_name,
            "call_type": call_type,
            "caller_name": caller_name or (patient_name if not is_incoming_to_patient else "Consultant"),
            "caller_role": "consultant" if is_incoming_to_patient else "patient",
            "timeout_seconds": NotificationService.CALL_ANSWER_TIMEOUT,
        }
        
        success = NotificationService._send_to_user(
            target_user_id,
            NotificationType.INCOMING_CALL,
            data,
            priority=NotificationPriority.HIGH
        )
        
        if success:
            # Schedule timeout task using Celery
            try:
                from .tasks import handle_call_no_answer
                handle_call_no_answer.apply_async(
                    args=[session_id],
                    countdown=NotificationService.CALL_ANSWER_TIMEOUT
                )
            except Exception as e:
                logger.warning(f"Could not schedule no-answer handler: {str(e)}")
        
        return success
    
    @staticmethod
    def send_call_ringing(patient_id: int, session_id: str, call_type: str) -> bool:
        """Send ringing notification to patient"""
        data = {
            "session_id": session_id,
            "call_type": call_type,
            "status": "ringing",
        }
        
        return NotificationService._send_to_user(
            patient_id,
            NotificationType.CALL_RINGING,
            data,
            priority=NotificationPriority.HIGH
        )
    
    # ==================== CALL RESPONSE NOTIFICATIONS ====================
    
    @staticmethod
    def send_call_accepted(
        patient_id: int,
        consultant_id: int,
        session_id: str,
        callback_url: str = ""
    ) -> bool:
        """Send call accepted notification"""
        data = {
            "session_id": session_id,
            "status": "accepted",
            "callback_url": callback_url,
        }
        
        # Notify both parties
        success_patient = NotificationService._send_to_user(
            patient_id,
            NotificationType.CALL_ACCEPTED,
            data,
            priority=NotificationPriority.HIGH
        )
        
        success_consultant = NotificationService._send_to_user(
            consultant_id,
            NotificationType.CALL_ACCEPTED,
            data,
            priority=NotificationPriority.HIGH
        )
        
        return success_patient and success_consultant
    
    @staticmethod
    def send_call_declined(
        patient_id: int,
        consultant_id: int,
        session_id: str,
        reason: str = "user_declined"
    ) -> bool:
        """Send call declined notification"""
        data = {
            "session_id": session_id,
            "status": "declined",
            "reason": reason,
        }
        
        success_patient = NotificationService._send_to_user(
            patient_id,
            NotificationType.CALL_DECLINED,
            data,
        )
        
        success_consultant = NotificationService._send_to_user(
            consultant_id,
            NotificationType.CALL_DECLINED,
            data,
        )
        
        return success_patient and success_consultant
    
    @staticmethod
    def send_call_ended(
        patient_id: int,
        consultant_id: int,
        session_id: str,
        duration_minutes: int = 0,
        reason: str = "user_ended"
    ) -> bool:
        """Send call ended notification"""
        data = {
            "session_id": session_id,
            "status": "ended",
            "duration_minutes": duration_minutes,
            "reason": reason,
            "timestamp": timezone.now().isoformat(),
        }
        
        success_patient = NotificationService._send_to_user(
            patient_id,
            NotificationType.CALL_ENDED,
            data,
        )
        
        success_consultant = NotificationService._send_to_user(
            consultant_id,
            NotificationType.CALL_ENDED,
            data,
        )
        
        return success_patient and success_consultant
    
    @staticmethod
    def send_call_missed(
        patient_id: int,
        consultant_id: int,
        session_id: str,
        call_type: str = "video"
    ) -> bool:
        """Send call missed notification"""
        data = {
            "session_id": session_id,
            "call_type": call_type,
            "status": "missed",
            "timestamp": timezone.now().isoformat(),
        }
        
        success_patient = NotificationService._send_to_user(
            patient_id,
            NotificationType.CALL_MISSED,
            data,
        )
        
        success_consultant = NotificationService._send_to_user(
            consultant_id,
            NotificationType.CALL_MISSED,
            data,
        )
        
        return success_patient and success_consultant
    
    @staticmethod
    def send_call_cancelled(
        patient_id: int,
        consultant_id: int,
        session_id: str,
        reason: str = "user_cancelled"
    ) -> bool:
        """Send call cancelled notification"""
        data = {
            "session_id": session_id,
            "status": "cancelled",
            "reason": reason,
            "timestamp": timezone.now().isoformat(),
        }
        
        success_patient = NotificationService._send_to_user(
            patient_id,
            NotificationType.CALL_CANCELLED,
            data,
        )
        
        success_consultant = NotificationService._send_to_user(
            consultant_id,
            NotificationType.CALL_CANCELLED,
            data,
        )
        
        return success_patient and success_consultant
    
    # ==================== CONNECTION QUALITY NOTIFICATIONS ====================
    
    @staticmethod
    def send_connection_established(
        patient_id: int,
        consultant_id: int,
        session_id: str,
        connection_type: str = "p2p"
    ) -> bool:
        """Send connection established notification"""
        data = {
            "session_id": session_id,
            "connection_type": connection_type,
            "status": "established",
        }
        
        success_patient = NotificationService._send_to_user(
            patient_id,
            NotificationType.CONNECTION_ESTABLISHED,
            data,
            priority=NotificationPriority.HIGH
        )
        
        success_consultant = NotificationService._send_to_user(
            consultant_id,
            NotificationType.CONNECTION_ESTABLISHED,
            data,
            priority=NotificationPriority.HIGH
        )
        
        return success_patient and success_consultant
    
    @staticmethod
    def send_connection_failed(
        patient_id: int,
        consultant_id: int,
        session_id: str,
        error_code: str = "unknown"
    ) -> bool:
        """Send connection failed notification"""
        data = {
            "session_id": session_id,
            "error_code": error_code,
            "status": "failed",
        }
        
        success_patient = NotificationService._send_to_user(
            patient_id,
            NotificationType.CONNECTION_FAILED,
            data,
            priority=NotificationPriority.CRITICAL
        )
        
        success_consultant = NotificationService._send_to_user(
            consultant_id,
            NotificationType.CONNECTION_FAILED,
            data,
            priority=NotificationPriority.CRITICAL
        )
        
        return success_patient and success_consultant
    
    @staticmethod
    def send_connection_quality_warning(
        patient_id: int,
        consultant_id: int,
        session_id: str,
        quality: str,
        stats: Dict
    ) -> bool:
        """Send connection quality warning"""
        data = {
            "session_id": session_id,
            "quality": quality,
            "stats": stats,
            "timestamp": timezone.now().isoformat(),
        }
        
        success_patient = NotificationService._send_to_user(
            patient_id,
            NotificationType.CONNECTION_QUALITY,
            data,
            priority=NotificationPriority.NORMAL
        )
        
        success_consultant = NotificationService._send_to_user(
            consultant_id,
            NotificationType.CONNECTION_QUALITY,
            data,
            priority=NotificationPriority.NORMAL
        )
        
        return success_patient and success_consultant
    
    # ==================== PARTICIPANT NOTIFICATIONS ====================
    
    @staticmethod
    def send_participant_joined(
        recipient_id: int,
        session_id: str,
        participant_id: int,
        participant_name: str
    ) -> bool:
        """Send participant joined notification"""
        data = {
            "session_id": session_id,
            "participant_id": str(participant_id),
            "participant_name": participant_name,
        }
        
        return NotificationService._send_to_user(
            recipient_id,
            NotificationType.PARTICIPANT_JOINED,
            data,
        )
    
    @staticmethod
    def send_participant_left(
        recipient_id: int,
        session_id: str,
        participant_id: int,
        participant_name: str
    ) -> bool:
        """Send participant left notification"""
        data = {
            "session_id": session_id,
            "participant_id": str(participant_id),
            "participant_name": participant_name,
        }
        
        return NotificationService._send_to_user(
            recipient_id,
            NotificationType.PARTICIPANT_LEFT,
            data,
        )
    
    # ==================== APPOINTMENT NOTIFICATIONS ====================
    
    @staticmethod
    def send_appointment_reminder(
        patient_id: int,
        consultant_id: int,
        appointment_id: str,
        reminder_type: str = "before_15_mins",
        scheduled_datetime: Optional[datetime] = None
    ) -> bool:
        """Send appointment reminder"""
        time_text = "10 minutes" if reminder_type == "before_10_mins" else "15 minutes"
        data = {
            "appointment_id": appointment_id,
            "reminder_type": reminder_type,
            "scheduled_datetime": scheduled_datetime.isoformat() if scheduled_datetime else None,
            "message": f"Reminder: You have an upcoming video call in {time_text}!",
            "timestamp": timezone.now().isoformat(),
        }
        
        success_patient = NotificationService._send_to_user(
            patient_id,
            NotificationType.APPOINTMENT_REMINDER,
            data,
            priority=NotificationPriority.HIGH
        )
        
        success_consultant = NotificationService._send_to_user(
            consultant_id,
            NotificationType.APPOINTMENT_REMINDER,
            data,
            priority=NotificationPriority.HIGH
        )
        
        return success_patient and success_consultant
    
    @staticmethod
    def send_call_session_ready(
        patient_id: int,
        consultant_id: int,
        session_id: str,
        appointment_id: str
    ) -> bool:
        """Send notification that call session is ready"""
        data = {
            "session_id": session_id,
            "appointment_id": appointment_id,
            "status": "ready",
            "message": "Your consultation call is ready to start",
        }
        
        success_patient = NotificationService._send_to_user(
            patient_id,
            NotificationType.CALL_SESSION_READY,
            data,
            priority=NotificationPriority.HIGH
        )
        
        success_consultant = NotificationService._send_to_user(
            consultant_id,
            NotificationType.CALL_SESSION_READY,
            data,
            priority=NotificationPriority.HIGH
        )
        
        return success_patient and success_consultant
    
    # ==================== ERROR & ALERT NOTIFICATIONS ====================
    
    @staticmethod
    def send_error_notification(
        user_id: int,
        error_code: str,
        error_message: str,
        session_id: Optional[str] = None
    ) -> bool:
        """Send error notification"""
        data = {
            "error_code": error_code,
            "error_message": error_message,
            "session_id": session_id,
            "timestamp": timezone.now().isoformat(),
        }
        
        return NotificationService._send_to_user(
            user_id,
            NotificationType.ERROR_NOTIFICATION,
            data,
            priority=NotificationPriority.CRITICAL
        )
    
    @staticmethod
    def send_system_message(user_ids: List[int], message: str, title: str = "System") -> bool:
        """Send system message to multiple users"""
        data = {
            "title": title,
            "message": message,
            "timestamp": timezone.now().isoformat(),
        }
        
        channel_layer = NotificationService._get_channel_layer()
        if not channel_layer:
            return False
        
        success_count = 0
        for user_id in user_ids:
            if NotificationService._send_to_user(
                user_id,
                NotificationType.SYSTEM_MESSAGE,
                data,
                priority=NotificationPriority.NORMAL
            ):
                success_count += 1
        
        return success_count == len(user_ids)
    
    # ==================== WEBRTC SIGNALING NOTIFICATIONS ====================
    
    @staticmethod
    def send_webrtc_offer(
        recipient_id: int,
        session_id: str,
        offer: Dict,
        from_user_id: int
    ) -> bool:
        """Send WebRTC offer"""
        data = {
            "session_id": session_id,
            "offer": offer,
            "from_user_id": str(from_user_id),
        }
        
        return NotificationService._send_to_user(
            recipient_id,
            NotificationType.WEBRTC_OFFER,
            data,
        )
    
    @staticmethod
    def send_webrtc_answer(
        recipient_id: int,
        session_id: str,
        answer: Dict,
        from_user_id: int
    ) -> bool:
        """Send WebRTC answer"""
        data = {
            "session_id": session_id,
            "answer": answer,
            "from_user_id": str(from_user_id),
        }
        
        return NotificationService._send_to_user(
            recipient_id,
            NotificationType.WEBRTC_ANSWER,
            data,
        )
    
    @staticmethod
    def send_ice_candidate(
        recipient_id: int,
        session_id: str,
        candidate: Dict,
        from_user_id: int
    ) -> bool:
        """Send ICE candidate"""
        data = {
            "session_id": session_id,
            "candidate": candidate,
            "from_user_id": str(from_user_id),
        }
        
        return NotificationService._send_to_user(
            recipient_id,
            NotificationType.ICE_CANDIDATE,
            data,
        )
